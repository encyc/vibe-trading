"""
新闻数据存储

存储和检索历史新闻数据，用于回测时获取特定时间的市场新闻。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from pi_logger import get_logger

from vibe_trading.config.settings import get_settings

logger = get_logger(__name__)


@dataclass
class NewsData:
    """新闻数据"""
    symbol: str
    timestamp: int  # 毫秒时间戳

    # 新闻内容
    title: str
    content: str
    url: str
    source: str  # 新闻来源

    # 情绪分析
    sentiment: str  # positive, negative, neutral
    sentiment_score: float  # -1.0 到 1.0

    # 相关性
    relevance_score: float  # 0.0 到 1.0
    categories: List[str]  # 新闻类别标签

    # 元数据
    author: Optional[str] = None
    published_at: Optional[int] = None  # 原始发布时间

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "source": self.source,
            "sentiment": self.sentiment,
            "sentiment_score": self.sentiment_score,
            "relevance_score": self.relevance_score,
            "categories": self.categories,
            "author": self.author,
            "published_at": self.published_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "NewsData":
        """从字典创建"""
        return cls(**data)


class NewsStorage:
    """
    新闻数据存储

    提供历史新闻数据的CRUD操作。
    """

    def __init__(self, database_url: Optional[str] = None):
        """初始化存储"""
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self._engine = None
        self._session_factory = None
        logger.info("NewsStorage initialized")

    async def init(self) -> None:
        """初始化数据库"""
        self._engine = create_async_engine(self.database_url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

        # 创建news_data表
        async with self._engine.begin() as conn:
            await conn.run_sync(self._create_tables)

    def _create_tables(self, conn) -> None:
        """创建数据表"""
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS news_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) NOT NULL,
                timestamp INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                url TEXT,
                source VARCHAR(50),
                sentiment VARCHAR(10),
                sentiment_score REAL,
                relevance_score REAL,
                categories TEXT,
                author VARCHAR(100),
                published_at INTEGER,
                created_at INTEGER NOT NULL
            )
        """))

        # 创建索引
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_news_symbol_timestamp
            ON news_data(symbol, timestamp)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_news_timestamp
            ON news_data(timestamp)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_news_sentiment
            ON news_data(sentiment)
        """))

    async def close(self) -> None:
        """关闭连接"""
        if self._engine:
            await self._engine.dispose()

    async def _ensure_initialized(self) -> None:
        """确保数据库已初始化"""
        if self._session_factory is None:
            await self.init()

    async def save_news(self, news: NewsData) -> bool:
        """
        保存新闻数据

        Args:
            news: 新闻数据

        Returns:
            是否保存成功
        """
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                # 检查是否已存在（基于symbol, timestamp, url）
                existing = await session.execute(
                    text("""
                        SELECT id FROM news_data
                        WHERE symbol = :symbol
                        AND timestamp = :timestamp
                        AND url = :url
                        LIMIT 1
                    """),
                    {
                        "symbol": news.symbol,
                        "timestamp": news.timestamp,
                        "url": news.url,
                    }
                )

                if existing.fetchone():
                    # 已存在，跳过
                    logger.debug(f"新闻已存在: {news.title[:50]}...")
                    return True

                # 插入新数据
                await session.execute(
                    text("""
                        INSERT INTO news_data
                        (symbol, timestamp, title, content, url, source,
                         sentiment, sentiment_score, relevance_score, categories,
                         author, published_at, created_at)
                        VALUES (:symbol, :timestamp, :title, :content, :url,
                                :source, :sentiment, :sentiment_score,
                                :relevance_score, :categories, :author,
                                :published_at, :created_at)
                    """),
                    {
                        "symbol": news.symbol,
                        "timestamp": news.timestamp,
                        "title": news.title,
                        "content": news.content,
                        "url": news.url,
                        "source": news.source,
                        "sentiment": news.sentiment,
                        "sentiment_score": news.sentiment_score,
                        "relevance_score": news.relevance_score,
                        "categories": ",".join(news.categories) if news.categories else "",
                        "author": news.author,
                        "published_at": news.published_at,
                        "created_at": int(datetime.now().timestamp() * 1000),
                    }
                )

                await session.commit()
                logger.debug(
                    f"保存新闻: {news.symbol} @ {datetime.fromtimestamp(news.timestamp/1000)}"
                )
                return True

        except Exception as e:
            logger.error(f"保存新闻失败: {e}", exc_info=True)
            return False

    async def save_news_batch(self, news_list: List[NewsData]) -> int:
        """
        批量保存新闻

        Args:
            news_list: 新闻列表

        Returns:
            成功保存的数量
        """
        saved_count = 0
        for news in news_list:
            if await self.save_news(news):
                saved_count += 1
        return saved_count

    async def get_news_at(
        self,
        symbol: str,
        timestamp: int,
        time_window_hours: int = 24,
        limit: int = 50,
    ) -> Optional[List[NewsData]]:
        """
        获取指定时间附近的新闻

        Args:
            symbol: 交易品种
            timestamp: 时间戳（毫秒）
            time_window_hours: 时间窗口（小时），前后各查询这么多小时
            limit: 最大返回数量

        Returns:
            新闻列表，按时间倒序排列
        """
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                window_ms = time_window_hours * 60 * 60 * 1000

                result = await session.execute(
                    text("""
                        SELECT * FROM news_data
                        WHERE symbol = :symbol
                        AND timestamp BETWEEN :start_time AND :end_time
                        ORDER BY timestamp DESC
                        LIMIT :limit
                    """),
                    {
                        "symbol": symbol,
                        "start_time": timestamp - window_ms,
                        "end_time": timestamp + window_ms,
                        "limit": limit,
                    }
                )

                rows = result.fetchall()

                return [
                    NewsData(
                        symbol=row[1],
                        timestamp=row[2],
                        title=row[3],
                        content=row[4],
                        url=row[5],
                        source=row[6],
                        sentiment=row[7],
                        sentiment_score=row[8],
                        relevance_score=row[9],
                        categories=row[10].split(",") if row[10] else [],
                        author=row[11],
                        published_at=row[12],
                    )
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"获取新闻失败: {e}", exc_info=True)
            return None

    async def get_news_history(
        self,
        symbol: str,
        start_time: int,
        end_time: int,
        sentiment: Optional[str] = None,
        min_relevance: float = 0.5,
        limit: int = 1000,
    ) -> List[NewsData]:
        """
        获取历史新闻

        Args:
            symbol: 交易品种
            start_time: 开始时间（毫秒）
            end_time: 结束时间（毫秒）
            sentiment: 筛选情绪（可选）
            min_relevance: 最小相关性评分
            limit: 最大返回数量

        Returns:
            新闻列表
        """
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                query = """
                    SELECT * FROM news_data
                    WHERE symbol = :symbol
                    AND timestamp >= :start_time
                    AND timestamp <= :end_time
                    AND relevance_score >= :min_relevance
                """
                params = {
                    "symbol": symbol,
                    "start_time": start_time,
                    "end_time": end_time,
                    "min_relevance": min_relevance,
                }

                if sentiment:
                    query += " AND sentiment = :sentiment"
                    params["sentiment"] = sentiment

                query += " ORDER BY timestamp DESC LIMIT :limit"
                params["limit"] = limit

                result = await session.execute(text(query), params)
                rows = result.fetchall()

                return [
                    NewsData(
                        symbol=row[1],
                        timestamp=row[2],
                        title=row[3],
                        content=row[4],
                        url=row[5],
                        source=row[6],
                        sentiment=row[7],
                        sentiment_score=row[8],
                        relevance_score=row[9],
                        categories=row[10].split(",") if row[10] else [],
                        author=row[11],
                        published_at=row[12],
                    )
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"获取历史新闻失败: {e}", exc_info=True)
            return []

    async def get_latest_news(
        self,
        symbol: str,
        limit: int = 20,
    ) -> Optional[List[NewsData]]:
        """获取最新新闻"""
        try:
            await self._ensure_initialized()
            async with self._session_factory() as session:
                result = await session.execute(
                    text("""
                        SELECT * FROM news_data
                        WHERE symbol = :symbol
                        ORDER BY timestamp DESC
                        LIMIT :limit
                    """),
                    {"symbol": symbol, "limit": limit}
                )

                rows = result.fetchall()

                return [
                    NewsData(
                        symbol=row[1],
                        timestamp=row[2],
                        title=row[3],
                        content=row[4],
                        url=row[5],
                        source=row[6],
                        sentiment=row[7],
                        sentiment_score=row[8],
                        relevance_score=row[9],
                        categories=row[10].split(",") if row[10] else [],
                        author=row[11],
                        published_at=row[12],
                    )
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"获取最新新闻失败: {e}", exc_info=True)
            return None


# 全局实例
_news_storage: Optional[NewsStorage] = None


def get_news_storage() -> NewsStorage:
    """获取全局NewsStorage实例"""
    global _news_storage
    if _news_storage is None:
        _news_storage = NewsStorage()
    return _news_storage


def reset_news_storage() -> None:
    """重置全局存储（用于测试）"""
    global _news_storage
    _news_storage = None
