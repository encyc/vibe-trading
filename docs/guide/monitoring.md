# Web 监控

Vibe Trading 的 Web 监控界面用于观察 Paper Trading 实盘数据流、Agent 协作过程、Runtime Log 和每根 K线的历史追溯记录。

当前版本采用 React + Vite + lightweight-charts，视觉上更接近 nof1.ai 的多模型交易竞技场：白底黑线、高密度 ticker、左侧主图表、右侧 Agent Monitor、底部 Agent 状态卡。

## 启动方式

推荐使用两个终端：

```bash
# 终端 1：启动交易系统 + WebSocket 后端
make start-web SYMBOL=BTCUSDT INTERVAL=30m

# 终端 2：启动 React 前端
make web
```

访问地址：

```text
Frontend:  http://localhost:3000
Backend:   http://localhost:8000
WebSocket: ws://localhost:8000/ws
```

`INTERVAL` 支持常见 Binance K线周期，例如 `1m`、`5m`、`15m`、`30m`、`1h`、`4h`、`1d`。

## 界面结构

```text
┌─────────────────────────────────────────────────────────────┐
│ TopBar: 品牌、导航、连接状态、行情 ticker                    │
├──────────────────────────────────┬──────────────────────────┤
│ Chart Zone                       │ Agent Monitor             │
│ - K线图                          │ - 分阶段 Agent 报告       │
│ - 决策标记                       ├──────────────────────────┤
│ - 底部 Agent 状态卡              │ Current Candle & Decision │
│                                  ├──────────────────────────┤
│                                  │ Runtime Log               │
└──────────────────────────────────┴──────────────────────────┘
```

## 核心功能

### 1. 实时 K线和决策标记

左侧图表显示实时 K线、均线和 BUY/SELL 决策标记。前端通过 WebSocket 接收 `kline` 和 `decision` 消息，并使用 `lightweight-charts` 渲染。

### 2. K线级追溯

点击任意历史 K线后，右侧面板会查询这根 K线的追溯记录：

```http
GET /api/bar/{open_time_ms}?symbol=BTCUSDT&interval=30m
```

返回内容包括：

- K线 OHLCV
- 阶段状态
- Agent 报告
- 最终决策
- Runtime Log

这些数据来自后端的 `bar_decision_journal` 表，主键是 `symbol + interval + open_time_ms`。

### 3. Agent Monitor

Agent Monitor 按协作阶段展示 Agent 输出：

- Phase 1: Technical / Fundamental / News / Sentiment Analysts
- Phase 2: Bull / Bear Researchers + Research Manager
- Phase 3: Aggressive / Neutral / Conservative Risk Analysts
- Phase 4: Trader
- Final: Portfolio Manager

每个 Agent 卡片默认显示紧凑预览。点击某个 Agent 后，该报告会展开；点击其他 Agent 时，之前展开的卡片会自动收起。Agent 报告支持基础 Markdown 渲染，包括标题、列表、粗体、行内代码和代码块。

### 4. Runtime Log

Runtime Log 会显示 Web 后端收到的日志事件。在 `make start-web` 模式下，后端会镜像同进程的 stdout/stderr，因此 terminal 中的 `pi_logger`、标准库 `logging`、`print()` 输出和错误栈也会同步到 Web。

注意：如果你单独启动 `make web-backend`，再在另一个进程里启动交易系统，两个进程的 stdout 不互通，Runtime Log 只能显示主动通过 API 推送的日志。

### 5. 拖拽和调整大小

右侧三个模块支持：

- 拖拽排序
- 垂直调整高度
- 主图和右侧区域之间的横向调整
- 布局自动保存到浏览器 localStorage

## REST API

常用接口：

```bash
# 系统状态
curl http://localhost:8000/api/status

# 当前内存中的 K线
curl http://localhost:8000/api/klines

# 当前内存中的决策
curl http://localhost:8000/api/decisions

# 最近日志
curl http://localhost:8000/api/logs

# 查询某根 K线追溯
curl "http://localhost:8000/api/bar/1710000000000?symbol=BTCUSDT&interval=30m"
```

## WebSocket 消息

前端连接：

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
```

服务器会推送这些消息类型：

| 类型 | 说明 |
|------|------|
| `init` | 初始化快照，包含 K线、指标、决策、日志和 Agent 报告 |
| `kline` | 新 K线或当前 K线更新 |
| `decision` | 最终交易决策 |
| `log` | Runtime Log 新行 |
| `phase` | 当前阶段状态 |
| `report` | Agent 报告 |
| `reset` | 前端状态重置 |
| `decision_tree` | 决策树数据 |

客户端会发送 `ping` 心跳，后端返回 `pong`。

## 故障排查

### 前端显示离线

1. 确认后端已启动：`curl http://localhost:8000/api/status`
2. 确认前端配置的 WebSocket 地址是 `ws://localhost:8000/ws`
3. 查看浏览器控制台是否有连接错误

### 图表没有数据

1. 确认 `make start-web` 正在运行
2. 检查 terminal 是否订阅了正确的 `SYMBOL` 和 `INTERVAL`
3. 等待历史 K线加载完成

### 点击历史 K线没有 Agent 报告

历史 K线只有在系统处理过该根 K线并写入 `bar_decision_journal` 后，才会有完整追溯记录。只从 Binance 加载的历史 OHLCV 不会自动生成 Agent 报告。

## 下一步

- 阅读 [API文档](/guide/api) 了解完整接口
- 阅读 [协作流程](/guide/workflow) 理解决策阶段
- 阅读 [配置说明](/guide/configuration) 调整模型和交易参数
