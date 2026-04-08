# 配置说明

本文档详细说明 Vibe Trading 系统的各项配置。

## 环境变量配置

### .env 文件

在 `backend/.env` 文件中配置以下参数：

```env
# ==================== Binance API 配置 ====================
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=false  # 使用测试网

# ==================== LLM 配置 ====================
LLM_PROVIDER=openai  # openai | anthropic | azure | local
LLM_API_KEY=your_llm_api_key_here
LLM_MODEL=gpt-4
LLM_TEMPERATURE=0.7  # 0.0-1.0，越高越随机
LLM_MAX_TOKENS=2000

# ==================== Azure OpenAI 配置（可选）====================
AZURE_OPENAI_API_KEY=your_azure_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4

# ==================== 数据库配置 ====================
DATABASE_URL=sqlite:///vibe_trading.db
# 或使用 PostgreSQL:
# DATABASE_URL=postgresql://user:password@localhost:5432/vibe_trading

# ==================== 日志配置 ====================
LOG_LEVEL=INFO  # DEBUG | INFO | WARNING | ERROR
LOG_FILE=logs/trading.log
JSON_LOGS=false  # 是否输出JSON格式日志

# ==================== 交易配置 ====================
TRADING_MODE=paper  # paper | live
DEFAULT_SYMBOL=BTCUSDT
DEFAULT_INTERVAL=30m
MAX_POSITION_SIZE=0.3  # 最大仓位比例
MIN_POSITION_SIZE=0.01  # 最小仓位比例

# ==================== 风控配置 ====================
ENABLE_EMERGENCY_STOP=true
EMERGENCY_STOP_THRESHOLD=0.1  # 10%亏损时紧急止损
MAX_DAILY_LOSS=0.05  # 最大日亏损 5%
MAX_DRAWDOWN=0.2  # 最大回撤 20%

# ==================== 系统配置 ====================
WORKER_THREADS=4  # 工作线程数
QUEUE_SIZE=1000  # 消息队列大小
CACHE_TTL=3600  # 缓存过期时间（秒）

# ==================== Web 监控配置 ====================
WEB_HOST=0.0.0.0
WEB_PORT=8000
WEBSOCKET_ENABLED=true

# ==================== 性能配置 ====================
KLINE_CACHE_SIZE=1000  # K线缓存数量
INDICATOR_CACHE_SIZE=100  # 指标缓存数量
ENABLE_RATE_LIMIT=true  # 启用速率限制
```

## Agent 配置

### Agent 配置文件

在 `backend/src/vibe_trading/config/agent_config.py` 中配置：

```python
class AgentConfig:
    name: str
    role: AgentRole
    temperature: float
    enabled: bool = True
    max_retries: int = 3
    timeout: int = 30

# 示例配置
TECHNICAL_ANALYST_CONFIG = AgentConfig(
    name="TechnicalAnalyst",
    role=AgentRole.ANALYST,
    temperature=0.3,  # 较低温度，更确定性
    enabled=True
)

BULL_RESEARCHER_CONFIG = AgentConfig(
    name="BullResearcher",
    role=AgentRole.RESEARCHER,
    temperature=0.7,  # 较高温度，更有创造性
    enabled=True
)
```

### 启用/禁用 Agent

```python
# 在 agent_config.py 中修改
AGENTS_ENABLED = {
    "technical_analyst": True,
    "fundamental_analyst": True,
    "news_analyst": True,
    "sentiment_analyst": True,
    "bull_researcher": True,
    "bear_researcher": True,
    "research_manager": True,
    "aggressive_risk": True,
    "neutral_risk": True,
    "conservative_risk": True,
    "trader": True,
    "portfolio_manager": True,
}
```

## 风控配置

### 风控参数

```python
class RiskConfig:
    # 仓位限制
    max_position_size: float = 0.3  # 最大30%仓位
    min_position_size: float = 0.01  # 最小1%仓位
    
    # 止损止盈
    default_stop_loss: float = 0.02  # 默认2%止损
    default_take_profit: float = 0.08  # 默认8%止盈
    
    # 风险限制
    max_daily_loss: float = 0.05  # 最大日亏损5%
    max_drawdown: float = 0.2  # 最大回撤20%
    
    # VaR 配置
    var_confidence_level: float = 0.95  # 95%置信度
    var_time_horizon: int = 1  # 1天时间跨度
    
    # 凯利公式
    kelly_fallback: float = 0.1  # 凯利公式失效时的默认值
    max_kelly_fraction: float = 0.25  # 最大凯利分数
```

## 交易配置

### 交易策略配置

