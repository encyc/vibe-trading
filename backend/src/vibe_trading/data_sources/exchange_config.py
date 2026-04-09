"""
多交易所配置管理

支持不同交易所的配置，兼容现有的 BinanceConfig。
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any
import os


class ExchangeType(str, Enum):
    """交易所类型"""

    BINANCE = "binance"
    OKX = "okx"
    BYBIT = "bybit"


@dataclass
class ExchangeConfig:
    """交易所配置基类

    统一的交易所配置接口。
    """

    exchange_type: ExchangeType
    environment: str = "testnet"  # testnet 或 mainnet
    api_key: str = ""
    api_secret: str = ""
    enable_websocket: bool = True
    enable_rest: bool = True

    # 交易所特定配置
    ws_base_url: Optional[str] = None
    rest_base_url: Optional[str] = None

    def __post_init__(self):
        """初始化后处理，设置默认URL"""
        # 子类可以覆盖此方法来设置交易所特定的默认值
        pass

    @property
    def is_testnet(self) -> bool:
        """是否为测试网"""
        return self.environment == "testnet"

    @classmethod
    def from_env(cls, exchange: ExchangeType) -> "ExchangeConfig":
        """从环境变量创建配置

        Args:
            exchange: 交易所类型

        Returns:
            交易所配置对象
        """
        if exchange == ExchangeType.BINANCE:
            return BinanceExchangeConfig.from_env()

        # 其他交易所的配置
        # 后续扩展 OKX、Bybit 等
        raise ValueError(f"Unsupported exchange: {exchange}")


@dataclass
class BinanceExchangeConfig(ExchangeConfig):
    """Binance 交易所配置

    兼容现有的 BinanceConfig，同时实现新的 ExchangeConfig 接口。
    """

    ws_base_url: str = ""
    rest_base_url: str = ""

    def __post_init__(self):
        """设置 Binance 特定的默认URL"""
        # 根据环境设置默认URL
        if not self.ws_base_url or not self.rest_base_url:
            if self.environment == "testnet":
                self.ws_base_url = "wss://stream.binancefuture.com"
                self.rest_base_url = "https://testnet.binancefuture.com"
            else:
                self.ws_base_url = "wss://fstream.binance.com"
                self.rest_base_url = "https://fapi.binance.com"

    @classmethod
    def from_env(cls) -> "BinanceExchangeConfig":
        """从环境变量创建 Binance 配置

        Returns:
            BinanceExchangeConfig 实例
        """
        # 检测环境：如果主网有配置则使用主网，否则使用测试网
        has_mainnet_key = bool(os.getenv("BINANCE_API_KEY"))
        environment = "mainnet" if has_mainnet_key else "testnet"

        if environment == "testnet":
            api_key = os.getenv("BINANCE_TESTNET_API_KEY", "")
            api_secret = os.getenv("BINANCE_TESTNET_API_SECRET", "")
        else:
            api_key = os.getenv("BINANCE_API_KEY", "")
            api_secret = os.getenv("BINANCE_API_SECRET", "")

        return cls(
            exchange_type=ExchangeType.BINANCE,
            environment=environment,
            api_key=api_key,
            api_secret=api_secret,
        )

    def to_binance_config(self):
        """转换为现有的 BinanceConfig 对象

        Returns:
            兼容的 BinanceConfig 对象
        """
        from vibe_trading.config.binance_config import BinanceConfig, BinanceEnvironment

        env = BinanceEnvironment.TESTNET if self.is_testnet else BinanceEnvironment.MAINNET

        return BinanceConfig(
            environment=env,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )


# 配置缓存
_exchange_configs: dict[ExchangeType, ExchangeConfig] = {}


def get_exchange_config(exchange: ExchangeType) -> ExchangeConfig:
    """获取交易所配置（带缓存）

    Args:
        exchange: 交易所类型

    Returns:
        交易所配置对象
    """
    if exchange not in _exchange_configs:
        _exchange_configs[exchange] = ExchangeConfig.from_env(exchange)

    return _exchange_configs[exchange]


def clear_config_cache():
    """清除配置缓存"""
    _exchange_configs.clear()
