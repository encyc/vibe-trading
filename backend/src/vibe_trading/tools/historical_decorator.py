"""
历史数据装饰器

为工具函数提供自动的历史数据回退功能。
在回测模式下，装饰器会自动从历史存储获取数据而非调用实时API。
"""
from functools import wraps
from typing import Callable, Literal, Optional

from pi_logger import get_logger

logger = get_logger(__name__)


def historical_data_fallback(
    data_type: Literal["fundamental", "news", "sentiment", "macro"]
):
    """
    装饰器：自动处理回测模式下的历史数据获取

    在回测模式下，此装饰器会：
    1. 检测ToolContext的mode
    2. 如果是回测模式，从historical_storage获取数据
    3. 如果是实时模式，调用原函数（API调用）

    Args:
        data_type: 数据类型（fundamental, news, sentiment, macro）

    Examples:
        >>> @historical_data_fallback("fundamental")
        ... async def get_funding_rate(symbol: str, tool_context: ToolContext) -> dict:
        ...     # 实时模式实现
        ...     return await binance_client.get_funding_rate(symbol)
        ...
        >>> # 回测模式下会自动从fundamental_storage获取数据

    Returns:
        装饰后的函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 尝试从kwargs或args获取tool_context
            tool_context = _extract_tool_context(args, kwargs)

            # 检查是否为回测模式
            if tool_context and tool_context.is_backtest():
                # 回测模式：从历史存储获取
                timestamp = tool_context.current_timestamp

                logger.debug(
                    f"回测模式: 从历史存储获取 {data_type} 数据 "
                    f"(timestamp={timestamp})"
                )

                historical_data = await tool_context.get_historical_data_at(
                    data_type, timestamp
                )

                if historical_data:
                    logger.debug(f"成功获取历史{data_type}数据")
                    return historical_data

                # 如果没有历史数据，记录警告但不中断
                logger.warning(
                    f"没有找到历史 {data_type} 数据 (timestamp={timestamp})"
                )
                # 返回None或默认值
                return None

            # 实时模式：调用原函数
            return await func(*args, **kwargs)

        return wrapper
    return decorator


def _extract_tool_context(args, kwargs) -> Optional:
    """
    从函数参数中提取ToolContext

    支持以下参数形式：
    1. tool_context作为关键字参数
    2. tool_context作为第一个位置参数
    3. context作为关键字参数（别名）

    Args:
        args: 位置参数
        kwargs: 关键字参数

    Returns:
        ToolContext对象，如果找不到则返回None
    """
    # 1. 尝试从kwargs获取
    if "tool_context" in kwargs:
        return kwargs["tool_context"]

    if "context" in kwargs:
        ctx = kwargs["context"]
        # 检查是否是ToolContext类型
        if hasattr(ctx, "is_backtest"):
            return ctx

    # 2. 尝试从args获取（通常是第一个参数）
    if args and len(args) > 0:
        first_arg = args[0]
        # 检查是否是ToolContext类型
        if hasattr(first_arg, "is_backtest") and hasattr(first_arg, "symbol"):
            return first_arg

    return None


# =============================================================================
# 便捷装饰器组合
# =============================================================================

def backtest_compatible(
    data_types: list[Literal["fundamental", "news", "sentiment", "macro"]]
):
    """
    组合装饰器：支持多种数据类型的历史数据回退

    Args:
        data_types: 支持的数据类型列表

    Examples:
        >>> @backtest_compatible(["fundamental", "sentiment"])
        ... async def get_market_data(symbol: str, tool_context: ToolContext):
        ...     # 可以处理fundamental和sentiment两种数据
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        # 这里简化处理，只使用第一个data_type
        # 完整实现需要根据实际调用参数动态选择
        if data_types:
            return historical_data_fallback(data_types[0])(func)
        return func
    return decorator


# =============================================================================
# 历史数据适配器
# =============================================================================

class HistoricalDataAdapter:
    """
    历史数据适配器

    提供统一的历史数据访问接口，支持多种数据源。
    """

    def __init__(self, tool_context):
        """
        初始化适配器

        Args:
            tool_context: ToolContext实例
        """
        self.context = tool_context

    async def get_funding_rate(self, symbol: str) -> Optional[dict]:
        """获取资金费率（历史或实时）"""
        if self.context.is_backtest():
            data = await self.context.get_historical_data_at("fundamental")
            if data:
                return {
                    "funding_rate": data.funding_rate if hasattr(data, "funding_rate") else None,
                    "timestamp": self.context.current_timestamp,
                }

        # 实时模式：调用API（需要外部实现）
        return None

    async def get_news_sentiment(self, symbol: str) -> Optional[dict]:
        """获取新闻情绪（历史或实时）"""
        if self.context.is_backtest():
            data = await self.context.get_historical_data_at("news")
            if data:
                return {
                    "sentiment": data.sentiment if hasattr(data, "sentiment") else None,
                    "timestamp": self.context.current_timestamp,
                }

        # 实时模式：调用API
        return None

    async def get_fear_greed_index(self) -> Optional[dict]:
        """获取恐惧贪婪指数（历史或实时）"""
        if self.context.is_backtest():
            data = await self.context.get_historical_data_at("sentiment")
            if data:
                return {
                    "value": data.value if hasattr(data, "value") else None,
                    "classification": data.classification if hasattr(data, "classification") else None,
                    "timestamp": self.context.current_timestamp,
                }

        # 实时模式：调用API
        return None

    async def get_macro_state(self, symbol: str) -> Optional[dict]:
        """获取宏观状态（历史或实时）"""
        if self.context.is_backtest():
            data = await self.context.get_historical_data_at("macro")
            if data:
                return {
                    "trend_direction": data.trend_direction,
                    "sentiment": data.overall_sentiment,
                    "timestamp": self.context.current_timestamp,
                }

        # 实时模式：返回当前状态
        return None
