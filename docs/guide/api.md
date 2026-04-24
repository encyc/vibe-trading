# API 文档

Vibe Trading 提供 RESTful API 和 WebSocket API，方便集成到外部应用。

## RESTful API

### 基础信息

- **Base URL**: `http://localhost:8000`
- **Content-Type**: `application/json`
- **认证**: API Key（可选）

### 端点列表

#### 1. 系统状态

**GET /api/status**

获取系统运行状态

```bash
curl http://localhost:8000/api/status
```

**响应示例**:
```json
{
  "status": "running",
  "version": "1.0.0",
  "uptime": 3600,
  "active_agents": 12,
  "last_decision": {
    "decision": "BUY",
    "timestamp": "2024-01-01T12:00:00Z",
    "symbol": "BTCUSDT"
  }
}
```

#### 2. 市场数据

**GET /api/market/{symbol}**

获取指定交易对的市场数据

```bash
curl http://localhost:8000/api/market/BTCUSDT
```

**响应示例**:
```json
{
  "symbol": "BTCUSDT",
  "price": 65000.50,
  "change_24h": 2.5,
  "volume_24h": 1000000,
  "high_24h": 66000,
  "low_24h": 63000,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

**GET /api/market/{symbol}/klines**

获取K线数据

```bash
curl "http://localhost:8000/api/market/BTCUSDT/klines?interval=1h&limit=100"
```

**参数**:
- `interval`: K线间隔 (1m, 5m, 15m, 30m, 1h, 4h, 1d)
- `limit`: 数量 (默认100，最大1000)

**响应示例**:
```json
{
  "symbol": "BTCUSDT",
  "interval": "1h",
  "klines": [
    {
      "timestamp": 1704110400000,
      "open": 65000,
      "high": 65500,
      "low": 64800,
      "close": 65200,
      "volume": 1000
    }
  ]
}
```

#### 3. 决策查询

**GET /api/decisions**

获取决策历史

```bash
curl "http://localhost:8000/api/decisions?symbol=BTCUSDT&limit=10"
```

**参数**:
- `symbol`: 交易对（可选）
- `limit`: 数量（默认10）
- `offset`: 偏移量（默认0）

**响应示例**:
```json
{
  "total": 100,
  "decisions": [
    {
      "id": "decision_001",
      "symbol": "BTCUSDT",
      "decision": "BUY",
      "quantity": 0.2,
      "price": 65000,
      "confidence": 0.75,
      "timestamp": "2024-01-01T12:00:00Z",
      "outcome": {
        "pnl": 500,
        "return": 0.05
      }
    }
  ]
}
```

**GET /api/decisions/{id}**

获取特定决策详情

```bash
curl http://localhost:8000/api/decisions/decision_001
```

**响应示例**:
```json
{
  "id": "decision_001",
  "symbol": "BTCUSDT",
  "decision": "BUY",
  "quantity": 0.2,
  "price": 65000,
  "confidence": 0.75,
  "timestamp": "2024-01-01T12:00:00Z",
  "rationale": "技术面和基本面支持上涨",
  "agent_outputs": {
    "technical": {...},
    "fundamental": {...}
  }
}
```

#### 4. Agent 状态

**GET /api/agents**

获取所有 Agent 状态

```bash
curl http://localhost:8000/api/agents
```

**响应示例**:
```json
{
  "agents": [
    {
      "name": "TechnicalAnalyst",
      "status": "idle",
      "last_execution": "2024-01-01T12:00:00Z",
      "success_rate": 0.85
    }
  ]
}
```

**GET /api/agents/{name}**

获取特定 Agent 状态

```bash
curl http://localhost:8000/api/agents/TechnicalAnalyst
```

#### 5. 配置管理

**GET /api/config**

获取当前配置

```bash
curl http://localhost:8000/api/config
```

**响应示例**:
```json
{
  "trading_mode": "paper",
  "default_symbol": "BTCUSDT",
  "default_interval": "30m",
  "max_position_size": 0.3
}
```

**PUT /api/config**

更新配置

```bash
curl -X PUT http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "max_position_size": 0.5
  }'
```

## WebSocket API

### 连接

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
```

### 消息类型

#### 1. K线数据

**客户端订阅**:
```javascript
ws.send(JSON.stringify({
  type: "subscribe",
  channel: "kline",
  symbol: "BTCUSDT",
  interval: "1h"
}));
```

