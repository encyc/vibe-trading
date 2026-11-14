# 设计：用 zenagent kernel 替换 pi_agent_core + pi_ai

日期：2026-11-13
状态：待批准
范围：`backend/src/vibe_trading/` 的 agent 运行时层

---

## 1. 意图与理由

当前 `vibe_trading` 的 agent 运行时依赖 `pi-py` 的两个包（`pi-py-agent-core` + `pi-py-ai`，
均 0.83.0）。要替换成 `zenagent-py`（0.13.6）的 kernel。

为什么换：

- **pi-py 是 TS 项目的 Python 移植**（`__upstream_ref__ = "earendil-works/pi@v0.83.0"`），
  带来的是 TS 生态的抽象形状（`AgentOptions(initial_state={...})` 的 dict 风格、
  `EventStream` 对象、Pydantic 消息模型）。zenagent 是**原生 Python** 写的，
  dataclass 消息、async generator 循环、`async for` 事件流。
- **zenagent 只依赖 `httpx`**，kernel 五层（types/events/providers/agent/tools）可读可改。
  pi-py 依赖 openai SDK + pydantic + 一批 provider 适配层。
- **zenagent 暴露 `stream_fn` 这个接缝**，让每个 agent 的 `temperature`/`max_tokens`
  能注入进去（pi-py 的 `AgentOptions` 不给这个口子，见 §3.3）。

换的**不是**功能对等替换：zenagent 是 coding agent，pi-py 是通用 LLM 运行时。有些
pi-py 有的东西 zenagent 没有（见 §6），有些 zenagent 有的是我们不需要的（见 §7.2）。

---

## 2. 目标 / 非目标 / 反目标

### 目标

1. 17 个 import pi 的文件全部改到 `vibe_trading.runtime`，生产路径（coordinator 4 phase）
   行为等价（除 §3.3 的采样参数变更是**故意的**行为变更）。
2. agent 层的类型、消息、事件边界由**项目自己拥有**，不再直接 import 第三方 agent 框架。
   这是 `docs/PI_PLATFORM_CONFORMANCE.md` 里判为 Partial 的第 3 条不变量
   （"Runtime/LLM isolated behind an adapter; platform owns its types"）。
3. `AgentConfig.temperature` / `max_tokens`（12 个值，写了从未生效）真正到达 LLM。
4. 每个阶段可独立回滚；`pi_agent_core`/`pi_ai` 在最后一个阶段之前一直可 import。

### 非目标

- 不接 zenagent 的 `app/` 层（`Runtime` / `ChatController` / `Supervisor` / `Session` /
  `PermissionGate` / memory / todo / `task` 工具 / MCP / skills）。理由见 §7.2。
- 不改交易业务逻辑：24 个工具的业务函数、12 个 agent 的 prompt、4 phase 编排、
  风控/审计/执行链路，全部零改动。
- 不引入 zenagent 的会话持久化。`vibe_trading.db` 仍是唯一记账处（决定见 §8.1）。
- 不重写 `PrimeAgent` 的能力（决定见 §8.2：本轮不动生产路径之外的东西）。

### 反目标（即使能跑起来也算失败）

- 迁移后某个 agent 静默返回 `"Analysis failed - no response from agent"` ——
  这是 §3.1 那个 `.role` 陷阱的失败模式，不报错、只是空结果。
- 给 12 个 agent 引入它们不需要的框架能力（会话文件、cwd 假设、权限审批），
  让每个 agent 实例变重、启动变慢、在 `~/.zenagent/` 留下垃圾。
- 为了"保持兼容"写一层把 zenagent 完全遮住的适配层，等于只是换了个底层依赖、
  没拿到任何 zenagent 的可读性和可控性。

---

## 3. 已验证的契约差异（全部实测，非推测）

验证方式：`/Users/mac/zen-agent` 源码 + 在本项目 `.venv` 里跑的探针脚本（见附录 A）。
`llm.yaml` 的 15 个配置全部 401/403/400（key 过期），所以**端到端真机验证不可用**；
下列结论来自离线假流验证与源码对照。

### 3.1 zenagent 的消息 dataclass 没有 `.role` 属性（最高风险）

