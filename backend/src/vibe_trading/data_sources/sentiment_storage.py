"""
情绪数据存储

存储和检索历史情绪指标数据，如恐惧贪婪指数、社交情绪等。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from pi_logger import get_logger

from vibe_trading.config.settings import get_settings

logger = get_logger(__name__)


@dataclass
class SentimentData:
    """情绪数据"""
    symbol: str  # "BTC" 或 "GLOBAL" 表示市场整体情绪
    timestamp: int  # 毫秒时间戳

    # 恐惧贪婪指数
    fear_greed_value: Optional[int] = None  # 0-100
    fear_greed_classification: Optional[str] = None  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"

    # 社交媒体情绪
    social_sentiment_score: Optional[float] = None  # -1.0 到 1.0
    social_volume: Optional[int] = None  # 提及量
    social_influence: Optional[float] = None  # 影响力评分

    # 趋势情绪
    trend_sentiment: Optional[str] = None  # "bullish", "bearish", "neutral"
    trend_strength: Optional[float] = None  # 0.0 到 1.0

    # 期权市场情绪
    put_call_ratio: Optional[float] = None
    implied_volatility: Optional[float] = None

    # 元数据
    data_source: Optional[str] = None  # 数据来源
    updated_at: Optional[int] = None  # 原始数据更新时间

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "fear_greed_value": self.fear_greed_value,
            "fear_greed_classification": self.fear_greed_classification,
            "social_sentiment_score": self.social_sentiment_score,
            "social_volume": self.social_volume,
            "social_influence": self.social_influence,
            "trend_sentiment": self.trend_sentiment,
            "trend_strength": self.trend_strength,
            "put_call_ratio": self.put_call_ratio,
            "implied_volatility": self.implied_volatility,
            "data_source": self.data_source,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SentimentData":
        """从字典创建"""
        return cls(**data)


class SentimentStorage:
    """
    情绪数据存储

    提供历史情绪数据的CRUD操作。
    """

    def __init__(self, database_url: Optional[str] = None):
        """初始化存储"""
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self._engine = None
        self._session_factory = None
        logger.info("SentimentStorage initialized")

    async def init(self) -> None:
        """初始化数据库"""
        self._engine = create_async_engine(self.database_url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

        # 创建sentiment_data表
        async with self._engine.begin() as conn:
            await conn.run_sync(self._create_tables)

    def _create_tables(self, conn) -> None:
        """创建数据表"""
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sentiment_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) NOT NULL,
                timestamp INTEGER NOT NULL,
                fear_greed_value INTEGER,
                fear_greed_classification VARCHAR(20),
                social_sentiment_score REAL,
                social_volume INTEGER,
                social_influence REAL,
                trend_sentiment VARCHAR(10),
                trend_strength REAL,
                put_call_ratio REAL,
                implied_volatility REAL,
                data_source VARCHAR(50),
                updated_at INTEGER,
                created_at INTEGER NOT NULL,
                UNIQUE(symbol, timestamp)
            )
        """))

        # 创建索引
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sentiment_symbol_timestamp
            ON sentiment_data(symbol, timestamp)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sentiment_timestamp
            ON sentiment_data(timestamp)
        """))

    async def close(self) -> None:
        """关闭连接"""
        if self._engine:
            await self._engine.dispose()

    async def _ensure_initialized(self) -> None:
        """确保数据库已初始化"""
        if self._session_factory is None:
            await self.init()

    async def save_sentiment(self, data: SentimentData) -> bool:
        """
        保存情绪数据

        Args:
            data: 情绪数据

        Returns:
            是否保存成功
        """
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                # 使用INSERT OR REPLACE
                await session.execute(
                    text("""
                        INSERT OR REPLACE INTO sentiment_data
                        (symbol, timestamp, fear_greed_value, fear_greed_classification,
                         social_sentiment_score, social_volume, social_influence,
                         trend_sentiment, trend_strength, put_call_ratio,
                         implied_volatility, data_source, updated_at, created_at)
                        VALUES (:symbol, :timestamp, :fear_greed_value, :fear_greed_classification,
                                :social_sentiment_score, :social_volume, :social_influence,
                                :trend_sentiment, :trend_strength, :put_call_ratio,
                                :implied_volatility, :data_source, :updated_at, :created_at)
                    """),
                    {
                        "symbol": data.symbol,
                        "timestamp": data.timestamp,
                        "fear_greed_value": data.fear_greed_value,
                        "fear_greed_classification": data.fear_greed_classification,
                        "social_sentiment_score": data.social_sentiment_score,
                        "social_volume": data.social_volume,
                        "social_influence": data.social_influence,
                        "trend_sentiment": data.trend_sentiment,
                        "trend_strength": data.trend_strength,
                        "put_call_ratio": data.put_call_ratio,
                        "implied_volatility": data.implied_volatility,
                        "data_source": data.data_source,
                        "updated_at": data.updated_at,
                        "created_at": int(datetime.now().timestamp() * 1000),
                    }
                )

                await session.commit()
                logger.debug(
                    f"保存情绪数据: {data.symbol} @ {datetime.fromtimestamp(data.timestamp/1000)}"
                )
                return True

        except Exception as e:
            logger.error(f"保存情绪数据失败: {e}", exc_info=True)
            return False

    async def get_sentiment_at(
        self,
        symbol: str,
        timestamp: int,
        tolerance_seconds: int = 3600,
    ) -> Optional[SentimentData]:
        """
        获取指定时间的情绪数据

        Args:
            symbol: 交易品种（"BTC" 或 "GLOBAL"）
            timestamp: 时间戳（毫秒）
            tolerance_seconds: 时间容差（秒），默认1小时

        Returns:
            情绪数据，如果不存在则返回None
        """
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                tolerance_ms = tolerance_seconds * 1000

                result = await session.execute(
                    text("""
                        SELECT * FROM sentiment_data
                        WHERE symbol = :symbol
                        AND ABS(timestamp - :timestamp) <= :tolerance_ms
                        ORDER BY ABS(timestamp - :timestamp) ASC
                        LIMIT 1
                    """),
                    {
                        "symbol": symbol,
                        "timestamp": timestamp,
                        "tolerance_ms": tolerance_ms
                    }
                )

                row = result.fetchone()

                if row:
                    return SentimentData(
                        symbol=row[1],
                        timestamp=row[2],
                        fear_greed_value=row[3],
                        fear_greed_classification=row[4],
                        social_sentiment_score=row[5],
                        social_volume=row[6],
                        social_influence=row[7],
                        trend_sentiment=row[8],
                        trend_strength=row[9],
                        put_call_ratio=row[10],
                        implied_volatility=row[11],
                        data_source=row[12],
                        updated_at=row[13],
                    )

                return None

        except Exception as e:
            logger.error(f"获取情绪数据失败: {e}", exc_info=True)
            return None

    async def get_sentiment_history(
        self,
        symbol: str,
        start_time: int,
        end_time: int,
        limit: int = 1000,
    ) -> List[SentimentData]:
        """
        获取历史情绪数据

        Args:
            symbol: 交易品种（"BTC" 或 "GLOBAL"）
            start_time: 开始时间（毫秒）
            end_time: 结束时间（毫秒）
            limit: 最大返回数量

        Returns:
            情绪数据列表
        """
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                result = await session.execute(
                    text("""
                        SELECT * FROM sentiment_data
                        WHERE symbol = :symbol
                        AND timestamp >= :start_time
                        AND timestamp <= :end_time
                        ORDER BY timestamp DESC
                        LIMIT :limit
                    """),
                    {
                        "symbol": symbol,
                        "start_time": start_time,
                        "end_time": end_time,
                        "limit": limit
                    }
                )

                rows = result.fetchall()

                return [
                    SentimentData(
                        symbol=row[1],
                        timestamp=row[2],
                        fear_greed_value=row[3],
                        fear_greed_classification=row[4],
                        social_sentiment_score=row[5],
                        social_volume=row[6],
                        social_influence=row[7],
                        trend_sentiment=row[8],
                        trend_strength=row[9],
                        put_call_ratio=row[10],
                        implied_volatility=row[11],
                        data_source=row[12],
                        updated_at=row[13],
                    )
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"获取历史情绪数据失败: {e}", exc_info=True)
            return []

    async def get_latest_sentiment(
        self,
        symbol: str,
    ) -> Optional[SentimentData]:
        """获取最新情绪数据"""
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                result = await session.execute(
                    text("""
                        SELECT * FROM sentiment_data
                        WHERE symbol = :symbol
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """),
                    {"symbol": symbol}
                )

                row = result.fetchone()

                if row:
                    return SentimentData(
                        symbol=row[1],
                        timestamp=row[2],
                        fear_greed_value=row[3],
                        fear_greed_classification=row[4],
                        social_sentiment_score=row[5],
                        social_volume=row[6],
                        social_influence=row[7],
                        trend_sentiment=row[8],
                        trend_strength=row[9],
                        put_call_ratio=row[10],
                        implied_volatility=row[11],
                        data_source=row[12],
                        updated_at=row[13],
                    )

                return None

        except Exception as e:
            logger.error(f"获取最新情绪数据失败: {e}", exc_info=True)
            return None

    async def get_fear_greed_history(
        self,
        start_time: int,
        end_time: int,
        limit: int = 1000,
    ) -> List[SentimentData]:
        """
        获取恐惧贪婪指数历史（市场整体情绪）

        Args:
            start_time: 开始时间（毫秒）
            end_time: 结束时间（毫秒）
            limit: 最大返回数量

        Returns:
            情绪数据列表
        """
        return await self.get_sentiment_history(
            symbol="GLOBAL",
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )


# 全局实例
_sentiment_storage: Optional[SentimentStorage] = None


def get_sentiment_storage() -> SentimentStorage:
    """获取全局SentimentStorage实例"""
    global _sentiment_storage
    if _sentiment_storage is None:
        _sentiment_storage = SentimentStorage()
    return _sentiment_storage


def reset_sentiment_storage() -> None:
    """重置全局存储（用于测试）"""
    global _sentiment_storage
    _sentiment_storage = None
