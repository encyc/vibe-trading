"""
Multi-threaded Trading System Main Entry Point

Launches and manages all threads:
1. Macro Analysis Thread (1h polling)
2. On Bar Thread (K-line triggered)
3. Event Driven Thread (Trigger monitoring)
"""
import asyncio
import logging
import signal
from typing import Dict, Optional

from pi_logger import get_logger, info, success, warning, separator

from vibe_trading.coordinator.thread_manager import ThreadManager, get_thread_manager
from vibe_trading.coordinator.shared_state import SharedStateManager, get_shared_state_manager
from vibe_trading.coordinator.event_queue import EventQueue, get_event_queue
from vibe_trading.coordinator.emergency_handler import EmergencyHandler
from vibe_trading.threads.macro_thread import MacroAnalysisThread
from vibe_trading.threads.onbar_thread import OnBarThread
from vibe_trading.triggers.trigger_registry import TriggerRegistry, get_trigger_registry
from vibe_trading.triggers.price_triggers import (
    PriceDropTrigger,
    PriceSpikeTrigger,
)
from vibe_trading.triggers.risk_triggers import (
    MarginRatioTrigger,
    DrawdownTrigger,
)

logger = logging.getLogger(__name__)
log = get_logger("MultiThreadMain")


class MultiThreadedTradingSystem:
    """
    Multi-threaded trading system
    
    Manages all threads and their lifecycle.
    """
    
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "30m",
    ):
        """
        Initialize multi-threaded trading system
        
        Args:
            symbol: Trading symbol
            interval: Time interval for On Bar thread
        """
        self.symbol = symbol
        self.interval = interval
        
        # Core components
        self.thread_manager = get_thread_manager()
        self.shared_state = get_shared_state_manager()
        self.event_queue = get_event_queue()
        self.trigger_registry = get_trigger_registry()
        
        # Threads
        self.macro_thread: Optional[MacroAnalysisThread] = None
        self.onbar_thread: Optional[OnBarThread] = None
        self.event_thread: Optional[asyncio.Task] = None
        
        # Emergency handler
        self.emergency_handler: Optional[EmergencyHandler] = None
        
        # State
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        log.info(f"MultiThreadedTradingSystem initialized for {symbol}")
    
    async def initialize(self) -> None:
        """Initialize all components"""
        info("Initializing multi-threaded trading system...", tag="INIT")
        
        # Initialize shared state cleanup task
        await self.shared_state.start_cleanup_task(interval_seconds=60)
        
        # Initialize macro thread
        self.macro_thread = MacroAnalysisThread(
            symbol=self.symbol,
            interval_seconds=3600,  # 1 hour
        )
        await self.macro_thread.initialize()
        
        # Initialize On Bar thread
        self.onbar_thread = OnBarThread(
            symbol=self.symbol,
            interval=self.interval,
            thread_manager=self.thread_manager,
        )
        await self.onbar_thread.initialize()
        
        # Initialize emergency handler
        self.emergency_handler = EmergencyHandler(
            thread_manager=self.thread_manager,
            shared_state=self.shared_state,
            event_queue=self.event_queue,
        )
        await self.emergency_handler.initialize(symbol=self.symbol)
        
        # Register default triggers
        await self._register_default_triggers()
        
        success("System initialization complete")
    
    async def _register_default_triggers(self) -> None:
        """Register default triggers"""
        info("Registering default triggers...", tag="TRIGGERS")
        
        # Price triggers
        price_drop = PriceDropTrigger(
            threshold_pct=0.03,
            symbol=self.symbol,
        )
        self.trigger_registry.register(price_drop)
        
        price_spike = PriceSpikeTrigger(
            threshold_pct=0.03,
            symbol=self.symbol,
        )
        self.trigger_registry.register(price_spike)
        
        # Risk triggers
        margin_trigger = MarginRatioTrigger(threshold_ratio=0.5)
        self.trigger_registry.register(margin_trigger)
        
        drawdown_trigger = DrawdownTrigger(threshold_drawdown=0.2)
        self.trigger_registry.register(drawdown_trigger)
        
        log.info(f"Registered {len(self.trigger_registry.get_all())} triggers")
    
    async def start(self) -> None:
        """Start all threads"""
        if self._running:
            warning("System already running")
            return
        
        self._running = True
        info("Starting multi-threaded trading system...", tag="START")
        
        # Register threads with thread manager
        await self.thread_manager.register_thread(
            name="macro_thread",
            coroutine=self.macro_thread.start,
        )
        
        await self.thread_manager.register_thread(
            name="onbar_thread",
            coroutine=self.onbar_thread.start,
        )
        
        # Start macro thread
        await self.thread_manager.start_thread("macro_thread")
        await self.thread_manager.run_thread(
            "macro_thread",
            self.macro_thread.start,
        )
        
        # Start On Bar thread
        await self.thread_manager.start_thread("onbar_thread")
        await self.thread_manager.run_thread(
            "onbar_thread",
            self.onbar_thread.start,
        )
        
        # Start event thread
        self.event_thread = asyncio.create_task(self._run_event_thread())
        
        success("All threads started")
        
        # Print system status
        await self._print_system_status()
    
    async def _run_event_thread(self) -> None:
        """Run event thread"""
        log.info("Starting event thread")
        
        while self._running:
            try:
                # Process event queue
                await self.emergency_handler.process_event_queue()
                
                # Check triggers periodically
                await self._check_triggers()
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in event thread: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    async def _check_triggers(self) -> None:
        """Check all triggers"""
        # This would build trigger context and evaluate triggers
        # For now, it's a placeholder
        pass
    
    async def stop(self) -> None:
        """Stop all threads"""
        if not self._running:
            warning("System not running")
            return
        
        info("Stopping multi-threaded trading system...", tag="STOP")
        
        self._running = False
        self._shutdown_event.set()
        
        # Cancel event thread
        if self.event_thread:
            self.event_thread.cancel()
            try:
                await self.event_thread
            except asyncio.CancelledError:
                pass
        
        # Stop macro thread
        if self.macro_thread:
            await self.macro_thread.stop()
        
        # Stop On Bar thread
        if self.onbar_thread:
            await self.onbar_thread.stop()
        
        # Stop shared state cleanup
        await self.shared_state.stop_cleanup_task()
        
        success("All threads stopped")
    
    async def _print_system_status(self) -> None:
        """Print system status"""
        separator("=", 60)
        info("SYSTEM STATUS", tag="STATUS")
        separator("-", 60)
        
        # Thread manager stats
        thread_stats = await self.thread_manager.get_statistics()
        log.info(f"Thread Manager: {thread_stats['total_threads']} threads")
        
        # Macro thread stats
        if self.macro_thread:
            macro_stats = self.macro_thread.get_statistics()
            log.info(f"Macro Thread: {macro_stats['total_runs']} runs")
        
        # On Bar thread stats
        if self.onbar_thread:
            onbar_stats = self.onbar_thread.get_statistics()
            log.info(f"On Bar Thread: {onbar_stats['total_bars']} bars")
        
        # Trigger registry stats
        trigger_stats = self.trigger_registry.get_statistics()
        log.info(f"Triggers: {trigger_stats.total_triggers} registered")
        
        # Emergency handler stats
        if self.emergency_handler:
            emergency_stats = self.emergency_handler.get_statistics()
            log.info(f"Emergency Handler: {emergency_stats['total_handled']} handled")
        
        # Shared state stats
        state_stats = await self.shared_state.get_statistics()
        log.info(f"Shared State: {state_stats['total_keys']} keys")
        
        # Event queue stats
        queue_stats = await self.event_queue.get_statistics()
        log.info(f"Event Queue: {queue_stats['queue_size']} pending")
        
        separator("=", 60)
    
    async def run(self) -> None:
        """Run the system (blocking)"""
        await self.initialize()
        await self.start()
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
        
        # Stop system
        await self.stop()
    
    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            log.info(f"Received signal {signum}, initiating shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Main entry point"""
    log.info("Starting Vibe Trading Multi-Threaded System")
    separator("=", 60)
    
    # Create system
    system = MultiThreadedTradingSystem(
        symbol="BTCUSDT",
        interval="30m",
    )
    
    # Setup signal handlers
    system.setup_signal_handlers()
    
    try:
        # Run system
        await system.run()
    except KeyboardInterrupt:
        log.info("Keyboard interrupt received")
        await system.stop()
    except Exception as e:
        log.error(f"Fatal error: {e}", exc_info=True)
        await system.stop()
    
    log.info("System shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())