zenagent 的 `UserMessage`/`AssistantMessage`/`ToolResultMessage` 是 dataclass，
`role` **只存在于 `to_json()` 的返回值里**，不是属性：

```
roles: ['<NO ROLE ATTR>', '<NO ROLE ATTR>', '<NO ROLE ATTR>', '<NO ROLE ATTR>']
classes: ['UserMessage', 'AssistantMessage', 'ToolResultMessage', 'AssistantMessage']
```

pi-py 的消息是 Pydantic 模型，`role` 是 `Literal` 判别字段（真属性）。

项目里 **11 处**依赖这个假设：

```
backend/src/vibe_trading/agents/analysts/base_analyst.py:71,155
backend/src/vibe_trading/agents/analysts/technical_analyst.py:78,119,169
backend/src/vibe_trading/agents/decision/decision_agents.py:204,486
backend/src/vibe_trading/agents/researchers/researcher_agents.py:103,306
backend/src/vibe_trading/agents/risk_mgmt/risk_agents.py:106
backend/src/vibe_trading/prime/prime_agent.py:667（getattr(message,"role",None)!="assistant"）
```

写法都是 `[m for m in messages if getattr(m, "role", None) == "assistant"]`，
`getattr` 的默认值让它在 zenagent 上**返回空列表而不是抛异常**，于是走到底部的
`return "Analysis failed - no response from agent"`。编译通过、日志无错、结果全空。

对策：`vibe_trading/runtime/messages.py` 提供 `is_assistant(m)` 与
`last_assistant_text(messages)`（`isinstance` 判别），11 处改为调它。这 11 处是同一段
复制粘贴（连 `"".join(getattr(c, "text", str(c)) for c in content)` 都一样），
合成函数后 diff 反而更小。

`prime_agent.py:667` 的 `_process_agent_response` 同理。

### 3.2 Agent 表面 API 差异

| pi-py 0.83 | zenagent 0.13.6 | 影响面 |
|---|---|---|
| `Agent(AgentOptions(initial_state={...}))` | `Agent(model=, system_prompt=, tools=, api_key=, ...)` | 全部 6 处构造点 |
| `agent.state.messages` | `agent.messages`（property，返回浅拷贝） | 11 处 |
| `agent.state.is_streaming` / `.error_message` | `agent.is_streaming` / `agent.error_message` | `prime_agent.py:1016-1018` |
| `agent.clear_messages()` | **两边都没有**；zenagent 有 `agent.reset()` | `macro_agent.py:136`（现状已坏，见 §3.4） |
| `subscribe(cb)`，cb 收到 `(event, cancel_event=None)` | `subscribe(cb)`，cb 只收到 `(event)` | **不用改**：三个回调都有默认值，实测可接（见 §3.9） |
| `AgentEvent` 是 dataclass 联合，`agent_end` 带 `messages` | 单一 `AgentEvent` dataclass，`agent_end` 带 `new_messages`，另带 `turns`/`termination`/`tool_stats` | `prime_agent.py:647` 的 `event.messages` |
| `agent.prompt()` 运行中 → `RuntimeError("Agent is already processing...")` | → `RuntimeError("Agent is already running; await wait_for_idle() first")` | `prime_agent.py:576` 的字符串匹配（见 §3.5） |
| `AgentToolResult(content, details, added_tool_names, terminate)` | `ToolResultAgent(content, details, is_error, terminate, error_kind)` | `agent_tools.py` 35 处构造 + 1 处 `details=` |
| `execute(tool_call_id, params, cancel_event, on_update)` | `execute(call_id, args, abort, on_update)`（`abort` 是 `AbortToken` 不是 `asyncio.Event`） | `_PyTool` 适配器 1 处 |
| `AgentTool` 是 `Protocol`（含 `label`、`execution_mode`） | `AgentTool` 是 **dataclass**（有 `approval` 层级、`timeout_s`、`hidden`） | 工具构造方式改变 |
| `Model(provider, api, base_url, input=, context_window=, max_tokens=)` | `Model(provider, api, base_url, context_window, max_tokens, reasoning, cost, compat, supports_vision)` | `llm_config.py` |
| `stream_simple(model, Context, SimpleStreamOptions)` → EventStream | **无等价物**；只有 `agent_loop()` 与 `Agent` | `reflection.py`（唯一一处一次性调用） |

