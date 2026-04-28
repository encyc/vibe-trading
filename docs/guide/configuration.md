# 配置说明

本文档说明当前 Vibe Trading 的主要配置项。系统默认读取项目根目录的 `.env` 文件；如果不存在，会退回到进程环境变量。

## 快速配置

建议从示例文件开始：

```bash
cp .env.example .env
```

常用配置如下：

```env
# 交易模式：paper 为模拟交易，live 为实盘交易
TRADING_MODE=paper

# 交易对与 K 线周期
SYMBOLS=BTCUSDT,ETHUSDT
INTERVAL=30m

# 风控参数
MAX_POSITION_SIZE=0.1
MAX_TOTAL_POSITION=0.3
STOP_LOSS_PCT=0.02
TAKE_PROFIT_PCT=0.05
LEVERAGE=5

# Agent 设置
DEBATE_ROUNDS=2
ENABLE_MEMORY=true
MEMORY_TOP_K=3

# LLM 配置名称：对应 backend/src/pi_ai/llm.yaml
LLM_MODEL=glm_4_7

# 按所选模型需要配置对应 API Key
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
XAI_API_KEY=your_xai_api_key_here

# Binance 测试网：Paper Trading 默认使用
BINANCE_TESTNET_API_KEY=your_testnet_api_key_here
BINANCE_TESTNET_API_SECRET=your_testnet_api_secret_here

# Binance 主网：Live Trading 才需要
BINANCE_API_KEY=your_mainnet_api_key_here
BINANCE_API_SECRET=your_mainnet_api_secret_here

# 情绪和新闻数据源
CRYPTOCOMPARE_API_KEY=your_cryptocompare_api_key_here
LUNARCRUSH_API_KEY=your_lunarcrush_api_key_here

# 日志与数据库
LOG_LEVEL=INFO
DATABASE_URL=sqlite+aiosqlite:///./vibe_trading.db
DEBUG=false
```

## LLM 配置

`LLM_MODEL` 不是直接填写供应商名称，而是填写 `backend/src/pi_ai/llm.yaml` 中的配置名，例如 `glm_4_7`、`iflow`、`longcat`、`gemini3_flash` 等。

切换模型时：

1. 在 `backend/src/pi_ai/llm.yaml` 中确认配置名存在。
2. 在 `.env` 中设置 `LLM_MODEL=<配置名>`。
3. 按该配置需要设置对应 API Key，例如 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GOOGLE_API_KEY`。

## Binance 配置

Paper Trading 默认使用 Binance Futures Testnet：

```env
BINANCE_TESTNET_API_KEY=your_testnet_api_key_here
BINANCE_TESTNET_API_SECRET=your_testnet_api_secret_here
```

Live Trading 才会使用主网 key，并且启动命令需要显式传入 live 模式和执行确认：

```env
BINANCE_API_KEY=your_mainnet_api_key_here
BINANCE_API_SECRET=your_mainnet_api_secret_here
```

## 运行时参数

Makefile 会把 `SYMBOL` 和 `INTERVAL` 传给后端命令：

```bash
make start SYMBOL=BTCUSDT INTERVAL=30m
make start-web SYMBOL=BTCUSDT INTERVAL=30m
make web
```

`make start-web` 启动后端交易系统和 WebSocket 服务，默认后端端口是 `8000`。`make web` 启动 React 前端，默认访问地址是 `http://localhost:3000`。

## Agent 配置

Agent 角色、温度、启用状态等集中在：

```text
backend/src/vibe_trading/config/agent_config.py
```

当前核心角色包括：

| 阶段 | Agent |
| --- | --- |
| Phase 1 | TechnicalAnalyst、FundamentalAnalyst、NewsAnalyst、SentimentAnalyst |
| Phase 2 | BullResearcher、BearResearcher、ResearchManager |
| Phase 3 | AggressiveRiskAnalyst、NeutralRiskAnalyst、ConservativeRiskAnalyst |
| Phase 4 | Trader、PortfolioManager |

修改 Agent 行为时优先调整配置和 prompt，避免直接改通用执行框架。

## 数据库配置

默认使用 SQLite：

```env
DATABASE_URL=sqlite+aiosqlite:///./vibe_trading.db
```

当前主要持久化内容包括：

| 表 | 用途 |
| --- | --- |
| `klines` | K 线行情数据 |
| `bar_decision_journal` | 每根 K 线的 Agent 报告、阶段状态、最终决策和运行日志快照 |

SQLite 表会在系统启动时自动初始化。开发环境中如果数据库损坏，可停止服务后删除 `vibe_trading.db`，再重新启动系统。

## Web 监控配置

当前 Web 监控由两部分组成：

| 组件 | 默认地址 | 说明 |
| --- | --- | --- |
| FastAPI 后端 | `http://localhost:8000` | REST API 和 WebSocket |
| React 前端 | `http://localhost:3000` | Agent Arena 监控界面 |
| WebSocket | `ws://localhost:8000/ws` | 实时推送 K 线、Agent 状态、日志、决策 |

关键接口见 [API 文档](/guide/api)，界面功能见 [Web 监控](/guide/monitoring)。

## 日志配置

```env
LOG_LEVEL=INFO
# 可选：写入文件
# LOG_FILE=./vibe_trading.log
```

项目代码中应使用 `pi_logger`：

```python
from pi_logger import get_logger

logger = get_logger(__name__)
logger.info("message", tag="AgentName")
```

不要用标准库 `logging.getLogger()` 替代，因为当前项目日志调用依赖 `tag` 参数。

## 配置检查

最小检查流程：

```bash
# 确认 .env 存在
test -f .env && echo ".env ok"

# 启动一次 Paper Trading
make start SYMBOL=BTCUSDT INTERVAL=30m

# 如需 Web 监控，另开终端启动前端
make web
```

如果 LLM 调用失败，优先检查：

1. `LLM_MODEL` 是否存在于 `backend/src/pi_ai/llm.yaml`。
2. 该模型配置对应的 API Key 是否已经在 `.env` 中设置。
3. 供应商额度、网络和 endpoint 是否正常。

## 配置最佳实践

1. 不要提交 `.env` 或真实 API Key。
2. 开发和观察阶段使用 `TRADING_MODE=paper`。
3. 实盘前单独确认 Binance 主网 key、权限、IP 白名单和 `--execute` 行为。
4. 修改 Agent 配置后，先用较长周期 K 线观察完整决策链路。
5. 需要追溯问题时，优先查看 Web 的 K 线级追溯和 `bar_decision_journal`。

## 下一步

- 查看 [快速开始](/guide/quick-start) 启动系统
- 查看 [Web 监控](/guide/monitoring) 理解前端观测能力
- 查看 [API 文档](/guide/api) 对接 REST 和 WebSocket
