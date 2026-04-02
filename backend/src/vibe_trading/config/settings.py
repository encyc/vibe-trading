"""
全局配置管理

使用单例模式管理应用配置。
"""
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from dotenv import load_dotenv

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

    # Agent 配置
    debate_rounds: int = 2  # 辩论轮数
    enable_memory: bool = True  # 是否启用记忆系统
    memory_top_k: int = 3  # 记忆检索数量

    # LLM 配置 - 使用 pi_ai/config.py 中的 llm.yaml
    llm_config_name: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "glm_4_7"))

    # 日志配置
    log_level: LogLevel = LogLevel.INFO
    log_file: Optional[str] = None

    # 外部 API 配置
    cryptocmp_api_key: Optional[str] = field(default_factory=lambda: os.getenv("CRYPTOCOMPARE_API_KEY"))

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
            debate_rounds=int(os.getenv("DEBATE_ROUNDS", "2")),
            enable_memory=os.getenv("ENABLE_MEMORY", "true").lower() == "true",
            memory_top_k=int(os.getenv("MEMORY_TOP_K", "3")),
            llm_config_name=os.getenv("LLM_MODEL", "glm_4_7"),
            log_level=LogLevel(os.getenv("LOG_LEVEL", "INFO")),
            log_file=os.getenv("LOG_FILE"),
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./vibe_trading.db"),
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