### 3.3 采样参数：从"写了不生效"变成"真的生效"

现在 `AgentConfig.temperature` 在 `agent_config.py` 有 12 个值（0.3–0.8），
`create_trading_agent()` 读 `config.role` 但**从不读 `config.temperature`**；
`AgentOptions` 也没有这个字段。所以温度一直停在服务商默认值。

zenagent 的 `Agent` 构造签名同样不含 `temperature`（`StreamOptions.temperature` 存在，
但 loop 构造 `StreamOptions` 时只填 `api_key`/`thinking`/`session_id`/`abort`）。
但 zenagent 的 `stream_fn` 是接缝——包一层即可注入，实测生效：

```
injected: {'temperature': 0.4, 'max_tokens': 2000}
```

实现：`runtime/model.py::tuned_stream(temperature, max_tokens)` 从 `stream_fn_for(model)`
取底层函数，`replace(options, temperature=..., max_tokens=...)` 后调用。

**这是行为变更**：同样的 prompt，agent 输出会变（尤其 bull/bear researcher 的 0.8）。
必须单独一次提交、单独评估。若不想引入不确定性，可以先用 `None` 让温度维持现状，
把开关留在 `AgentConfig` 上——但那等于放弃非目标 3。

### 3.4 一个既有 bug：`clear_messages()` 在 pi-py 0.83 里就不存在

```
has clear_messages: False
```

`macro_agent.py:136` 调用 `self._agent.clear_messages()`，而 `dir(Agent)` 里没有这个方法。
也就是说 **MacroAnalysisAgent 现在就是坏的**（`AttributeError`），只是 macro 线程
可能没跑到那条路径、或者异常被上层吞了。迁移时不能照抄，要给它 `reset()`。

同类：`prime_agent.py:1016` 读 `self.state.is_streaming` 和 `self.state.error_message`，
pi-py 的 `AgentState` 有这两个字段，所以那里现在是对的——迁移后要改成 `self.is_streaming`。

### 3.5 "Agent 忙"的异常消息不同 —— 会破坏 Prime 的字符串判断

`prime_agent.py:576` 靠异常消息字符串判断状态：

```python
except RuntimeError as e:
    if "already processing" in str(e):
        self._send_as_steering_message(message)
    else:
        raise
```

实测两个框架的原文完全不同：

| | 消息 |
|---|---|
| pi-py 0.83 | `'Agent is already processing. Use steer() or follow_up() to queue messages.'` |
| zenagent 0.13.6 | `'Agent is already running; await wait_for_idle() first'` |

`"already processing"` 在 zenagent 的消息里**不出现**，所以这段会走 `else: raise`。
后果是**抛异常而不是静默失效**（比 §3.1 好），但 Prime 的 steering 降级路径会整条失效：
并发来消息时不是排队，是炸。

对策：`TradingAgent` 暴露 `is_running` property，Prime 改成
`if self.is_running: self._send_as_steering_message(...)`，不再匹配字符串。
（顺带修掉一个既有反模式：用异常文本做控制流。）

### 3.6 llm.yaml 缺 zenagent `Model` 需要的字段

`llm.yaml` 每条只有 `provider` / `api_key` / `base_url` / `model` / `description`。
zenagent 的 `Model` 还需要 `context_window`、`max_tokens`、`reasoning`、`cost`、`compat`。

`compat` 是硬需求：`glm_4_7` 指向 `open.bigmodel.cn`（zai 方言），需要
`thinking_format=zai`、`zai_tool_stream=true`、`supports_developer_role=false`、
`max_tokens_field=max_tokens`。不补的话 GLM 的流式工具调用帧和 `developer` 角色会被
当纯 OpenAI 处理，而 GLM 是多数 prompt 的目标模型之一。`deepseek` 需要
`requires_reasoning_content_on_assistant`。

zenagent 有 `sniff_compat(base_url)` 作为兜底（按 host 猜方言），实测：

```
sniff bigmodel: thinking_format='zai', zai_tool_stream=True, supports_developer_role=False
sniff opencode: thinking_format=None, all defaults
sniff aliyun:   thinking_format=None, all defaults
```

