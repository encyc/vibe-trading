"""
K线数据存储模块

提供 K线数据的存储和检索功能。
"""
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import Column, Integer, String, Float, Boolean, BigInteger
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import select

from vibe_trading.config.settings import get_settings
from vibe_trading.data_sources.binance_client import Kline

Base = declarative_base()


class KlineModel(Base):
    """K线数据模型"""
    __tablename__ = "klines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), index=True, nullable=False)
    interval = Column(String(10), nullable=False)
    open_time = Column(BigInteger, index=True, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    close_time = Column(BigInteger, nullable=False)
    quote_volume = Column(Float, nullable=False)
    trades = Column(Integer, nullable=False)
    taker_buy_base = Column(Float, nullable=False)
    taker_buy_quote = Column(Float, nullable=False)
    is_final = Column(Boolean, default=False)

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


@dataclass
class KlineQuery:
    """K线查询条件"""
    symbol: str
    interval: str
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    limit: Optional[int] = None


class KlineStorage:
    """K线数据存储"""

    def __init__(self, database_url: Optional[str] = None):
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self._engine = None
        self._session_factory = None

    async def init(self) -> None:
        """初始化数据库"""
        self._engine = create_async_engine(self.database_url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

        # 创建表
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._engine:
            await self._engine.dispose()

    async def _ensure_initialized(self) -> None:
        """确保数据库已初始化"""
        if self._session_factory is None:
            await self.init()

    async def store_kline(self, kline: Kline) -> None:
        """存储单条 K线数据"""
        await self._ensure_initialized()
        async with self._session_factory() as session:
            # 检查是否已存在
            stmt = select(KlineModel).where(
                KlineModel.symbol == kline.symbol,
                KlineModel.interval == kline.interval,
                KlineModel.open_time == kline.open_time,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # 更新现有记录
                existing.open = kline.open
                existing.high = kline.high
                existing.low = kline.low
                existing.close = kline.close
                existing.volume = kline.volume
                existing.close_time = kline.close_time
                existing.quote_volume = kline.quote_volume
                existing.trades = kline.trades
                existing.taker_buy_base = kline.taker_buy_base
                existing.taker_buy_quote = kline.taker_buy_quote
                existing.is_final = kline.is_final
            else:
                # 插入新记录
                db_kline = KlineModel(
                    symbol=kline.symbol,
                    interval=kline.interval,
                    open_time=kline.open_time,
                    open=kline.open,
                    high=kline.high,
                    low=kline.low,
                    close=kline.close,
                    volume=kline.volume,
                    close_time=kline.close_time,
                    quote_volume=kline.quote_volume,
                    trades=kline.trades,
                    taker_buy_base=kline.taker_buy_base,
                    taker_buy_quote=kline.taker_buy_quote,
                    is_final=kline.is_final,
                )
                session.add(db_kline)

            await session.commit()

    async def store_klines(self, klines: List[Kline]) -> None:
        """批量存储 K线数据"""
        await self._ensure_initialized()
        async with self._session_factory() as session:
            for kline in klines:
                stmt = select(KlineModel).where(
                    KlineModel.symbol == kline.symbol,
                    KlineModel.interval == kline.interval,
                    KlineModel.open_time == kline.open_time,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.open = kline.open
                    existing.high = kline.high
                    existing.low = kline.low
                    existing.close = kline.close
                    existing.volume = kline.volume
                    existing.close_time = kline.close_time
                    existing.quote_volume = kline.quote_volume
                    existing.trades = kline.trades
                    existing.taker_buy_base = kline.taker_buy_base
                    existing.taker_buy_quote = kline.taker_buy_quote
                    existing.is_final = kline.is_final
                else:
                    db_kline = KlineModel(
                        symbol=kline.symbol,
                        interval=kline.interval,
                        open_time=kline.open_time,
                        open=kline.open,
                        high=kline.high,
                        low=kline.low,
                        close=kline.close,
                        volume=kline.volume,
                        close_time=kline.close_time,
                        quote_volume=kline.quote_volume,
                        trades=kline.trades,
                        taker_buy_base=kline.taker_buy_base,
                        taker_buy_quote=kline.taker_buy_quote,
                        is_final=kline.is_final,
                    )
                    session.add(db_kline)

            await session.commit()

    async def query_klines(self, query: KlineQuery) -> List[Kline]:
        """查询 K线数据"""
        await self._ensure_initialized()
        async with self._session_factory() as session:
            stmt = select(KlineModel).where(
                KlineModel.symbol == query.symbol,
                KlineModel.interval == query.interval,
            )

            if query.start_time:
                stmt = stmt.where(KlineModel.open_time >= query.start_time)
            if query.end_time:
                stmt = stmt.where(KlineModel.open_time <= query.end_time)

            stmt = stmt.order_by(KlineModel.open_time.desc())

            if query.limit:
                stmt = stmt.limit(query.limit)

            result = await session.execute(stmt)
            rows = result.scalars().all()

            klines = []
            for row in reversed(rows):
                klines.append(
                    Kline(
                        symbol=row.symbol,
                        interval=row.interval,
                        open_time=row.open_time,
                        open=row.open,
                        high=row.high,
                        low=row.low,
                        close=row.close,
                        volume=row.volume,
                        close_time=row.close_time,
                        quote_volume=row.quote_volume,
                        trades=row.trades,
                        taker_buy_base=row.taker_buy_base,
                        taker_buy_quote=row.taker_buy_quote,
                        is_final=row.is_final,
                    )
                )

            return klines

    async def get_latest_kline(self, symbol: str, interval: str) -> Optional[Kline]:
        """获取最新的 K线数据"""
        query = KlineQuery(symbol=symbol, interval=interval, limit=1)
        klines = await self.query_klines(query)
        return klines[0] if klines else None

    async def count_klines(self, symbol: str, interval: str) -> int:
        """统计 K线数量"""
        await self._ensure_initialized()
        async with self._session_factory() as session:
            stmt = select(KlineModel).where(
                KlineModel.symbol == symbol,
                KlineModel.interval == interval,
            )
            result = await session.execute(stmt)
            return len(result.all())
