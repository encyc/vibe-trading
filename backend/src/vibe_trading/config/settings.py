"""
全局配置管理

使用单例模式管理应用配置。
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from dotenv import load_dotenv

# 尝试从项目根目录加载 .env 文件
# settings.py 在 backend/src/vibe_trading/config/
# 项目根目录在往上 5 级
_env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)
else:
    # 回退到默认加载方式
    load_dotenv()


class TradingMode(str, Enum):
    """交易模式"""
    PAPER = "paper"  # 模拟交易
    LIVE = "live"    # 实盘交易


class LogLevel(str, Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class Settings:
    """全局配置"""

    # 基础配置
    project_name: str = "vibe-trading"
    version: str = "0.1.0"
    debug: bool = False

    # 交易配置
    trading_mode: TradingMode = TradingMode.PAPER
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    interval: str = "30m"  # K线间隔

    # 风控配置
    max_position_size: float = 0.1  # 单个交易对最大仓位 (USDT)
    max_total_position: float = 0.3  # 总最大仓位
    stop_loss_pct: float = 0.02  # 止损百分比
    take_profit_pct: float = 0.05  # 止盈百分比
    leverage: int = 5  # 杠杆倍数
    execution_max_single_order_notional: float = 100.0
    execution_max_total_exposure: float = 300.0
    execution_max_margin_fraction: float = 0.5
    execution_position_mode: str = "hedge"

    # Agent 配置
    debate_rounds: int = 2  # 辩论轮数
    enable_memory: bool = True  # 是否启用记忆系统
    memory_top_k: int = 3  # 记忆检索数量
    memory_storage_path: str = "./data/memory_storage.pkl"  # 反思记忆持久化路径
    reflection_benchmark_symbol: str = "BTCUSDT"  # alpha 计算的基准交易对
    reflection_maturation_bars: int = 12  # 决策快照多少根 bar 后回看评估

    # LLM 配置 - 使用 vibe_trading/config/llm_config.py 加载的 llm.yaml
    llm_config_name: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "glm_5_3_flash"))

    # 日志配置
    log_level: LogLevel = LogLevel.INFO
    log_file: Optional[str] = None
    enable_file_logging: bool = True  # 是否启用文件日志记录

    # 外部 API 配置
    binance_testnet_api_key: str = field(default_factory=lambda: os.getenv("BINANCE_TESTNET_API_KEY", ""))
    binance_testnet_api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_TESTNET_API_SECRET", ""))
    binance_api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
    binance_api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_API_SECRET", ""))
    okx_api_key: str = field(default_factory=lambda: os.getenv("OKX_API_KEY", ""))
    okx_secret_key: str = field(default_factory=lambda: os.getenv("OKX_SECRET_KEY", ""))
    okx_passphrase: str = field(default_factory=lambda: os.getenv("OKX_PASSPHRASE", ""))
    okx_demo_trading: bool = field(default_factory=lambda: os.getenv("OKX_DEMO_TRADING", "false").lower() == "true")
    cryptocmp_api_key: Optional[str] = field(default_factory=lambda: os.getenv("CRYPTOCOMPARE_API_KEY"))
    lunarcrush_api_key: Optional[str] = field(default_factory=lambda: os.getenv("LUNARCRUSH_API_KEY"))

    # 数据库配置
    database_url: str = "sqlite+aiosqlite:///./vibe_trading.db"

    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量创建配置"""
        return cls(
            debug=os.getenv("DEBUG", "false").lower() == "true",
            trading_mode=TradingMode(os.getenv("TRADING_MODE", "paper")),
            symbols=os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT").split(","),
            interval=os.getenv("INTERVAL", "30m"),
            max_position_size=float(os.getenv("MAX_POSITION_SIZE", "0.1")),
            max_total_position=float(os.getenv("MAX_TOTAL_POSITION", "0.3")),
            stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "0.02")),
            take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "0.05")),
            leverage=int(os.getenv("LEVERAGE", "5")),
            execution_max_single_order_notional=float(os.getenv("EXECUTION_MAX_SINGLE_ORDER_NOTIONAL", "100")),
            execution_max_total_exposure=float(os.getenv("EXECUTION_MAX_TOTAL_EXPOSURE", "300")),
            execution_max_margin_fraction=float(os.getenv("EXECUTION_MAX_MARGIN_FRACTION", "0.5")),
            execution_position_mode=os.getenv("EXECUTION_POSITION_MODE", "hedge"),
            debate_rounds=int(os.getenv("DEBATE_ROUNDS", "2")),
            enable_memory=os.getenv("ENABLE_MEMORY", "true").lower() == "true",
            memory_top_k=int(os.getenv("MEMORY_TOP_K", "3")),
            memory_storage_path=os.getenv("MEMORY_STORAGE_PATH", "./data/memory_storage.pkl"),
            reflection_benchmark_symbol=os.getenv("REFLECTION_BENCHMARK_SYMBOL", "BTCUSDT"),
            reflection_maturation_bars=int(os.getenv("REFLECTION_MATURATION_BARS", "12")),
            llm_config_name=os.getenv("LLM_MODEL", "glm_5_3_flash"),
            log_level=LogLevel(os.getenv("LOG_LEVEL", "INFO")),
            log_file=os.getenv("LOG_FILE"),
            enable_file_logging=os.getenv("ENABLE_FILE_LOGGING", "true").lower() == "true",
            binance_testnet_api_key=os.getenv("BINANCE_TESTNET_API_KEY", ""),
            binance_testnet_api_secret=os.getenv("BINANCE_TESTNET_API_SECRET", ""),
            binance_api_key=os.getenv("BINANCE_API_KEY", ""),
            binance_api_secret=os.getenv("BINANCE_API_SECRET", ""),
            okx_api_key=os.getenv("OKX_API_KEY", ""),
            okx_secret_key=os.getenv("OKX_SECRET_KEY", ""),
            okx_passphrase=os.getenv("OKX_PASSPHRASE", ""),
            okx_demo_trading=os.getenv("OKX_DEMO_TRADING", "false").lower() == "true",
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./vibe_trading.db"),
            cryptocmp_api_key=os.getenv("CRYPTOCOMPARE_API_KEY"),
            lunarcrush_api_key=os.getenv("LUNARCRUSH_API_KEY"),
        )


# 单例实例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局配置单例"""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def set_settings(settings: Settings) -> None:
    """设置全局配置"""
    global _settings
    _settings = settings
