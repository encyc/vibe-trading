# zenagent kernel 使用说明

本项目用 [`zenagent-py`](https://pypi.org/project/zenagent-py/)（0.13.6）作为
agent 运行时。本文记录**我们用了它的哪几层**、`runtime/` 各文件管什么，以及一张
与旧 pi-py 的契约差异表（踩坑清单）。

> 历史背景：项目曾用 `pi-py`（`pi-py-ai` + `pi-py-agent-core` 0.83.0，
> 是 TS 项目 `earendil-works/pi` 的 Python 复刻）。迁移原因与设计见
> `docs/superpowers/specs/2026-11-13-zenagent-kernel-migration-design.md`。

## 只用了 kernel 的四层

zenagent 有六层，我们只用下面四层；`app/` 和 `cli/` 一层都没用：

```
zenagent/types.py       消息 / 内容块 / Usage / Cost          ✅ 用
zenagent/events.py      AssistantEvent / AgentEvent / AbortToken ✅ 用
zenagent/providers/     catalog / compat / 各协议适配器        ✅ 用
zenagent/agent/         loop + Agent 状态机                    ✅ 用
zenagent/tools/         文件/bash/grep/web/todo/task/lsp…      ❌ 不用
zenagent/app/           Runtime/ChatController/Session/权限门   ❌ 不用
zenagent/cli/           TUI/REPL/headless/RPC                  ❌ 不用
```

**为什么不接 `app/`**：它是给"一个人在 git 仓库里跟一个 coding agent 对话"
设计的——会话落盘到 `~/.zenagent/`、读 `AGENTS.md`、权限审批、`task` 子代理、
Zen/Swarm 多角色编排。本项目的 12 个 agent 是**程序驱动的流水线**：没人坐在终端前，
没有 git 仓库语义，状态写 `vibe_trading.db`。接进来只会让每个 agent 实例变重，
并把数据落盘位置绑到 `~/.zenagent/`。

## `runtime/` 的六个文件

`vibe_trading/runtime/` 是**唯一 import `zenagent` 的地方**。换内核只改这个包。

| 文件 | 职责 |
|---|---|
| `messages.py` | 消息读取：`is_assistant()` / `last_assistant_text()` / `message_text()` |
| `model.py` | 取 Model + 凭证；`tuned_stream()` 把温度/输出上限注入 `StreamOptions` |
| `tools.py` | `make_tool()`：Pydantic 参数类 + 执行函数 → `zenagent.AgentTool` |
| `agent.py` | `TradingAgent`（持有 `zenagent.Agent`）+ `one_shot()` |
| `__init__.py` | 门面导出 |

`agent_factory.create_trading_agent()` 是 12 个 agent 的主要构造入口；
另有 4 处自建（`macro_agent`、两个 `emergency_agent`、PortfolioManager）直接
构造 `TradingAgent`。

## 契约差异清单（迁移时逐条验过的坑）

### 1. 消息没有 `.role` 属性 —— 最危险的一条

zenagent 的消息是 dataclass，`role` **只出现在 `to_json()` 的返回值里**：

```python
>>> from zenagent.types import AssistantMessage
>>> hasattr(msg, "role")
False
```

所以**绝不能**写 `getattr(m, "role", None) == "assistant"`——它不报错，只是永远
取到 `None`，把"agent 没回复"伪装成正常空结果。一律用
`runtime.messages.is_assistant(m)`（内部是 `isinstance`）。

`tests/test_runtime_offline.py::test_zen_message_has_no_role_attribute` 钉住了这个
事实：如果 zenagent 哪天加了 `.role`，那条测试会失败并提醒我们简化代码。

### 2. Agent 表面 API

| 旧（pi-py） | 新（zenagent） |
|---|---|
| `Agent(AgentOptions(initial_state={...}))` | `Agent(model=, system_prompt=, tools=, api_key=)` |
| `agent.state.messages` | `agent.messages` |
| `agent.state.is_streaming` | `agent.is_streaming` |
| `agent.clear_messages()`（**pi-py 里也不存在**） | `agent.reset()` |
| `agent.subscribe(cb)`，cb 收到 `(event, cancel_event)` | cb 只收到 `(event)` |
| `AgentEvent` 是 dataclass 联合，`agent_end.messages` | 单一 dataclass，`agent_end.new_messages` |

**2 参回调不用改**：三个既有回调的签名是 `(event, cancel_event=None)`，有默认值
就能接住单参调用，实测通过。

### 3. "Agent 忙"的异常文本不同

| | 消息 |
|---|---|
| pi-py | `'Agent is already processing. Use steer() or follow_up() to queue messages.'` |
| zenagent | `'Agent is already running; await wait_for_idle() first'` |

`PrimeAgent` 原来靠 `if "already processing" in str(e)` 判断并降级到 steering。
在新框架下这段会走 `else: raise`，整条降级路径失效。已改为读
`TradingAgent.is_running`——顺带修掉"用异常文本做控制流"这个反模式。

### 4. 采样参数要自己注入

zenagent 的 `Agent` 没有 `temperature` / `max_tokens` 参数，loop 构造
`StreamOptions` 时只填 `api_key` / `thinking` / `session_id` / `abort`。
`stream_fn` 是公开接缝，包一层即可：

```python
def tuned_stream(temperature=None, max_tokens=None):
    async def stream(model, messages, tools, options):
        options = replace(options, temperature=temperature, max_tokens=max_tokens)
        async for event in stream_fn_for(model)(model, messages, tools, options):
            yield event
    return stream
```

迁移前 `AgentConfig.temperature` 有 12 个值但**从未被读取**（
`create_trading_agent` 不读它）。所以现在是真生效，属于**故意的行为变更**：
同样的 prompt，输出会变。

### 5. Model 的技术参数从 catalog 继承

`llm.yaml` 只选模型（`provider` + `model`），`base_url` / `compat` /
`context_window` / `max_tokens` / 定价都从 zenagent 的 catalog（202 个模型）继承。
catalog 未收录时用 `sniff_compat(base_url)` 按 host 猜方言。

`compat` 不能省：GLM 需要 `thinking_format=zai`、`zai_tool_stream=true`、
`supports_developer_role=false`；DeepSeek 需要
`requires_reasoning_content_on_assistant`。手抄这些容易错，所以优先命中 catalog。

### 6. 成本可能是 0

`Cost` 由 catalog 单价计算。catalog 未收录的模型 → `usage.cost.total` 恒为 0。
所以 `TradingAgent` **不暴露** cost API，避免让人误以为它是准的。

### 7. 一次性调用没有 helper

zenagent 只有 `agent_loop()` 和 `Agent`，没有 `stream_simple` 这类单轮 helper。
`runtime.one_shot()` 是 15 行的替代品（单轮、无工具、跑完取文本）。

### 8. 输出被截断时 `termination` 仍是 `"stop"`

`termination` 只在 provider 报错/取消时变成 `"error"` / `"aborted"`；正常轮次的
终止原因在**最后一条助手消息的 `stop_reason`** 上。文本撞 `max_tokens` 时
`stop_reason == "length"`，而 `termination` 依然是 `"stop"`——调用方若只看
`termination`，会把半截报告当成完整报告。

所以 `TradingAgent` 提供 `last_stop_reason` / `was_truncated`。相关的一条决定：
`AgentConfig.max_tokens` 的默认值从 2000 改成 `None`。那个 2000 在迁移前**从未
生效过**，是未经验证的历史值；迁移后若直接生效会截断长分析报告。要收紧输出上限的
agent 需显式设置。`tests/test_runtime_offline.py::test_truncated_output_is_visible_not_silent`
钉住了这个行为。

## llm.yaml 与凭证

`llm.yaml` **不存明文 key**。凭证解析顺序：

1. yaml 里显式写的 `api_key`（支持 `${VAR}`）——仅仅为了向后兼容
2. `~/.zenagent/settings.json` 的 `api_keys`（zenagent 自己的约定，优先于环境变量）
3. 环境变量，键名取自 catalog 的 `api_key_env`

> 历史遗留：迁移前的 `llm.yaml` 含明文 key（longcat / iflow / glm_4_7 /
> aliyun_* / opencode-zen），这些已进入 git 历史。轮换需另行处理。

## 测试

`tests/test_runtime_offline.py` 用 zenagent 的 fake-stream 接缝跑，**不需要网络与
API key**，覆盖：消息提取（含 `.role` 陷阱）、工具适配、采样注入、完整工具轮、
2 参回调兼容、`is_running`、`reset`。

```bash
PYTHONPATH=backend/src uv run pytest tests/test_runtime_offline.py -v
```