`bigmodel.cn` 猜对了，opencode/aliyun 猜成纯 OpenAI（对这两个网关是对的）。

**但有一条更好的路**：zenagent 的 catalog（202 个模型，`load_catalog()` + `find_model(catalog, model_id)`）
里已经有你 yaml 里 15 个配置中的 4 个，且带着正确的 compat 和 context_window：

| yaml 配置 | model id | 在 catalog | catalog provider / context_window |
|---|---|---|---|
| `glm_4_7` | `glm-4.7` | **是** | `zai` / 204800 |
| `openai_gpt4o` | `gpt-4o` | **是** | `openai` / 128000 |
| `openai_gpt4o_mini` | `gpt-4o-mini` | **是** | `openai` / 128000 |
| `gemini_pro` | `gemini-1.5-pro` | **是** | `google` / 1000000 |
| 其余 11 个 | — | 否 | — |

对策：`runtime/model.py` 的解析顺序是
**catalog 命中 → 用 catalog 的 compat/context_window/max_tokens（yaml 仍可覆盖）→ 未命中 → `sniff_compat(base_url)` → yaml 的显式字段优先于两者**。
这样只给 11 个非 catalog 模型写 compat，且不用手抄 GLM 的 zai 方言。

### 3.7 成本永远是 0（不是缺陷，是须知）

zenagent 的 `Cost` 从 catalog 单价计算。`llm.yaml` 的 15 个配置里 11 个不在 catalog，
所以 `usage.cost.total` 会恒为 0（实测确认）。pi-py 那边本来也不报成本
（`token_optimizer.py` 自己按硬编码价格估）。

影响：`TradingAgent` **不要**暴露 cost 相关 API 给调用方，避免让人以为它是准的。
若将来要成本，在 yaml 里补 `cost:` 字段或让 catalog 命中。

### 3.8 两个项目已经在用的 `cancel_event` 参数其实没人读

`AgentTool.execute` 在两边的签名第三个参数都是取消信号（pi 是 `asyncio.Event`，
zenagent 是 `AbortToken`）。项目里只有 `agent_tools.py:56` 声明了它，**24 个工具实现
没有一个读它**（`grep cancel_event` 除声明与注释外 0 命中）。所以这个类型变更
是零成本的——但也不能顺手把它当"取消能力"用，因为下游工具不支持。

### 3.9 订阅回调的签名：2 参兼容，1 参也行

zenagent 的 `_dispatch` 只传 `event` 一个参数。项目里三个回调的签名是
`(event, cancel_event=None)`（`agent_factory.py:35`、`decision_agents.py:377`、
`prime_agent.py:633`）——有默认值所以能接住，实测通过：

```
2-arg callback works: True
first 3: [('agent_start', None), ('message_start', None), ('message_end', None)]
```

**不需要改这三个回调**。这与我先前的判断不同（先前以为必须改成 1 参），
实测证明不用动——少改 3 处。

### 3.10 config.temperature 确实是死字段

`inspect.getsource(create_trading_agent)` 搜 `temperature`/`max_tokens`：两个都是
`False`。确认 §3.3 的判断——12 个温度值写了从未生效。

---

## 4. 做法

### 4.1 形状：`vibe_trading/runtime/` 包 + 持有而非继承

新增 `backend/src/vibe_trading/runtime/`，约 300 行，是唯一 import `zenagent` 的地方：

```
runtime/
  __init__.py     导出 TradingAgent, Model 构造, AgentTool 适配, 消息提取
  model.py        llm.yaml → zenagent Model；tuned_stream() 注入采样
  messages.py     is_assistant() / last_assistant_text() / text_of() / usage_of()
  tools.py        PyTool：Pydantic 参数类 + 异步 execute → zenagent AgentTool dataclass
  agent.py        TradingAgent：包装 zenagent Agent，向上提供项目需要的最小面
```

12 个 agent 文件从 `from pi_agent_core import Agent, AgentOptions` 改为
`from vibe_trading.runtime import TradingAgent`，业务逻辑不动。

