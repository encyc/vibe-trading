"""
Provider 工厂

管理交易所数据提供者的创建和生命周期。
"""
import logging
from typing import Optional, Dict

from .base import ExchangeProvider
from .registry import ProviderRegistry
from ..exchange_config import ExchangeType, get_exchange_config


logger = logging.getLogger(__name__)


class ProviderFactory:
    """Provider 工厂

    负责创建、缓存和管理交易所数据提供者实例。
    """

    # 缓存已创建的 Provider 实例
    _instances: Dict[str, ExchangeProvider] = {}

    @classmethod
    async def create_provider(
        cls,
        exchange: str,
        config: Optional[object] = None,
    ) -> ExchangeProvider:
        """创建Provider实例

        Args:
            exchange: 交易所名称（如 "binance", "okx"）
            config: 可选的配置对象。如果为None，则从环境变量加载

        Returns:
            ExchangeProvider 实例

        Raises:
            ValueError: 如果交易所不存在
        """
        # 如果已存在实例，直接返回
        if exchange in cls._instances:
            logger.debug(f"Returning cached {exchange} provider")
            return cls._instances[exchange]

        # 获取Provider类
        provider_class = ProviderRegistry.get(exchange)
        if not provider_class:
            raise ValueError(f"Unknown exchange: {exchange}. Available: {ProviderRegistry.list_providers()}")

        # 获取配置（如果未提供）
        if config is None:
            exchange_type = ExchangeType(exchange)
            config = get_exchange_config(exchange_type)

        # 创建实例
        logger.info(f"Creating {exchange} provider...")
        provider = provider_class(config)

        # 建立连接
        try:
            await provider.connect()
            logger.info(f"{exchange} provider connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect {exchange} provider: {e}")
            # 即使连接失败也缓存实例，以便重试
            pass

        # 缓存实例
        cls._instances[exchange] = provider

        return provider

    @classmethod
    async def get_provider(cls, exchange: str) -> ExchangeProvider:
        """获取Provider实例（如不存在则创建）

        Args:
            exchange: 交易所名称

        Returns:
            ExchangeProvider 实例
        """
        return await cls.create_provider(exchange)

    @classmethod
    async def close_provider(cls, exchange: str) -> None:
        """关闭并移除Provider实例

        Args:
            exchange: 交易所名称
        """
        if exchange in cls._instances:
            provider = cls._instances[exchange]
            await provider.disconnect()
            del cls._instances[exchange]
            logger.info(f"Closed {exchange} provider")

    @classmethod
    async def close_all(cls) -> None:
        """关闭所有Provider实例"""
        for exchange in list(cls._instances.keys()):
            await cls.close_provider(exchange)

    @classmethod
    def list_active_providers(cls) -> list:
        """列出所有活跃的Provider

        Returns:
            交易所名称列表
        """
        return list(cls._instances.keys())

    @classmethod
    def has_provider(cls, exchange: str) -> bool:
        """检查Provider是否已创建

        Args:
            exchange: 交易所名称

        Returns:
            True 如果已创建，False 否则
        """
        return exchange in cls._instances
