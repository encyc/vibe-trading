"""
基本面数据存储

存储和检索历史基本面数据，如资金费率、持仓量等。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import json

from sqlalchemy import select, update, delete, and_, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from pi_logger import get_logger

from vibe_trading.config.settings import get_settings

logger = get_logger(__name__)


@dataclass
class FundamentalData:
    """基本面数据"""
    symbol: str
    timestamp: int  # 毫秒时间戳

    # 资金费率相关
    funding_rate: float
    mark_price: float
    index_price: float
    # 持仓量相关
    open_interest: float
    open_interest_value: float  # 持仓价值

    # 元数据
    funding_rate_annualized: Optional[float] = None  # 年化资金费率
    next_funding_time: Optional[int] = None  # 下次资金费率时间

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "funding_rate": self.funding_rate,
            "mark_price": self.mark_price,
            "index_price": self.index_price,
            "open_interest": self.open_interest,
            "open_interest_value": self.open_interest_value,
            "funding_rate_annualized": self.funding_rate_annualized,
            "next_funding_time": self.next_funding_time,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "FundamentalData":
        """从字典创建"""
        return cls(**data)


class FundamentalStorage:
    """
    基本面数据存储

    提供历史资金费率、持仓量等数据的CRUD操作。
    """

    def __init__(self, database_url: Optional[str] = None):
        """初始化存储"""
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self._engine = None
        self._session_factory = None
        logger.info("FundamentalStorage initialized")

    async def init(self) -> None:
        """初始化数据库"""
        self._engine = create_async_engine(self.database_url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

        # 创建fundamental_data表
        async with self._engine.begin() as conn:
            await conn.run_sync(self._create_tables)

    def _create_tables(self, conn) -> None:
        """创建数据表"""
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fundamental_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) NOT NULL,
                timestamp INTEGER NOT NULL,
                funding_rate REAL NOT NULL,
                mark_price REAL NOT NULL,
                index_price REAL NOT NULL,
                open_interest REAL NOT NULL,
                open_interest_value REAL NOT NULL,
                funding_rate_annualized REAL,
                next_funding_time INTEGER,
                created_at INTEGER NOT NULL,
                UNIQUE(symbol, timestamp)
            )
        """))

        # 创建索引
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fundamental_symbol_timestamp
            ON fundamental_data(symbol, timestamp)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fundamental_timestamp
            ON fundamental_data(timestamp)
        """))

    async def close(self) -> None:
        """关闭连接"""
        if self._engine:
            await self._engine.dispose()

    async def _ensure_initialized(self) -> None:
        """确保数据库已初始化"""
        if self._session_factory is None:
            await self.init()

    async def save_fundamental_data(self, data: FundamentalData) -> bool:
        """
        保存基本面数据

        Args:
            data: 基本面数据

        Returns:
            是否保存成功
        """
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                # 使用INSERT OR REPLACE
                await session.execute(
                    text("""
                        INSERT OR REPLACE INTO fundamental_data
                        (symbol, timestamp, funding_rate, mark_price, index_price,
                         open_interest, open_interest_value, funding_rate_annualized,
                         next_funding_time, created_at)
                        VALUES (:symbol, :timestamp, :funding_rate, :mark_price,
                                :index_price, :open_interest, :open_interest_value,
                                :funding_rate_annualized, :next_funding_time,
                                :created_at)
                    """),
                    {
                        "symbol": data.symbol,
                        "timestamp": data.timestamp,
                        "funding_rate": data.funding_rate,
                        "mark_price": data.mark_price,
                        "index_price": data.index_price,
                        "open_interest": data.open_interest,
                        "open_interest_value": data.open_interest_value,
                        "funding_rate_annualized": data.funding_rate_annualized,
                        "next_funding_time": data.next_funding_time,
                        "created_at": int(datetime.now().timestamp() * 1000),
                    }
                )

                await session.commit()
                logger.debug(
                    f"保存基本面数据: {data.symbol} @ {datetime.fromtimestamp(data.timestamp/1000)}"
                )
                return True

        except Exception as e:
            logger.error(f"保存基本面数据失败: {e}", exc_info=True)
            return False

    async def get_fundamental_data(
        self,
        symbol: str,
        timestamp: int,
        tolerance_seconds: int = 60
    ) -> Optional[FundamentalData]:
        """
        获取指定时间的基本面数据

        Args:
            symbol: 交易品种
            timestamp: 时间戳（毫秒）
            tolerance_seconds: 时间容差（秒）

        Returns:
            基本面数据，如果不存在则返回None
        """
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                tolerance_ms = tolerance_seconds * 1000

                result = await session.execute(
                    text("""
                        SELECT * FROM fundamental_data
                        WHERE symbol = :symbol
                        AND ABS(timestamp - :timestamp) <= :tolerance_ms
                        ORDER BY ABS(timestamp - :timestamp) ASC
                        LIMIT 1
                    """),
                    {"symbol": symbol, "timestamp": timestamp, "tolerance_ms": tolerance_ms}
                )

                row = result.fetchone()

                if row:
                    return FundamentalData(
                        symbol=row[1],
                        timestamp=row[2],
                        funding_rate=row[3],
                        mark_price=row[4],
                        index_price=row[5],
                        open_interest=row[6],
                        open_interest_value=row[7],
                        funding_rate_annualized=row[8],
                        next_funding_time=row[9],
                    )

                return None

        except Exception as e:
            logger.error(f"获取基本面数据失败: {e}", exc_info=True)
            return None

    async def get_fundamental_history(
        self,
        symbol: str,
        start_time: int,
        end_time: int,
        limit: int = 1000,
    ) -> List[FundamentalData]:
        """
        获取历史基本面数据

        Args:
            symbol: 交易品种
            start_time: 开始时间（毫秒）
            end_time: 结束时间（毫秒）
            limit: 最大返回数量

        Returns:
            基本面数据列表
        """
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                result = await session.execute(
                    text("""
                        SELECT * FROM fundamental_data
                        WHERE symbol = :symbol
                        AND timestamp >= :start_time
                        AND timestamp <= :end_time
                        ORDER BY timestamp DESC
                        LIMIT :limit
                    """),
                    {"symbol": symbol, "start_time": start_time, "end_time": end_time, "limit": limit}
                )

                rows = result.fetchall()

                return [
                    FundamentalData(
                        symbol=row[1],
                        timestamp=row[2],
                        funding_rate=row[3],
                        mark_price=row[4],
                        index_price=row[5],
                        open_interest=row[6],
                        open_interest_value=row[7],
                        funding_rate_annualized=row[8],
                        next_funding_time=row[9],
                    )
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"获取历史基本面数据失败: {e}", exc_info=True)
            return []

    async def get_latest_fundamental_data(
        self,
        symbol: str,
    ) -> Optional[FundamentalData]:
        """获取最新的基本面数据"""
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                result = await session.execute(
                    text("""
                        SELECT * FROM fundamental_data
                        WHERE symbol = :symbol
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """),
                    {"symbol": symbol}
                )

                row = result.fetchone()

                if row:
                    return FundamentalData(
                        symbol=row[1],
                        timestamp=row[2],
                        funding_rate=row[3],
                        mark_price=row[4],
                        index_price=row[5],
                        open_interest=row[6],
                        open_interest_value=row[7],
                        funding_rate_annualized=row[8],
                        next_funding_time=row[9],
                    )

                return None

        except Exception as e:
            logger.error(f"获取最新基本面数据失败: {e}", exc_info=True)
            return None


# 全局实例
_fundamental_storage: Optional[FundamentalStorage] = None


def get_fundamental_storage() -> FundamentalStorage:
    """获取全局FundamentalStorage实例"""
    global _fundamental_storage
    if _fundamental_storage is None:
        _fundamental_storage = FundamentalStorage()
    return _fundamental_storage


def reset_fundamental_storage() -> None:
    """重置全局存储（用于测试）"""
    global _fundamental_storage
    _fundamental_storage = None
