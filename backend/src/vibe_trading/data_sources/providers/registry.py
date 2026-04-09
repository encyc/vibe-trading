"""
Provider 注册表

管理所有可用的交易所提供者类。
"""
from typing import Dict, Type, Optional, List

from .base import ExchangeProvider


class ProviderRegistry:
    """Provider 注册表

    使用注册表模式管理所有交易所提供者类。
    支持动态注册和查询。
    """

    _providers: Dict[str, Type[ExchangeProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_class: Type[ExchangeProvider]) -> None:
        """注册Provider类

        Args:
            name: 交易所名称（如 "binance", "okx"）
            provider_class: Provider类

        Raises:
            ValueError: 如果名称已存在
        """
        if name in cls._providers:
            raise ValueError(f"Provider '{name}' is already registered")

        if not issubclass(provider_class, ExchangeProvider):
            raise TypeError(f"{provider_class} must be a subclass of ExchangeProvider")

        cls._providers[name] = provider_class

    @classmethod
    def get(cls, name: str) -> Optional[Type[ExchangeProvider]]:
        """获取Provider类

        Args:
            name: 交易所名称

        Returns:
            Provider类，如果不存在则返回None
        """
        return cls._providers.get(name)

    @classmethod
    def list_providers(cls) -> List[str]:
        """列出所有已注册的Provider

        Returns:
            交易所名称列表
        """
        return list(cls._providers.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """检查Provider是否已注册

        Args:
            name: 交易所名称

        Returns:
            True 如果已注册，False 否则
        """
        return name in cls._providers

    @classmethod
    def unregister(cls, name: str) -> None:
        """注销Provider

        Args:
            name: 交易所名称

        Raises:
            KeyError: 如果Provider不存在
        """
        if name not in cls._providers:
            raise KeyError(f"Provider '{name}' is not registered")

        del cls._providers[name]


# 注册内置Provider
from .binance_provider import BinanceProvider
ProviderRegistry.register("binance", BinanceProvider)