**为什么是持有而不是继承**：`PrimeAgent` 现在 `class PrimeAgent(Agent)`。zenagent 的
`Agent.__init__` 是 `(model, system_prompt, tools, api_key, *, ...)`，
pi-py 是 `(AgentOptions)` —— 两种构造形状靠改一行兼容不了。更重要的是继承会把框架的
版本演进锁死在我们的类层次里（zenagent 目前 0.13.x，架构文档记录了一次
"2026-11-07 架构清理"，`StreamOptions`、工具协议都搬过家）。持有 + 薄转发更稳。

`TradingAgent` 提供的最小面：

```python
class TradingAgent:
    def __init__(self, *, role, system_prompt, tools, model=None, temperature=None,
                 max_tokens=None, streaming_name=None, on_event=None): ...
    async def prompt(self, text: str) -> None        # 转发；不支持并发（zenagent 只允许一次 run）
    async def wait_for_idle(self) -> None
    def abort(self) -> None
    @property is_running -> bool                   # 替掉 Prime 的异常字符串匹配（§3.5）
    @property messages -> list                     # 转发 agent.messages
    def last_assistant_text(self) -> str           # 走 messages.py
    def reset(self) -> None                        # 转发 agent.reset()
    def subscribe(self, cb) -> None                # 透传；2 参回调也能接
    def steer(self, text: str) -> None             # zenagent 的 steer 接受 str
```

这里刻意**不**复制 zenagent 的 `AgentState`：只暴露调用点实际用到的成员，
而不是把整个状态机透传出去。也**不**暴露 cost（§3.7：11/15 配置恒为 0）。

### 4.2 工具适配：`_PyTool` 换目标，业务零改动

`agent_tools.py` 现有的 `_PyTool` 适配器（约 45 行）思路正是需要的：把
`(Pydantic 参数类, 异步 execute 函数)` 包成框架的 tool。只需换目标：

- `AgentToolResult(...)` → `ToolResultAgent(...)`（35 处构造，只改类型名；
  `content`/`details` 字段名一致；`added_tool_names` zenagent 没有但项目也没用）
- `parameters = ParamsClass.model_json_schema()`（不变，zenagent 也要 JSON Schema dict）
- `execute(self, tool_call_id, params, cancel_event, on_update)` →
  `execute(self, call_id, args, abort, on_update)`；`cancel_event` 的类型从
  `asyncio.Event` 变 `AbortToken`，但项目里 24 个工具**没有一个读它**，直接丢弃即可
- zenagent 的 `AgentTool` 是 dataclass 不是 Protocol，所以适配器可以简化为直接
  构造 dataclass（不再需要 `_PyTool` 这个类，用一个工厂函数 `make_tool(...)` 代替）
- 加 `approval`：交易工具全是"调外部 API / 下单"，按 zenagent 的语义应是 `"exec"`；
  `submit_trade_order` 额外给 `execution_mode="sequential"`（zenagent 的 `is_exclusive`
  会把 `approval="write"` 或 `sequential` 的工具单独串行执行）——这正好对上
  "下单不能与其他工具并发"的隐含要求

### 4.3 `agent_factory.py` 是唯一的构造入口（保持现状）

现在 `create_trading_agent()` 是 12 个 agent 里 11 个的创建入口
（`decision_agents.py` 的 PortfolioManager 自建、`macro_agent.py` 自建、
两个 `emergency_agent.py` 自建——共 5 处自建点）。

迁移时**不改这个形状**：`create_trading_agent()` 改为返回 `TradingAgent`，
5 处自建点各自改构造调用。不借机重构成"统一工厂"——那是独立的重构，不在本次范围。

### 4.4 `reflection.py`：唯一的一次性 LLM 调用

`memory/reflection.py` 用 `pi_ai.stream_simple(model, Context, SimpleStreamOptions)`
做无工具的单轮调用。zenagent 没有等价 helper（只有 `agent_loop` 和 `Agent`）。

对策：`runtime/agent.py` 加 `async def one_shot(model, system_prompt, user_text) -> str`，
内部构造一个无工具的 `Agent`，`prompt()` + `wait_for_idle()` + `last_assistant_text()`。
约 15 行。不引 `agent_loop` 直用是因为 `Agent` 已经把事件订阅、idle 等待、
错误翻译（异常→`stop_reason="error"`）做好了。

### 4.5 文档

