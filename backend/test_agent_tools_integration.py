#!/usr/bin/env python3
"""测试Agent Tools集成"""
import asyncio
import sys
sys.path.insert(0, 'src')

async def test():
    from vibe_trading.agents.agent_factory import create_trading_agent, ToolContext, AgentConfig
    from vibe_trading.config.agent_config import AgentRole

    tool_context = ToolContext(symbol="BTCUSDT", interval="30m")

    config = AgentConfig(
        name="Technical Analyst",
        role=AgentRole.TECHNICAL_ANALYST,
        temperature=0.5,
    )

    agent = await create_trading_agent(config, tool_context, enable_streaming=False)

    tools = agent.state.get('tools', [])
    print(f"Tools数量: {len(tools)}")

    if tools:
        print("✅ Tools已设置:")
        for tool in tools:
            print(f"  - {tool.name}")
    else:
        print("❌ Tools为空！")

    print("测试完成")

if __name__ == "__main__":
    asyncio.run(test())
