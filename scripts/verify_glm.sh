#!/bin/bash
# 0 点后验证：GLM 配额重置后，用真实端点跑通迁移后的 agent 栈
cd /Users/mac/vibe-trading
LOG=/tmp/glm_verify_$(date +%Y%m%d_%H%M%S).log
exec > "$LOG" 2>&1
echo "=== started $(date) ==="

PYTHONPATH=backend/src .venv/bin/python - <<'PY'
import asyncio, json, sys
from vibe_trading.runtime import TradingAgent

RESULTS = {}

async def probe(name, system_prompt, user_text, tools=None):
    try:
        a = TradingAgent(role=name, system_prompt=system_prompt, tools=tools or [])
        await asyncio.wait_for(a.prompt(user_text), timeout=120)
        results[name] = {
            "termination": a.termination,
            "text_len": len(a.last_assistant_text()),
            "text_head": a.last_assistant_text()[:160],
            "error": a.error_message,
            "messages": [type(m).__name__ for m in a.messages],
        }
    except Exception as e:
        results[name] = {"exception": f"{type(e).__name__}: {e}"}
    return results[name]

async def main():
    print("--- 1. bare model call ---")
    r = await probe("smoke", "Reply with exactly: ok", "say ok")
    print(json.dumps(r, ensure_ascii=False, indent=2))

    print("\n--- 2. tool round (real tool, real model) ---")
    from vibe_trading.agents.agent_tools import get_tools_for_agent
    tools = [t for t in get_tools_for_agent("technical_analyst") if t.name == "get_current_price"]
    r2 = await probe(
        "tool_round",
        "You are a crypto analyst. Call the tool to get the price, then answer in one Chinese sentence.",
        "BTCUSDT 现在多少钱？",
        tools=tools,
    )
    print(json.dumps(r2, ensure_ascii=False, indent=2))

    print("\n--- 3. full agent via factory ---")
    from vibe_trading.agents.agent_factory import create_trading_agent, ToolContext
    from vibe_trading.config.agent_config import AgentTeamConfig
    ctx = ToolContext(symbol="BTCUSDT", interval="30m", storage=None)
    a = await create_trading_agent(AgentTeamConfig().technical_analyst, ctx)
    await asyncio.wait_for(a.prompt("用一句话说明当前 BTCUSDT 的技术面，然后调用工具取一次价格。"), timeout=180)
    print(json.dumps({
        "termination": a.termination,
        "text_len": len(a.last_assistant_text()),
        "text_head": a.last_assistant_text()[:300],
        "error": a.error_message,
        "messages": [type(m).__name__ for m in a.messages],
    }, ensure_ascii=False, indent=2))

    ok = (r.get("termination") == "stop" and r.get("text_len", 0) > 0)
    print("\n=== VERDICT:", "PASS" if ok else "FAIL", "===")
    sys.exit(0 if ok else 1)

results = {}
asyncio.run(main())
PY
echo "=== finished $(date) rc=$? ==="