`docs/pi_agent_core.md` 现在描述 pi 的用法。迁移完成后它变成历史文档；
新增 `docs/zenagent_kernel.md` 记录：kernel 五层里我们用了哪几层、`runtime/` 的
6 个文件各管什么、§3 那张契约差异表（作为踩坑清单）。
`README.md`/`CLAUDE.md`/`AGENTS.md` 里 `pi-py`/`pi-agent-core` 的字样改掉。
`docs/PI_PLATFORM_CONFORMANCE.md` 是历史评审报告，**不改**（它是某个时间点的快照）。

---

## 5. 阶段划分与每阶段的验证

每一阶段独立可回滚；`pi_agent_core`/`pi_ai` 到阶段 5 才移除。

| 阶段 | 内容 | 验证（可执行） |
|---|---|---|
| 0 | `runtime/` 骨架 6 文件；`TradingAgent`、`make_tool`、`messages`、`tuned_stream`、`one_shot`、`llm_config` 扩展 | 离线假流：构造 agent → `prompt` → 工具轮 → `last_assistant_text()` 拿到文本；`tuned_stream` 注入的 `temperature`/`max_tokens` 出现在 `StreamOptions` |
| 1 | `agent_tools.py`：`_PyTool` → `make_tool`，35 处 `AgentToolResult`→`ToolResultAgent`，加 `approval`/`execution_mode` | `get_all_tools()` 返回 24 个；`get_tools_for_agent()` 对 12 个角色返回预期集合（现有硬编码 if/elif 不变）；`create_submit_trade_order_tool()` 构造成功 |
| 2 | 11 个 agent 文件：换 import + 11 处 `.role` 提取；5 处自建点改 `TradingAgent` 构造；`macro_agent.clear_messages()`→`reset()` | `pytest tests/`（18 个文件，其中多数需要网络/key，只要求 import 与构造通过）；`python -c` 逐个构造 12 个 agent |
| 3 | `reflection.py` → `one_shot()` | 反思路径返回非空文本（离线假流） |
| 4 | `PrimeAgent` + `subagent_factory` + `subagent_handle`：继承 → 持有；`"already processing"` 字符串匹配 → `is_running`（§3.5）；`event.messages` → `event.new_messages` | `tests/prime/` 两个文件；`PrimeAgent.__init__` 能构造；并发 prompt 走 steering 而不是抛异常 |
| 5 | `pyproject.toml`：去 `pi-py-ai`/`pi-py-agent-core`，加 `zenagent-py>=0.13.6`；清理 `docs/pi_agent_core.md` | `uv sync` 干净；`grep -rn "pi_agent_core\|pi_ai" backend/src` 只剩 0 命中；`python -c "import vibe_trading.cli"` |

阶段 2 之后到阶段 4 之前，`pi_agent_core` 仍被 `prime/` 引用，所以 **zenagent 与 pi-py
短期共存**。这是有意的：不搞大爆炸式一次切完。

---

## 6. pi-py 有、zenagent 没有的能力（迁移时要知道丢了什么）

逐项确认项目是否在用：

| 能力 | pi-py | zenagent | 项目在用吗 |
|---|---|---|---|
| `openai-responses` 适配器 | 有 | 有 | 否 |
| `google-generative-ai` 适配器 | 有（`pi_ai/providers`） | 有（`google_generative_ai.py`） | `llm.yaml` 有 `gemini_pro`，但 provider 映射成 `openai-completions`——本身就不对 |
| 一次性调用 helper | `stream_simple`/`complete_simple` | 无（§4.4 自己包） | 1 处 |
| 会话持久化 | `JsonlSessionStorage`/`Session` | `Session`（更完整：boundary、派生、租约） | 否 |
| 上下文压缩 | `harness.compaction`（`should_compact`/`compact`） | `config.naive_overflow_prune` + `transform_context` 接缝 | 否（`token_optimizer.py` 自己做 prompt 截断） |
| Skills | `harness.skills` | `skills.py`（更完整，文件驱动） | 否 |
| `prepare_next_turn` / `convert_to_llm` 钩子 | 有 | 无（只有 `before/after_tool_call`、`transform_context`、`get_steering_messages`） | 否（`grep` 0 命中） |
| `follow_up_queue` | 有 | 无（只有 `steer`） | 否（只在注释里被提到） |
| 每模型 `thinking_budgets` | 有 | `stream_options.thinking`（off/low/medium/high/max） | 否 |

