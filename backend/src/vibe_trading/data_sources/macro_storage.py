"""
Macro Storage

Stores and retrieves macro analysis results.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json

from sqlalchemy import select, update, delete, and_, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from vibe_trading.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class MacroState:
    """Macro analysis state"""
    symbol: str
    timestamp: int
    
    # Trend Analysis
    trend_direction: str  # UPTREND/DOWNTREND/SIDEWAYS
    trend_strength: str   # STRONG/MODERATE/WEAK
    market_regime: str    # BULL/BEAR/NEUTRAL
    
    # Sentiment Analysis
    overall_sentiment: str  # POSITIVE/NEGATIVE/NEUTRAL
    sentiment_score: float  # -100 to 100
    
    # Major Events
    major_events: List[Dict]
    
    # Agent Recommendation
    agent_recommendation: Dict
    
    # Metadata
    confidence: float  # 0 to 1
    analysis_duration: float  # seconds
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "MacroState":
        """Create from dictionary"""
        return cls(**data)


class MacroStorage:
    """
    Macro state storage
    
    Provides CRUD operations for macro analysis results.
    """
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize macro storage"""
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self._engine = None
        self._session_factory = None
        logger.info("MacroStorage initialized")
    
    async def init(self) -> None:
        """Initialize database"""
        self._engine = create_async_engine(self.database_url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        
        # Create macro_states table if not exists
        async with self._engine.begin() as conn:
            await conn.run_sync(self._create_tables)
    
    def _create_tables(self, conn) -> None:
        """Create macro_states table"""
        # Create table using SQL
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS macro_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) NOT NULL,
                timestamp INTEGER NOT NULL,
                trend_direction VARCHAR(20),
                trend_strength VARCHAR(20),
                market_regime VARCHAR(20),
                overall_sentiment VARCHAR(20),
                sentiment_score REAL,
                major_events TEXT,
                agent_recommendation TEXT,
                confidence REAL,
                analysis_duration REAL,
                created_at INTEGER NOT NULL,
                UNIQUE(symbol, timestamp)
            )
        """))
        
        # Create indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_macro_states_symbol_timestamp 
            ON macro_states(symbol, timestamp)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_macro_states_timestamp 
            ON macro_states(timestamp)
        """))
    
    async def close(self) -> None:
        """Close database connection"""
        if self._engine:
            await self._engine.dispose()
    
    async def save_state(self, state: MacroState) -> bool:
        """
        Save macro state to database
        
        Args:
            state: Macro state to save
            
        Returns:
            True if saved successfully
        """
        try:
            async with self._session_factory() as session:
                # Insert or update
                stmt = text("""
                    INSERT OR REPLACE INTO macro_states (
                        symbol, timestamp,
                        trend_direction, trend_strength, market_regime,
                        overall_sentiment, sentiment_score,
                        major_events, agent_recommendation,
                        confidence, analysis_duration,
                        created_at
                    ) VALUES (
                        :symbol, :timestamp,
                        :trend_direction, :trend_strength, :market_regime,
                        :overall_sentiment, :sentiment_score,
                        :major_events, :agent_recommendation,
                        :confidence, :analysis_duration,
                        :created_at
                    )
                """)
                
                await session.execute(
                    stmt,
                    {
                        "symbol": state.symbol,
                        "timestamp": state.timestamp,
                        "trend_direction": state.trend_direction,
                        "trend_strength": state.trend_strength,
                        "market_regime": state.market_regime,
                        "overall_sentiment": state.overall_sentiment,
                        "sentiment_score": state.sentiment_score,
                        "major_events": json.dumps(state.major_events),
                        "agent_recommendation": json.dumps(state.agent_recommendation),
                        "confidence": state.confidence,
                        "analysis_duration": state.analysis_duration,
                        "created_at": int(datetime.now().timestamp() * 1000),
                    }
                )
                
                await session.commit()
                logger.debug(f"Macro state saved: {state.symbol} @ {state.timestamp}")
                return True
                
        except Exception as e:
            logger.error(f"Error saving macro state: {e}", exc_info=True)
            return False
    
    async def get_latest_state(self, symbol: str) -> Optional[MacroState]:
        """
        Get latest macro state for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            MacroState or None if not found
        """
        try:
            async with self._session_factory() as session:
                stmt = text("""
                    SELECT * FROM macro_states
                    WHERE symbol = :symbol
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                
                result = await session.execute(stmt, {"symbol": symbol})
                row = result.fetchone()
                
                if row:
                    return self._row_to_state(row)
                return None
                
        except Exception as e:
            logger.error(f"Error getting latest macro state: {e}", exc_info=True)
            return None
    
    async def get_state_by_timestamp(
        self,
        symbol: str,
        timestamp: int,
        tolerance_seconds: int = 60
    ) -> Optional[MacroState]:
        """
        Get macro state by timestamp
        
        Args:
            symbol: Trading symbol
            timestamp: Target timestamp (milliseconds)
            tolerance_seconds: Time tolerance in seconds
            
        Returns:
            MacroState or None if not found
        """
        try:
            async with self._session_factory() as session:
                stmt = text("""
                    SELECT * FROM macro_states
                    WHERE symbol = :symbol
                    AND ABS(timestamp - :timestamp) <= :tolerance_ms
                    ORDER BY ABS(timestamp - :timestamp) ASC
                    LIMIT 1
                """)
                
                tolerance_ms = tolerance_seconds * 1000
                result = await session.execute(
                    stmt,
                    {
                        "symbol": symbol,
                        "timestamp": timestamp,
                        "tolerance_ms": tolerance_ms,
                    }
                )
                row = result.fetchone()
                
                if row:
                    return self._row_to_state(row)
                return None
                
        except Exception as e:
            logger.error(f"Error getting macro state by timestamp: {e}", exc_info=True)
            return None
    
    async def get_history(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 10
    ) -> List[MacroState]:
        """
        Get macro state history
        
        Args:
            symbol: Trading symbol
            start_time: Start timestamp (milliseconds)
            end_time: End timestamp (milliseconds)
            limit: Maximum number of records
            
        Returns:
            List of MacroState
        """
        try:
            async with self._session_factory() as session:
                where_clauses = ["symbol = :symbol"]
                params = {"symbol": symbol}
                
                if start_time is not None:
                    where_clauses.append("timestamp >= :start_time")
                    params["start_time"] = start_time
                
                if end_time is not None:
                    where_clauses.append("timestamp <= :end_time")
                    params["end_time"] = end_time
                
                params["limit"] = limit
                
                stmt = text(f"""
                    SELECT * FROM macro_states
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY timestamp DESC
                    LIMIT :limit
                """)
                
                result = await session.execute(stmt, params)
                rows = result.fetchall()
                
                return [self._row_to_state(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error getting macro history: {e}", exc_info=True)
            return []
    
    async def compare_states(
        self,
        state1: MacroState,
        state2: MacroState
    ) -> Dict:
        """
        Compare two macro states
        
        Args:
            state1: First state
            state2: Second state
            
        Returns:
            Dictionary of differences
        """
        changes = {}
        
        # Compare trend
        if state1.trend_direction != state2.trend_direction:
            changes["trend_direction"] = {
                "old": state1.trend_direction,
                "new": state2.trend_direction,
            }
        
        # Compare market regime
        if state1.market_regime != state2.market_regime:
            changes["market_regime"] = {
                "old": state1.market_regime,
                "new": state2.market_regime,
            }
        
        # Compare sentiment
        if state1.overall_sentiment != state2.overall_sentiment:
            changes["overall_sentiment"] = {
                "old": state1.overall_sentiment,
                "new": state2.overall_sentiment,
            }
        
        # Compare sentiment score
        score_change = state2.sentiment_score - state1.sentiment_score
        if abs(score_change) > 10:
            changes["sentiment_score_change"] = score_change
        
        # Compare confidence
        if state1.confidence != state2.confidence:
            changes["confidence"] = {
                "old": state1.confidence,
                "new": state2.confidence,
            }
        
        return changes
    
    async def delete_old_states(self, days_to_keep: int = 30) -> int:
        """
        Delete old macro states
        
        Args:
            days_to_keep: Number of days to keep
            
        Returns:
            Number of deleted records
        """
        try:
            async with self._session_factory() as session:
                cutoff_time = int(
                    (datetime.now() - timedelta(days=days_to_keep)).timestamp() * 1000
                )
                
                stmt = text("""
                    DELETE FROM macro_states
                    WHERE timestamp < :cutoff_time
                """)
                
                result = await session.execute(stmt, {"cutoff_time": cutoff_time})
                await session.commit()
                
                deleted_count = result.rowcount if hasattr(result, 'rowcount') else 0
                logger.info(f"Deleted {deleted_count} old macro states")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Error deleting old macro states: {e}", exc_info=True)
            return 0
    
    async def get_statistics(self, symbol: str) -> Dict:
        """
        Get storage statistics for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary of statistics
        """
        try:
            async with self._session_factory() as session:
                # Get count
                count_stmt = text("""
                    SELECT COUNT(*) as count FROM macro_states WHERE symbol = :symbol
                """)
                count_result = await session.execute(count_stmt, {"symbol": symbol})
                count_row = count_result.fetchone()
                count = count_row[0] if count_row else 0
                
                # Get latest timestamp
                latest_stmt = text("""
                    SELECT MAX(timestamp) as latest FROM macro_states WHERE symbol = :symbol
                """)
                latest_result = await session.execute(latest_stmt, {"symbol": symbol})
                latest_row = latest_result.fetchone()
                latest_timestamp = latest_row[0] if latest_row else None
                
                # Get trend distribution
                trend_stmt = text("""
                    SELECT trend_direction, COUNT(*) as count
                    FROM macro_states
                    WHERE symbol = :symbol
                    GROUP BY trend_direction
                """)
                trend_result = await session.execute(trend_stmt, {"symbol": symbol})
                trend_distribution = {
                    row[0]: row[1] for row in trend_result.fetchall()
                }
                
                return {
                    "total_records": count,
                    "latest_timestamp": latest_timestamp,
                    "trend_distribution": trend_distribution,
                }
                
        except Exception as e:
            logger.error(f"Error getting macro statistics: {e}", exc_info=True)
            return {}
    
    def _row_to_state(self, row) -> MacroState:
        """Convert database row to MacroState"""
        return MacroState(
            symbol=row[1],
            timestamp=row[2],
            trend_direction=row[3],
            trend_strength=row[4],
            market_regime=row[5],
            overall_sentiment=row[6],
            sentiment_score=row[7],
            major_events=json.loads(row[8]) if row[8] else [],
            agent_recommendation=json.loads(row[9]) if row[9] else {},
            confidence=row[10],
            analysis_duration=row[11],
        )


# Global instance
_macro_storage: Optional[MacroStorage] = None


def get_macro_storage() -> MacroStorage:
    """Get global macro storage instance"""
    global _macro_storage
    if _macro_storage is None:
        _macro_storage = MacroStorage()
    return _macro_storage


def reset_macro_storage() -> None:
    """Reset global macro storage (for testing)"""
    global _macro_storage
    _macro_storage = None