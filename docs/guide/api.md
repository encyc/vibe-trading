# API 文档

Vibe Trading 当前 Web API 主要服务于 React 监控前端：提供实时 WebSocket 推送、内存状态查询、K线级决策追溯和调试接口。

## 基础信息

- Base URL: `http://localhost:8000`
- WebSocket: `ws://localhost:8000/ws`
- Content-Type: `application/json`
- 当前版本没有启用 API Key 认证，默认用于本地开发和监控。

## REST API

### GET `/api/status`

获取 Web 后端当前状态。

```bash
curl http://localhost:8000/api/status
```

响应示例：

```json
{
  "connected_clients": 1,
  "total_klines": 100,
  "total_decisions": 3,
  "current_phase": "COMPLETED"
}
```

### GET `/api/klines`

获取当前内存中的 K线数据。

```bash
curl http://localhost:8000/api/klines
```

响应示例：

```json
{
  "klines": [
    {
      "time": "2026-04-28T10:00:00",
      "open_time_ms": 1777341600000,
      "symbol": "BTCUSDT",
      "interval": "30m",
      "open": 65000,
      "high": 65500,
      "low": 64800,
      "close": 65200,
      "volume": 1000
    }
  ]
}
```

### GET `/api/decisions`

获取当前内存中的决策记录。

```bash
curl http://localhost:8000/api/decisions
```

### GET `/api/logs`

获取最近日志。

```bash
curl http://localhost:8000/api/logs
```

### GET `/api/bar/{open_time_ms}`

按 K线开盘时间查询完整追溯记录。

```bash
curl "http://localhost:8000/api/bar/1777341600000?symbol=BTCUSDT&interval=30m"
```

响应示例：

```json
{
  "found": true,
  "bar": {
    "symbol": "BTCUSDT",
    "interval": "30m",
    "open_time_ms": 1777341600000,
    "bar_time": "2026-04-28T10:00:00",
    "kline": {},
    "phase_status": {
      "current": "COMPLETED",
      "ANALYZING": { "status": "completed", "duration": null }
    },
    "decision": {
      "index": 1,
      "time": "2026-04-28T10:00:00",
      "close": 65200,
      "decision": "HOLD",
      "rationale": "综合风险后保持观望"
    },
    "reports": {
      "analysts": {
        "technical": "技术分析报告..."
      }
    },
    "logs": [],
    "updated_at": "2026-04-28T10:05:00"
  }
}
```

如果没有追溯记录：

```json
{
  "found": false,
  "bar": null
}
```

### POST `/api/kline`

写入或广播一根 K线。通常由后端线程调用。

```bash
curl -X POST http://localhost:8000/api/kline \
  -H "Content-Type: application/json" \
  -d '{
    "time": "2026-04-28T10:00:00",
    "open_time_ms": 1777341600000,
    "symbol": "BTCUSDT",
    "interval": "30m",
    "open": 65000,
    "high": 65500,
    "low": 64800,
    "close": 65200,
    "volume": 1000
  }'
```

### POST `/api/decision`

写入最终决策，并归档到对应 K线 journal。

```bash
curl -X POST http://localhost:8000/api/decision \
  -H "Content-Type: application/json" \
  -d '{
    "index": 1,
    "time": "2026-04-28T10:00:00",
    "open_time_ms": 1777341600000,
    "symbol": "BTCUSDT",
    "interval": "30m",
    "close": 65200,
    "decision": "HOLD",
    "rationale": "风险收益比不足，保持观望"
  }'
```

### POST `/api/log`

写入一条 Runtime Log。

```bash
curl -X POST http://localhost:8000/api/log \
  -H "Content-Type: application/json" \
  -d '{
    "level": "info",
    "tag": "OnBar",
    "message": "开始处理K线",
    "open_time_ms": 1777341600000,
    "symbol": "BTCUSDT",
    "interval": "30m"
  }'
```

### POST `/api/phase`

更新当前阶段状态。

```bash
curl -X POST http://localhost:8000/api/phase \
  -H "Content-Type: application/json" \
  -d '{
    "phase": "ANALYZING",
    "status": "running",
    "open_time_ms": 1777341600000,
    "symbol": "BTCUSDT",
    "interval": "30m"
  }'
```

### POST `/api/report`

写入 Agent 报告。

```bash
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "Technical Analyst",
    "phase": "analysts",
    "content": "### 结论\n- 当前趋势偏多\n- 需要关注上方阻力",
    "open_time_ms": 1777341600000,
    "symbol": "BTCUSDT",
    "interval": "30m"
  }'
```

### POST `/api/reset`

清空 Web 内存状态。不会清空 SQLite 中的 `bar_decision_journal`。

```bash
curl -X POST http://localhost:8000/api/reset
```

### POST `/api/decision_tree`

广播决策树数据。当前主要用于前端扩展和调试。

## WebSocket API

### 连接

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
```

连接成功后，服务端会发送一条 `init` 消息，包含当前快照：

```json
{
  "type": "init",
  "timestamp": "2026-04-28T10:00:00",
  "data": {
    "klines": [],
    "indicators": {},
    "decisions": [],
    "logs": [],
    "phase_status": {},
    "agent_reports": {}
  }
}
```

### 消息类型

| 类型 | 说明 |
|------|------|
| `init` | 初始化快照 |
| `kline` | K线新增或更新 |
| `decision` | 最终交易决策 |
| `log` | Runtime Log |
| `phase` | 阶段状态 |
| `report` | Agent 报告 |
| `reset` | 状态重置 |
| `decision_tree` | 决策树数据 |

客户端可以发送文本 `ping`，服务端会返回 `pong`。

## 数据持久化

当前 Web 监控相关数据分为两类：

| 数据 | 存储位置 | 说明 |
|------|----------|------|
| K线历史 | SQLite `klines` 表 | 由 `KlineStorage` 管理 |
| K线决策追溯 | SQLite `bar_decision_journal` 表 | 保存每根K线的报告、日志、决策 |
| 当前 Web 快照 | 内存 | 供实时前端快速展示 |

## 注意事项

- API 面向本地监控，不是公开交易 API。
- `GET /api/bar/{open_time_ms}` 只有在该 K线被系统处理并写入 journal 后才会返回完整 Agent 报告。
- 如果前后端分开部署，需要设置前端环境变量 `VITE_API_BASE_URL` 和 `VITE_WS_URL`。

## 下一步

- 阅读 [Web监控](/guide/monitoring) 了解前端交互
- 阅读 [协作流程](/guide/workflow) 理解决策阶段
- 阅读 [配置说明](/guide/configuration) 配置 LLM 和交易参数