```python
class TradingConfig:
    # 默认参数
    symbol: str = "BTCUSDT"
    interval: str = "30m"
    
    # 执行策略
    execution_strategy: str = "limit"  # limit | market | twap
    
    # 订单类型
    default_order_type: str = "LIMIT"
    
    # 超时设置
    order_timeout: int = 60  # 秒
    max_retry: int = 3
```

## 回测配置

### 回测参数

```python
class BacktestConfig:
    symbol: str
    interval: str
    start_time: datetime
    end_time: datetime
    initial_balance: float = 10000.0
    
    # LLM 模式
    llm_mode: LLMMode = LLMMode.SIMULATED
    
    # 手续费
    maker_fee: float = 0.0002  # 0.02%
    taker_fee: float = 0.0004  # 0.04%
    
    # 滑点
    slippage: float = 0.0005  # 0.05%
    
    # 缓存
    enable_cache: bool = True
    cache_ttl: int = 3600
```

## Web 监控配置

### Web 服务器配置

```python
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # WebSocket
    websocket_enabled: bool = True
    websocket_path: str = "/ws"
    
    # 静态文件
    static_dir: str = "frontend"
    
    # 认证（可选）
    enable_auth: bool = False
    api_key: str = ""
```

## 数据源配置

### Binance API 配置

```python
class BinanceConfig:
    api_key: str
    api_secret: str
    testnet: bool = False
    
    # 连接池
    max_connections: int = 10
    timeout: int = 30
    
    # 速率限制
    rate_limit: int = 1200  # 每分钟请求数
    rate_limit_window: int = 60  # 秒
```

## 日志配置

### 日志配置

```python
class LoggingConfig:
    level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 文件日志
    enable_file_logging: bool = True
    log_file: str = "logs/trading.log"
    max_bytes: int = 10485760  # 10MB
    backup_count: int = 5
    
    # JSON 日志
    json_output: bool = False
```

## 性能配置

### 性能优化配置

```python
class PerformanceConfig:
    # 线程配置
    worker_threads: int = 4
    max_tasks: int = 1000
    
    # 队列配置
    queue_size: int = 1000
    batch_size: int = 10
    
    # 缓存配置
    kline_cache_size: int = 1000
    indicator_cache_size: int = 100
    memory_cache_size: int = 10000
    
    # 连接池
    db_pool_size: int = 10
    max_overflow: int = 20
```

## 验证配置

### 检查配置

```python
from vibe_trading.config.settings import get_settings

settings = get_settings()

# 验证必需的配置
if not settings.binance_api_key:
    raise ValueError("BINANCE_API_KEY is required")

if not settings.llm_api_key:
    raise ValueError("LLM_API_KEY is required")

# 打印配置
print(f"Trading Mode: {settings.trading_mode}")
print(f"Symbol: {settings.default_symbol}")
print(f"Interval: {settings.default_interval}")
```

### 配置验证脚本

```bash
# 验证配置文件
PYTHONPATH=backend/src uv run -- vibe-trade config validate

# 生成配置报告
PYTHONPATH=backend/src uv run -- vibe-trade config report
```

## 动态配置

### 运行时修改配置

```python
from vibe_trading.config.settings import get_settings

settings = get_settings()

# 修改配置
settings.trading_mode = "live"
settings.max_position_size = 0.5

# 保存配置
settings.save()
```

### 环境变量覆盖

```bash
# 运行时覆盖环境变量
BINANCE_API_KEY=new_key \
PYTHONPATH=backend/src \
uv run -- vibe-trade start BTCUSDT
```

## 配置最佳实践

1. **使用环境变量**：敏感信息（API密钥）使用环境变量
2. **版本控制**：不要提交 `.env` 文件到版本控制
3. **配置分离**：开发、测试、生产环境使用不同配置
4. **文档记录**：记录配置变更和原因
5. **定期审查**：定期检查和优化配置

## 故障排除

### 配置文件未加载

**问题**：修改配置后未生效

**解决方案**：
1. 确认 `.env` 文件在正确位置
2. 重启应用程序
3. 检查环境变量语法

### API 密钥无效

**问题**：API 密钥错误导致无法连接

**解决方案**：
1. 检查 API 密钥是否正确
2. 确认 API 密钥有足够权限
3. 测试网络连接

### LLM 配置错误

**问题**：LLM 调用失败

**解决方案**：
1. 确认 LLM API 密钥有效
2. 检查模型名称是否正确
3. 验证 API 额度充足

## 下一步

- 了解 [记忆系统](/guide/memory) 配置
- 学习 [自定义Agent](/guide/custom-agent) 添加功能
- 查看 [API文档](/guide/api) 集成配置