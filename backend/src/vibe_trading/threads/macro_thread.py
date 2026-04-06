"""
Macro Analysis Thread

Runs macro analysis on a periodic basis (every hour).
"""
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime
import time

from vibe_trading.agents.macro_agent import MacroAnalysisAgent
from vibe_trading.data_sources.macro_storage import MacroStorage, get_macro_storage
from vibe_trading.agents.agent_factory import ToolContext
from vibe_trading.agents.messaging import get_message_broker, MessageType
from vibe_trading.tools import sentiment_tools, fundamental_tools, market_data_tools

logger = logging.getLogger(__name__)


class MacroAnalysisThread:
    """
    Macro analysis thread
    
    Runs periodically to analyze the macro environment and update the macro state.
    """
    
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval_seconds: int = 3600,  # 1 hour
        storage: Optional[MacroStorage] = None,
    ):
        """
        Initialize macro analysis thread
        
        Args:
            symbol: Trading symbol to analyze
            interval_seconds: Analysis interval in seconds
            storage: Macro storage instance
        """
        self.symbol = symbol
        self.interval_seconds = interval_seconds
        self.storage = storage or get_macro_storage()
        
        # Initialize agent
        self._agent: Optional[MacroAnalysisAgent] = None
        self._tool_context: Optional[ToolContext] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Statistics
        self._total_runs = 0
        self._successful_runs = 0
        self._failed_runs = 0
        self._last_run_time: Optional[datetime] = None
        
        logger.info(f"MacroAnalysisThread initialized for {symbol} (interval={interval_seconds}s)")
    
    async def initialize(self) -> None:
        """Initialize the thread"""
        # Initialize storage
        await self.storage.init()

        # Create tool context
        self._tool_context = ToolContext(
            symbol=self.symbol,
            interval="1h",
        )

        # Initialize macro agent
        self._agent = MacroAnalysisAgent()
        await self._agent.initialize(self._tool_context, enable_streaming=False)

        logger.info("MacroAnalysisThread initialized")
    
    async def start(self) -> None:
        """Start the macro analysis thread"""
        if self._running:
            logger.warning("MacroAnalysisThread already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("MacroAnalysisThread started")
    
    async def stop(self) -> None:
        """Stop the macro analysis thread"""
        if not self._running:
            logger.warning("MacroAnalysisThread not running")
            return
        
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("MacroAnalysisThread stopped")
    
    async def _run_loop(self) -> None:
        """Main loop for macro analysis"""
        while self._running:
            try:
                # Check if should run
                should_run = await self._should_update()
                
                if should_run:
                    await self._run_analysis()
                else:
                    logger.debug("Skipping macro analysis (already up to date)")
                
                # Wait for next interval
                await asyncio.sleep(self.interval_seconds)
                
            except asyncio.CancelledError:
                logger.info("MacroAnalysisThread cancelled")
                break
            except Exception as e:
                logger.error(f"Error in macro analysis loop: {e}", exc_info=True)
                self._failed_runs += 1
                await asyncio.sleep(60)  # Wait 1 minute before retry
    
    async def _should_update(self) -> bool:
        """
        Check if macro analysis should be updated
        
        Returns:
            True if update is needed
        """
        # Get latest state
        latest_state = await self.storage.get_latest_state(self.symbol)
        
        if latest_state is None:
            return True
        
        # Check if latest state is older than interval
        latest_timestamp = latest_state.timestamp / 1000  # Convert to seconds
        current_timestamp = time.time()
        
        time_since_last = current_timestamp - latest_timestamp
        
        return time_since_last >= self.interval_seconds
    
    async def _run_analysis(self) -> None:
        """Run macro analysis"""
        start_time = time.time()
        
        try:
            self._total_runs += 1
            logger.info(f"Starting macro analysis for {self.symbol}")
            
            # Collect market data
            market_data = await self._collect_market_data()
            
            # Perform analysis
            analysis = await self._agent.analyze(market_data)
            
            # Create macro state
            analysis_duration = time.time() - start_time
            macro_state = await self._agent.create_macro_state(
                symbol=self.symbol,
                analysis=analysis,
                analysis_duration=analysis_duration,
            )
            
            # Save to storage
            saved = await self.storage.save_state(macro_state)
            
            if saved:
                self._successful_runs += 1
                self._last_run_time = datetime.now()
                
                logger.info(
                    f"Macro analysis completed: {macro_state.market_regime} "
                    f"(trend={macro_state.trend_direction}, "
                    f"sentiment={macro_state.overall_sentiment}, "
                    f"confidence={macro_state.confidence:.2f})"
                )
                
                # Notify other threads
                await self._notify_update(macro_state)
            else:
                self._failed_runs += 1
                logger.error("Failed to save macro state")
            
        except Exception as e:
            self._failed_runs += 1
            logger.error(f"Error running macro analysis: {e}", exc_info=True)
    
    async def _collect_market_data(self) -> Dict:
        """
        Collect market data for macro analysis
        
        Returns:
            Dictionary of market data
        """
        market_data = {
            "symbol": self.symbol,
        }
        
        try:
            # Get fear/greed index
            fg_data = await sentiment_tools.get_fear_and_greed_index()
            market_data["fear_greed"] = fg_data
            logger.debug("Collected fear/greed index")
        except Exception as e:
            logger.warning(f"Failed to get fear/greed index: {e}")
        
        try:
            # Get funding rate
            fr_data = await fundamental_tools.get_funding_rates(self.symbol)
            market_data["funding_rate"] = fr_data
            logger.debug("Collected funding rate")
        except Exception as e:
            logger.warning(f"Failed to get funding rate: {e}")
        
        try:
            # Get 24h ticker
            ticker_data = await market_data_tools.get_24hr_ticker(self.symbol)
            market_data["ticker_24h"] = ticker_data
            logger.debug("Collected 24h ticker")
        except Exception as e:
            logger.warning(f"Failed to get 24h ticker: {e}")
        
        try:
            # Get trending symbols
            trending_data = await sentiment_tools.get_trending_symbols()
            market_data["trending"] = trending_data
            logger.debug("Collected trending symbols")
        except Exception as e:
            logger.warning(f"Failed to get trending symbols: {e}")
        
        return market_data
    
    async def _notify_update(self, macro_state) -> None:
        """
        Notify other threads of macro state update
        
        Args:
            macro_state: Updated macro state
        """
        message_broker = get_message_broker()
        
        message_broker.send(
            sender="macro_thread",
            receiver="all",
            message_type=MessageType.INFO,
            content={
                "type": "macro_state_update",
                "symbol": self.symbol,
                "state": macro_state.to_dict(),
            },
            correlation_id=f"macro_{int(time.time() * 1000)}",
        )
        
        logger.debug(f"Macro state update notified: {macro_state.market_regime}")
    
    def get_statistics(self) -> Dict:
        """
        Get thread statistics
        
        Returns:
            Dictionary of statistics
        """
        return {
            "symbol": self.symbol,
            "running": self._running,
            "interval_seconds": self.interval_seconds,
            "total_runs": self._total_runs,
            "successful_runs": self._successful_runs,
            "failed_runs": self._failed_runs,
            "success_rate": (
                self._successful_runs / self._total_runs
                if self._total_runs > 0 else 0.0
            ),
            "last_run_time": (
                self._last_run_time.isoformat()
                if self._last_run_time else None
            ),
        }
    
    async def run_once(self) -> Optional[Dict]:
        """
        Run macro analysis once (for testing or manual trigger)
        
        Returns:
            Macro state or None if failed
        """
        try:
            start_time = time.time()
            logger.info(f"Running macro analysis once for {self.symbol}")
            
            # Collect market data
            market_data = await self._collect_market_data()
            
            # Perform analysis
            analysis = await self._agent.analyze(market_data)
            
            # Create macro state
            analysis_duration = time.time() - start_time
            macro_state = await self._agent.create_macro_state(
                symbol=self.symbol,
                analysis=analysis,
                analysis_duration=analysis_duration,
            )
            
            # Save to storage
            saved = await self.storage.save_state(macro_state)
            
            if saved:
                logger.info(f"Macro analysis completed: {macro_state.market_regime}")
                return macro_state.to_dict()
            else:
                logger.error("Failed to save macro state")
                return None
            
        except Exception as e:
            logger.error(f"Error running macro analysis once: {e}", exc_info=True)
            return None