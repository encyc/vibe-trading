"""
统一数据模型

定义跨交易所的标准化数据结构。
"""
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from enum import Enum


class IntervalType(str, Enum):
    """标准化的K线间隔"""

    MINUTE_1 = "1m"
    MINUTE_3 = "3m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_2 = "2h"
    HOUR_4 = "4h"
    HOUR_6 = "6h"
    HOUR_12 = "12h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"


@dataclass
class StandardKline:
    """标准化K线数据

    跨交易所的统一K线格式，包含所有必要字段。
    """

    exchange: str  # 交易所标识（如 "binance", "okx"）
    symbol: str  # 交易对（如 "BTCUSDT"）
    interval: str  # K线间隔（如 "1m", "5m", "1h"）
    open_time: int  # 开盘时间（毫秒时间戳）
    open: float  # 开盘价
    high: float  # 最高价
    low: float  # 最低价
    close: float  # 收盘价
    volume: float  # 成交量
    close_time: int  # 收盘时间（毫秒时间戳）
    quote_volume: float  # 成交额
    trades: int  # 成交笔数
    taker_buy_base: float  # 主动买入量
    taker_buy_quote: float  # 主动买入额
    is_final: bool  # 是否已完成（K线是否关闭）

    @property
    def open_datetime(self) -> datetime:
        """开盘时间（datetime对象）"""
        return datetime.fromtimestamp(self.open_time / 1000)

    @property
    def close_datetime(self) -> datetime:
        """收盘时间（datetime对象）"""
        return datetime.fromtimestamp(self.close_time / 1000)

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time": self.open_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "close_time": self.close_time,
            "quote_volume": self.quote_volume,
            "trades": self.trades,
            "taker_buy_base": self.taker_buy_base,
            "taker_buy_quote": self.taker_buy_quote,
            "is_final": self.is_final,
        }


@dataclass
class StandardTicker:
    """标准化24小时行情

    跨交易所的统一24小时ticker格式。
    """

    exchange: str  # 交易所标识
    symbol: str  # 交易对
    price_change: float  # 价格变化
    price_change_percent: float  # 价格变化百分比
    high: float  # 24小时最高价
    low: float  # 24小时最低价
    volume: float  # 24小时成交量
    quote_volume: float  # 24小时成交额
    open: float  # 24小时开盘价
    close: float  # 最新价格
    timestamp: int  # 时间戳（毫秒）

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "price_change": self.price_change,
            "price_change_percent": self.price_change_percent,
            "high": self.high,
            "low": self.low,
            "volume": self.volume,
            "quote_volume": self.quote_volume,
            "open": self.open,
            "close": self.close,
            "timestamp": self.timestamp,
        }


@dataclass
class OrderBookLevel:
    """订单簿层级

    表示订单簿中的一个价格层级。
    """

    price: float  # 价格
    quantity: float  # 数量


@dataclass
class StandardOrderBook:
    """标准化订单簿

    跨交易所的统一订单簿格式。
    """

    exchange: str  # 交易所标识
    symbol: str  # 交易对
    bids: List[OrderBookLevel]  # 买单列表（从高到低）
    asks: List[OrderBookLevel]  # 卖单列表（从低到高）
    timestamp: int  # 时间戳（毫秒）

    def get_best_bid(self) -> Optional[OrderBookLevel]:
        """获取最优买价"""
        return self.bids[0] if self.bids else None

    def get_best_ask(self) -> Optional[OrderBookLevel]:
        """获取最优卖价"""
        return self.asks[0] if self.asks else None

    def get_spread(self) -> Optional[float]:
        """获取买卖价差"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid and best_ask:
            return best_ask.price - best_bid.price
        return None

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "bids": [{"price": level.price, "quantity": level.quantity} for level in self.bids],
            "asks": [{"price": level.price, "quantity": level.quantity} for level in self.asks],
            "timestamp": self.timestamp,
        }