结论：**唯一真实的能力缺口是一次性调用**，其余要么没在用，要么 zenagent 更强。

## 7. 不做什么

### 7.1 不接 zenagent 的 `app/` 层

`zenagent.app`（`Runtime`/`ChatController`/`CommandRegistry`/`SessionManager`/
`PermissionGate`/`Supervisor`/`WorkspaceState`/`RunLedger`/`SessionLease`）是给
"一个人在 git 仓库里跟一个 coding agent 对话"设计的。它内建：

- 会话落盘到 `~/.zenagent/`（`sessions/`、`projects/`、`locks/`）
- cwd / git root 假设（`project.py` 找最近的 `.git`）
- `AGENTS.md` / `CLAUDE.md` 作为 context 文件读入
- 权限审批门（`ask` 工具、`PermissionBroker`）
- `task` 子代理、`todo`、`memory`、`lsp`、`github` 工具
- Zen 模式（router + worker fleet）、Swarm 模式（多角色房间）

我们的 12 个 agent 是**程序驱动的流水线**：没人坐在终端前，没有 git 仓库语义，
没有审批对话，状态写 `vibe_trading.db`。接 `app/` 会让每个 agent 实例多出一堆
用不上的东西，并把数据落盘位置绑到 `~/.zenagent/`。

**只取 kernel 四层**：`types` / `events` / `providers` / `agent`。`tools` 层只用来
对照写法（我们要的是 24 个交易工具，不是文件/bash/搜索）。

### 7.2 不引入 zenagent 的会话持久化（决定 §8.1）

### 7.3 不重写 PrimeAgent 的能力（决定 §8.2）

### 7.4 不借机重构的东西

`get_tools_for_agent()` 的 if/elif 角色链、`token_optimizer.py`、
`create_trading_agent()` 的工厂形状、`docs/PI_PLATFORM_CONFORMANCE.md`——
都在"能改"的范围外。它们各自是独立的重构，混进来会让这次迁移无法验证。

---

## 8. 已做的决定（附理由）

### 8.1 不接 zenagent 的会话持久化

zenagent 的 `Session`（JSONL append-only，带 boundary、派生、单 writer 租约）比
pi-py 的 `JsonlSessionStorage` 完整得多，是它的强项。但：

- 项目已经有两套存储：`vibe_trading.db`（决策/kline/macro/trigger/order audit）
  和 `web/journal_storage.py`（per-bar 决策日志）。再加第三套（每 agent 一个
  JSONL）会让"这次决策依据什么"的溯源变成三处拼。
- zenagent 的 `Session` 的 boundary 语义是为 `/compact` 和 fork 服务的，
  我们不做交互式压缩和 fork。
- 12 个 agent 每次分析完就丢弃上下文（`macro_agent` 甚至主动清空），
  持久化的收益是"事后审计"，而审计已经有 `vibe_trading.db` + `logs/`。

结论：`vibe_trading.db` 继续当唯一记账处。若将来要 trace 每个 agent 的完整
transcript，用 `TradingAgent.on_event` 回调写进现有 DB，而不是引 `Session`。

### 8.2 本轮迁移生产路径，PrimeAgent 最后单独一轮

`PrimeAgent` 是 1026 行的 `Agent` 子类，现状：

- 3 个 subagent 是 `enabled=False` 的 stub（`subagent_factory.py:55,63,70`）
- `_parse_decision_from_text` 用关键词匹配（`"买入" in text` / `"buy" in text_lower`）
- `_prompt_agent_for_decision` 里 `except RuntimeError as e: if "already processing" in str(e)`
  ——靠异常消息字符串判断状态

它是半成品。迁移它要动 1026 行 + 2 个测试文件，而它不属于生产路径
（生产路径是 `coordinator/trading_coordinator.py` 的 4 phase）。

结论：阶段 4 只做**最小可迁移**——让 `PrimeAgent` 从继承改成持有 `TradingAgent`、
构造能通过、`tests/prime/` 的 import 和构造断言通过。**不修**它的关键词决策、
不启用 stub subagent。那些是独立的技术债，单独处理。

