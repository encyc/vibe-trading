"""
On Bar Thread

K-line triggered main trading thread using full coordinator.
"""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime

from vibe_trading.coordinator.trading_coordinator import (
    TradingCoordinator,
    TradingDecision,
)
from vibe_trading.coordinator.thread_manager import ThreadManager, get_thread_manager
from vibe_trading.agents.messaging import get_message_broker, MessageType
from vibe_trading.websocket_manager import get_websocket_manager
from vibe_trading.data_sources.binance_client import BinanceClient, KlineInterval
from vibe_trading.config.binance_config import BinanceConfig, BinanceEnvironment
from vibe_trading.config.settings import get_settings
from pi_logger import get_logger, info

logger = logging.getLogger(__name__)
log = get_logger("OnBarThread")


class OnBarThread:
    """
    On Bar thread
    
    Subscribes to K-line data and executes full 5-phase decision flow.
    """
    
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "30m",
        thread_manager: Optional[ThreadManager] = None,
    ):
        """
        Initialize On Bar thread
        
        Args:
            symbol: Trading symbol
            interval: Time interval
            thread_manager: Thread manager instance
        """
        self.symbol = symbol
        self.interval = interval
        self.thread_manager = thread_manager or get_thread_manager()
        
        # Coordinator
        self._coordinator: Optional[TradingCoordinator] = None
        
        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._emergency_mode = False
        
        # Statistics
        self._total_bars = 0
        self._decisions_made = 0
        self._emergency_stops = 0
        self._last_bar_time: Optional[datetime] = None
        
        logger.info(f"OnBarThread initialized for {symbol} ({interval})")
    
    async def initialize(self) -> None:
        """Initialize the thread"""
        # Initialize coordinator with full agent team
        self._coordinator = TradingCoordinator(
            symbol=self.symbol,
            interval=self.interval,
        )
        await self._coordinator.initialize()
        
        logger.info("OnBarThread initialized with full agent team")
    
    async def start(self) -> None:
        """Start the On Bar thread"""
        if self._running:
            logger.warning("OnBarThread already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("OnBarThread started")
    
    async def stop(self) -> None:
        """Stop the On Bar thread"""
        if not self._running:
            logger.warning("OnBarThread not running")
            return
        
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("OnBarThread stopped")

    async def _load_historical_klines_to_web(self, limit: int = 100) -> None:
        """从 Binance API 获取历史K线并推送到 web server"""
        try:
            info(f"获取历史K线: {self.symbol} {self.interval} ({limit}根)", tag="OnBar")

            # 使用实盘配置（获取真实市场数据，不需要API密钥）
            config = BinanceConfig(environment=BinanceEnvironment.MAINNET)
            client = BinanceClient(config)

            # 获取 K线 interval 枚举
            interval_map = {
                "1m": KlineInterval.MINUTE_1,
                "5m": KlineInterval.MINUTE_5,
                "15m": KlineInterval.MINUTE_15,
                "30m": KlineInterval.MINUTE_30,
                "1h": KlineInterval.HOUR_1,
                "4h": KlineInterval.HOUR_4,
                "1d": KlineInterval.DAY_1,
            }
            kline_interval = interval_map.get(self.interval, KlineInterval.MINUTE_30)

            # 获取历史K线（通过 rest 客户端）
            raw_klines = await client.rest.get_klines(
                symbol=self.symbol,
                interval=kline_interval,
                limit=limit,
            )

            if not raw_klines:
                info(f"未获取到历史K线数据", tag="OnBar")
                return

            # 推送到 web server
            from vibe_trading.web.server import send_kline, state

            # 清空 web state 的旧数据
            state.klines = []
            state.current_symbol = self.symbol
            state.current_interval = self.interval

            # 推送每根K线
            for raw in raw_klines:
                open_time = raw[0]  # 开盘时间 (毫秒)
                bar_time_iso = datetime.fromtimestamp(open_time / 1000).isoformat()

                kline_data = {
                    "time": bar_time_iso,
                    "open_time_ms": int(open_time),
                    "symbol": self.symbol,
                    "interval": self.interval,
                    "open": float(raw[1]),
                    "high": float(raw[2]),
                    "low": float(raw[3]),
                    "close": float(raw[4]),
                    "volume": float(raw[5]),
                }

                # 直接添加到 state（不通过 POST API）
                state.klines.append(kline_data)

            info(f"已加载 {len(state.klines)} 根历史K线到 web", tag="OnBar")

            # 计算技术指标
            from vibe_trading.web.server import calculate_indicators
            await calculate_indicators()

            # 通知前端刷新
            from vibe_trading.web.server import ConnectionState
            await state.send_update("init", {
                "klines": state.klines,
                "indicators": state.indicators,
                "decisions": state.decisions,
                "logs": state.logs[-100:],
                "phase_status": state.phase_status,
                "agent_reports": state.agent_reports,
            })

            # 关闭客户端
            await client.close()

        except Exception as e:
            log.error(f"获取历史K线失败: {e}", exc_info=True)

    async def _run_loop(self) -> None:
        """Main loop for K-line processing"""
        try:
            # 获取历史K线数据并推送到 web（初始化显示）
            await self._load_historical_klines_to_web()

            # Get WebSocket manager - 使用实盘数据流（不需要API密钥）
            ws_manager = get_websocket_manager(
                api_key=None,
                api_secret=None,
                testnet=False,  # 实盘数据
            )

            # Subscribe to K-line stream
            await ws_manager.subscribe_kline(
                symbol=self.symbol,
                interval=self.interval,
                callback=self._process_kline,
            )

            # Start WebSocket
            await ws_manager.start()

            # Keep running while thread is active
            while self._running:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("OnBarThread cancelled")
        except Exception as e:
            logger.error(f"Error in OnBarThread loop: {e}", exc_info=True)
        finally:
            # Stop WebSocket
            if 'ws_manager' in locals():
                await ws_manager.stop()
    
    async def _process_kline(self, kline) -> None:
        """
        Process K-line data

        Args:
            kline: K-line data
        """
        self._total_bars += 1
        self._last_bar_time = datetime.now()

        # Extract price
        close_price = float(kline.close)

        logger.debug(f"Processing K-line: {self.symbol} @ ${close_price:.2f}")

        # 发送K线数据到Web (忽略错误，Web可能未启动)
        try:
            from vibe_trading.web.server import send_kline, send_log
            bar_time_iso = datetime.fromtimestamp(kline.open_time / 1000).isoformat()
            await send_kline({
                "time": bar_time_iso,
                "open_time_ms": int(kline.open_time),
                "symbol": self.symbol,
                "interval": self.interval,
                "open": float(kline.open),
                "high": float(kline.high),
                "low": float(kline.low),
                "close": close_price,
                "volume": float(kline.volume),
            })
        except Exception:
            pass  # Web服务器未启动时忽略

        try:
            # 发送日志到Web
            from vibe_trading.web.server import send_log, send_phase
            await send_log(
                "info",
                "OnBar",
                f"处理K线: {self.symbol} @ ${close_price:.2f}",
                open_time_ms=int(kline.open_time),
                symbol=self.symbol,
                interval=self.interval,
            )
            await send_phase(
                "ANALYZING",
                "running",
                open_time_ms=int(kline.open_time),
                symbol=self.symbol,
                interval=self.interval,
            )

            # Execute full 5-phase decision flow with all 13 agents
            decision = await self._coordinator.analyze_and_decide(
                current_price=close_price,
                account_balance=10000.0,  # Would get from account
                current_positions=[],  # Would get from position manager
                bar_open_time_ms=int(kline.open_time),
            )

            self._decisions_made += 1

            # Log decision
            logger.info(
                f"Decision: {decision.decision} - {decision.rationale[:100]}..."
            )

            # 发送决策到Web
            try:
                from vibe_trading.web.server import send_decision
                await send_decision({
                    "index": self._decisions_made,
                    "time": datetime.fromtimestamp(kline.open_time / 1000).isoformat(),
                    "open_time_ms": int(kline.open_time),
                    "symbol": self.symbol,
                    "interval": self.interval,
                    "close": close_price,
                    "decision": decision.decision,
                    "rationale": decision.rationale,
                })
                await send_log(
                    "info",
                    "Decision",
                    f"决策: {decision.decision}",
                    open_time_ms=int(kline.open_time),
                    symbol=self.symbol,
                    interval=self.interval,
                )
                await send_phase(
                    "COMPLETED",
                    "completed",
                    open_time_ms=int(kline.open_time),
                    symbol=self.symbol,
                    interval=self.interval,
                )
            except Exception:
                pass  # Web服务器未启动时忽略

            # Send message
            message_broker = get_message_broker()
            message_broker.send(
                sender="onbar_thread",
                receiver="all",
                message_type=MessageType.INFO,
                content={
                    "type": "trading_decision",
                    "symbol": self.symbol,
                    "decision": decision.decision,
                    "price": close_price,
                },
                correlation_id=f"onbar_{int(datetime.now().timestamp() * 1000)}",
            )

            # Execute trade if needed
            if decision.decision in ["BUY", "SELL", "STRONG_BUY", "STRONG_SELL"]:
                await self._execute_trade(decision)

        except Exception as e:
            logger.error(f"Error in decision flow: {e}", exc_info=True)
            # 发送错误日志到Web
            try:
                from vibe_trading.web.server import send_log
                await send_log(
                    "error",
                    "OnBar",
                    f"决策流程错误: {e}",
                    open_time_ms=int(kline.open_time),
                    symbol=self.symbol,
                    interval=self.interval,
                )
            except Exception:
                pass
    
    async def _execute_trade(self, decision: TradingDecision) -> None:
        """
        Execute trading decision
        
        Args:
            decision: Trading decision
        """
        logger.info(f"Executing trade: {decision.decision}")
        
        # TODO: Implement actual trade execution
        # This would integrate with OrderExecutor
        
        # For now, just log
        logger.info(f"Trade execution placeholder: {decision.decision}")
    
    async def _is_emergency_mode(self) -> bool:
        """
        Check if system is in emergency mode
        
        Returns:
            True if in emergency mode
        """
        return await self.thread_manager.is_emergency_mode()
    
    async def _handle_emergency_message(self, message) -> None:
        """
        Handle emergency message
        
        Args:
            message: Emergency message
        """
        content = message.content
        action = content.get("action")
        
        if action == "emergency_stop":
            logger.warning("Received emergency stop command")
            self._emergency_mode = True
        elif action == "emergency_resume":
            logger.info("Received emergency resume command")
            self._emergency_mode = False
        elif action == "emergency_suggestion":
            logger.info(f"Received emergency suggestion: {content.get('suggestion')}")
            # Handle suggestion
    
    def get_statistics(self) -> Dict:
        """
        Get thread statistics
        
        Returns:
            Dictionary of statistics
        """
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "running": self._running,
            "emergency_mode": self._emergency_mode,
            "total_bars": self._total_bars,
            "decisions_made": self._decisions_made,
            "emergency_stops": self._emergency_stops,
            "decision_rate": (
                self._decisions_made / self._total_bars
                if self._total_bars > 0 else 0.0
            ),
            "last_bar_time": (
                self._last_bar_time.isoformat()
                if self._last_bar_time else None
            ),
        }
    
    async def run_once(self, price: float) -> Optional[Dict]:
        """
        Run decision flow once (for testing)
        
        Args:
            price: Current price
            
        Returns:
            Decision or None if failed
        """
        try:
            logger.info(f"Running OnBarThread once for {self.symbol} @ ${price:.2f}")
            
            # Execute full 5-phase decision flow with all 13 agents
            decision = await self._coordinator.analyze_and_decide(
                current_price=price,
                account_balance=10000.0,
                current_positions=[],
            )
            
            logger.info(f"Decision: {decision.decision}")
            return decision.to_dict()
            
        except Exception as e:
            logger.error(f"Error running OnBarThread once: {e}", exc_info=True)
            return None