**服务器推送**:
```json
{
  "type": "kline",
  "data": {
    "symbol": "BTCUSDT",
    "interval": "1h",
    "open": 65000,
    "high": 65500,
    "low": 64800,
    "close": 65200,
    "volume": 1000,
    "timestamp": "2024-01-01T12:00:00Z"
  }
}
```

#### 2. 决策更新

**客户端订阅**:
```javascript
ws.send(JSON.stringify({
  type: "subscribe",
  channel: "decision"
}));
```

**服务器推送**:
```json
{
  "type": "decision",
  "data": {
    "id": "decision_001",
    "symbol": "BTCUSDT",
    "decision": "BUY",
    "quantity": 0.2,
    "price": 65000,
    "confidence": 0.75,
    "timestamp": "2024-01-01T12:00:00Z"
  }
}
```

#### 3. Agent 状态

**客户端订阅**:
```javascript
ws.send(JSON.stringify({
  type: "subscribe",
  channel": "agent_status"
}));
```

**服务器推送**:
```json
{
  "type": "agent_status",
  "data": {
    "agent": "TechnicalAnalyst",
    "status": "running",
    "phase": "analysts",
    "progress": 0.5
  }
}
```

#### 4. 日志消息

**客户端订阅**:
```javascript
ws.send(JSON.stringify({
  type: "subscribe",
  channel": "log"
}));
```

**服务器推送**:
```json
{
  "type": "log",
  "data": {
    "level": "INFO",
    "tag": "TRADING",
    "message": "新K线到达，开始分析",
    "timestamp": "2024-01-01T12:00:00Z"
  }
}
```

## 错误处理

### 错误格式

```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "Invalid symbol parameter",
    "details": "Symbol must be a valid trading pair"
  }
}
```

### 错误代码

| 代码 | 说明 |
|------|------|
| INVALID_PARAMETER | 参数无效 |
| UNAUTHORIZED | 未授权 |
| NOT_FOUND | 资源不存在 |
| RATE_LIMIT_EXCEEDED | 超出速率限制 |
| INTERNAL_ERROR | 内部错误 |

## 认证

### API Key 认证

在请求头中包含 API Key：

```bash
curl http://localhost:8000/api/status \
  -H "X-API-Key: your_api_key_here"
```

### 生成 API Key

```python
from vibe_trading.config.settings import get_settings

settings = get_settings()
api_key = settings.generate_api_key()
print(api_key)
```

## Python SDK

### 安装

```bash
pip install vibe-trading-sdk
```

### 使用示例

```python
from vibe_trading_sdk import VibeTradingClient

# 初始化客户端
client = VibeTradingClient(
    base_url="http://localhost:8000",
    api_key="your_api_key"
)

# 获取系统状态
status = client.get_status()
print(status)

# 获取市场数据
market_data = client.get_market_data("BTCUSDT")
print(market_data)

# 获取决策历史
decisions = client.get_decisions(symbol="BTCUSDT", limit=10)
print(decisions)
```

## JavaScript SDK

### 安装

```bash
npm install vibe-trading-sdk
```

### 使用示例

```javascript
import { VibeTradingClient } from 'vibe-trading-sdk';

const client = new VibeTradingClient({
  baseUrl: 'http://localhost:8000',
  apiKey: 'your_api_key'
});

// 获取系统状态
const status = await client.getStatus();
console.log(status);

// 获取市场数据
const marketData = await client.getMarketData('BTCUSDT');
console.log(marketData);

// WebSocket 连接
client.connectWebSocket();
client.subscribe('kline', 'BTCUSDT', '1h');
client.on('kline', (data) => {
  console.log('New kline:', data);
});
```

## 速率限制

### 限制规则

- 每分钟最多 100 个请求
- 每小时最多 1000 个请求
- 每天最多 10000 个请求

### 响应头

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704110400
```

## 最佳实践

1. **使用 WebSocket**：实时数据使用 WebSocket 而非轮询
2. **缓存数据**：缓存不常变化的数据
3. **错误重试**：实现指数退避重试机制
4. **监控限流**：监控速率限制头部
5. **异步处理**：使用异步客户端提高性能

## 故障排除

### 连接失败

检查：
1. 服务是否启动
2. 端口是否正确
3. 防火墙设置

### 认证失败

检查：
1. API Key 是否正确
2. API Key 是否过期
3. 权限是否足够

### 数据异常

检查：
1. 参数格式是否正确
2. 数据源是否可用
3. 查看错误日志

## 下一步

- 了解 [配置说明](/guide/configuration) 配置 API
- 学习 [自定义Agent](/guide/custom-agent) 扩展功能