---

## 9. 留给实现者的空间

- `TradingAgent` 到底暴露几个成员：以"17 个文件的调用点实际用到的"为准，多一个不加。
- `runtime/model.py` 的 catalog 复用粒度：是"catalog 命中就整条采用 catalog 的
  compat/context_window"，还是"catalog 只补 yaml 没写的字段"（设计倾向后者，
  但 yaml 现在一条都没写，所以两者在阶段 0 结果相同）。
- 阶段 1 的 `make_tool` 是工厂函数还是保留 `_PyTool` 类（倾向函数，更短）。
- 阶段 2 的 11 处 `.role` 提取，是逐个替换还是先加 `is_assistant()` 再批量替换
  （倾向后者，一次提交）。
- 离线假流测试放在 `tests/` 还是 `runtime/` 内的 doctest（倾向 `tests/test_runtime_offline.py`，
  用 zenagent 自己的 `examples/custom_tool.py` 那套 fake stream 写法）。

---

## 附录 A：验证脚本

五个探针脚本（会话内临时文件，结论已抄进 §3）：

1. `/tmp/zen_spike.py` —— 真实端点 + 工具。结果：请求打到 `opencode.ai/zen/v1`，
   401 被翻译成 `error` 事件（`partial.error_message` 带原文），**不抛异常**。
   证明 zenagent 的错误处理路径正确，但 key 过期无法验证正常路径。
2. `/tmp/probe.py` —— `llm.yaml` 全部 15 个配置逐个试。结果：15/15 全部 4xx
   （401/403/400/404）。结论：**端到端真机验证不可用**。
3. `/tmp/offline.py` —— 假流 + 工具轮。结果见 §3.1/§3.2：
   - 事件序列 `agent_start → message_start/end → turn_start → ... → tool_execution_start/end → ... → agent_end`
   - 4 条消息全部 `<NO ROLE ATTR>`
   - `agent.messages` 存在，`agent.state` 不存在，`clear_messages` 不存在，`reset` 存在
   - `termination == "stop"`，工具结果正确回填
4. `/tmp/temp2.py` —— `stream_fn` 包装注入采样。结果
   `injected: {'temperature': 0.4, 'max_tokens': 2000}`。
5. `/tmp/legacy_cb.py` —— 2 参回调 + 忙状态异常文本。结果：项目现有
   `(event, cancel_event=None)` 回调**不用改**（§3.9）；两个框架的忙状态异常消息不同，
   `"already processing"` 在 zenagent 版本里不出现（§3.5）。

另有两处用 `python -c` 直接验的：`find_model(load_catalog(), id)` 对 `glm-4.7`/
`gpt-4o`/`gpt-4o-mini`/`gemini-1.5-pro` 命中且带正确 compat（§3.6）；
`inspect.getsource(create_trading_agent)` 确认不读 temperature/max_tokens（§3.10）。

## 附录 B：17 个 import 点清单

```
agents/agent_factory.py          Agent, AgentOptions, AgentEvent, AgentTool, TextContent, ThinkingContent
agents/agent_tools.py            AgentToolResult, TextContent
agents/analysts/base_analyst.py  Agent, AgentOptions
agents/analysts/technical_analyst.py  Agent, AgentOptions
agents/decision/decision_agents.py    Agent, AgentOptions
agents/decision/emergency_agent.py    Agent, AgentOptions
agents/macro_agent.py            Agent, AgentOptions
agents/researchers/researcher_agents.py  Agent, AgentOptions
agents/risk_mgmt/emergency_agent.py   Agent, AgentOptions
agents/risk_mgmt/risk_agents.py  Agent, AgentOptions
cli.py                           （字符串提及："基于pi_agent_core的新架构"）
config/llm_config.py             Model
memory/reflection.py             stream_simple, Context, UserMessage, TextContent, SimpleStreamOptions
prime/models.py                  （注释提及）
prime/prime_agent.py             Agent, AgentOptions, AgentMessage, TextContent, UserMessage
prime/subagent_factory.py        Agent
prime/subagent_handle.py         Agent
```

`cli.py` 与 `prime/models.py` 只有字符串/注释提及，阶段 5 顺带改。
