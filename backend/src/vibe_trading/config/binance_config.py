"""
Binance API 配置
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import os


class BinanceEnvironment(str, Enum):
    """Binance 环境"""
    TESTNET = "testnet"  # 测试网
    MAINNET = "mainnet"  # 主网


@dataclass
class BinanceConfig:
    """Binance API 配置"""

    environment: BinanceEnvironment = BinanceEnvironment.TESTNET

    # API 密钥
    api_key: str = ""
    api_secret: str = ""

    # WebSocket 配置
    ws_base_url: str = ""
    rest_base_url: str = ""

    def __post_init__(self):
        """初始化后处理，设置默认值"""
        if self.environment == BinanceEnvironment.TESTNET:
            self.ws_base_url = "wss://stream.binancefuture.com"
            self.rest_base_url = "https://testnet.binancefuture.com"
        else:
            self.ws_base_url = "wss://fstream.binance.com"
            self.rest_base_url = "https://fapi.binance.com"

    @classmethod
    def from_env(cls, environment: BinanceEnvironment = BinanceEnvironment.TESTNET) -> "BinanceConfig":
        """从环境变量创建配置"""
        if environment == BinanceEnvironment.TESTNET:
            api_key = os.getenv("BINANCE_TESTNET_API_KEY", "")
            api_secret = os.getenv("BINANCE_TESTNET_API_SECRET", "")
        else:
            api_key = os.getenv("BINANCE_API_KEY", "")
            api_secret = os.getenv("BINANCE_API_SECRET", "")

        return cls(
            environment=environment,
            api_key=api_key,
            api_secret=api_secret,
        )

    @property
    def is_testnet(self) -> bool:
        """是否为测试网"""
        return self.environment == BinanceEnvironment.TESTNET

    @property
    def ws_kline_template(self) -> str:
        """K线 WebSocket 模板"""
        return f"{self.ws_base_url}/ws/{{symbol}}@kline_{{interval}}"

    @property
    def ws_user_data_stream(self) -> str:
        """用户数据流 WebSocket 地址"""
        return f"{self.ws_base_url}/ws"
