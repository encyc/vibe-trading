"""
On Bar Thread

K-line triggered main trading thread using full coordinator.
"""
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime

from vibe_trading.coordinator.trading_coordinator import (
    TradingCoordinator,
    TradingDecision,
)
from vibe_trading.coordinator.thread_manager import ThreadManager, get_thread_manager
from vibe_trading.agents.messaging import get_message_broker, MessageType
from vibe_trading.websocket_manager import get_websocket_manager
from vibe_trading.data_sources.binance_client import BinanceClient, Kline, KlineInterval
from vibe_trading.config.binance_config import BinanceConfig, BinanceEnvironment
from vibe_trading.execution.order_executor import OrderExecutor
from pi_logger import get_logger, info

logger = logging.getLogger(__name__)
log = get_logger("OnBarThread")


def _kline_data_environment() -> "BinanceEnvironment":
    """选行情端点：mainnet 被网络/代理挡住时用 testnet 的行情源。

    端点本身不涉及资金，paper 模式下用哪边只是"能不能连上"的问题。
    可用 BINANCE_KLINE_ENV=testnet|mainnet 显式指定。
    """
    import os

    choice = os.getenv("BINANCE_KLINE_ENV", "").strip().lower()
    if choice == "testnet":
        return BinanceEnvironment.TESTNET
    if choice == "mainnet":
        return BinanceEnvironment.MAINNET
    return BinanceEnvironment.MAINNET


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
        executor: Optional[OrderExecutor] = None,
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
        self.executor = executor
        
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
        #: 最近一次已处理 bar 的 open_time（毫秒），用于 WS / REST 双通道去重
        self._last_handled_open_time: Optional[int] = None
        
        logger.info(f"OnBarThread initialized for {symbol} ({interval})")
    
    async def initialize(self) -> None:
        """Initialize the thread"""
        # Initialize coordinator with full agent team
        from vibe_trading.memory.memory import create_memory_from_settings

        self._coordinator = TradingCoordinator(
            symbol=self.symbol,
            interval=self.interval,
            executor=self.executor,
            memory=create_memory_from_settings(),
        )
        await self._coordinator.initialize()
        
        logger.info("OnBarThread initialized with full agent team")

    async def _get_positions(self) -> list[dict]:
        """Read current positions through the configured executor."""
        if not self.executor:
            return []
        positions = await self.executor.get_positions()
        return [
            {
                "symbol": pos.symbol,
                "position_amount": pos.position_amount,
                "entry_price": pos.entry_price,
                "mark_price": pos.mark_price,
                "unrealized_profit": pos.unrealized_profit,
                "liquidation_price": pos.liquidation_price,
                "leverage": pos.leverage,
                "position_side": pos.position_side.value,
                "notional": pos.notional,
            }
            for pos in positions
        ]

    async def _get_account_balance(self) -> float:
        """Read available USDT balance through the configured executor."""
        if not self.executor:
            return 10000.0
        balances = await self.executor.get_balance()
        usdt = balances.get("USDT", 10000.0)
        if isinstance(usdt, dict):
            return float(usdt.get("available", usdt.get("balance", 10000.0)))
        return float(usdt)
    
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
            config = BinanceConfig(environment=_kline_data_environment())
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
                info("未获取到历史K线数据", tag="OnBar")
                return

            # 推送到 web server
            from vibe_trading.web.server import state

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
            await state.send_update("init", {
                "klines": state.klines,
                "indicators": state.indicators,
                "decisions": state.decisions,
                "logs": state.logs[-100:],
                "executions": state.executions[-100:],
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

            # Keep running while thread is active.
            # WebSocket 可能在订阅后立刻失败（代理/网络/端点问题），所以这里并行跑一个
            # REST 轮询兜底：WS 收不到数据时仍然按 bar 收盘推进。
            poll_task = asyncio.create_task(self._rest_poll_loop())
            try:
                while self._running:
                    await asyncio.sleep(1)
            finally:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass

        except asyncio.CancelledError:
            logger.info("OnBarThread cancelled")
        except Exception as e:
            logger.error(f"Error in OnBarThread loop: {e}", exc_info=True)
        finally:
            # Stop WebSocket
            if 'ws_manager' in locals():
                await ws_manager.stop()

    async def _rest_poll_loop(self) -> None:
        """REST 轮询兜底：WS 不可用时用已收盘的 K 线推进决策流程。

        只在检测到 WS 长时间没有新 bar 时才启动工作，避免与 WS 重复处理同一根 bar。
        每根 bar 只处理一次（按 open_time 去重）。
        """
        interval_seconds = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900,
            "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
        }.get(self.interval, 1800)
        poll_every = min(interval_seconds, 30)
        seen_open_time = self._last_handled_open_time

        config = BinanceConfig(environment=_kline_data_environment())
        client = BinanceClient(config)
        interval_enum = {
            "1m": KlineInterval.MINUTE_1,
            "5m": KlineInterval.MINUTE_5,
            "15m": KlineInterval.MINUTE_15,
            "30m": KlineInterval.MINUTE_30,
            "1h": KlineInterval.HOUR_1,
            "4h": KlineInterval.HOUR_4,
            "1d": KlineInterval.DAY_1,
        }.get(self.interval, KlineInterval.MINUTE_30)

        info(f"REST 轮询兜底已启动（每 {poll_every}s 检查一次已收盘 bar）", tag="OnBar")

        while self._running:
            await asyncio.sleep(poll_every)
            try:
                bars = await client.rest.get_klines(
                    symbol=self.symbol, interval=interval_enum, limit=2
                )
                if not bars:
                    continue
                # 倒数第二根是刚收盘的那根（最后一根还在走）
                last_closed = bars[-2] if len(bars) >= 2 else None
                if last_closed is None:
                    continue
                open_time = int(last_closed[0])
                if seen_open_time is not None and open_time <= seen_open_time:
                    continue
                seen_open_time = open_time
                kline = Kline.from_rest(last_closed)
                kline.symbol = self.symbol
                kline.interval = self.interval
                info(f"REST 取到已收盘 bar {kline.open_datetime}", tag="OnBar")
                await self._process_kline(kline)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # 网络抖动不应终止轮询
                logger.warning(f"REST 轮询失败（继续重试）: {type(exc).__name__}: {exc}")

    
    async def _process_kline(self, kline) -> None:
        """
        Process K-line data

        Args:
            kline: K-line data
        """
        # WS 与 REST 双通道可能送来同一根 bar：按 open_time 去重，只处理一次
        open_time_ms = int(kline.open_time)
        if (
            self._last_handled_open_time is not None
            and open_time_ms <= self._last_handled_open_time
        ):
            logger.debug(f"跳过重复 bar open_time={open_time_ms}")
            return
        self._last_handled_open_time = open_time_ms

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
            positions = await self._get_positions()
            account_balance = await self._get_account_balance()
            decision = await self._coordinator.analyze_and_decide(
                current_price=close_price,
                account_balance=account_balance,
                current_positions=positions,
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
            positions = await self._get_positions()
            account_balance = await self._get_account_balance()
            decision = await self._coordinator.analyze_and_decide(
                current_price=price,
                account_balance=account_balance,
                current_positions=positions,
            )
            
            logger.info(f"Decision: {decision.decision}")
            return decision.to_dict()
            
        except Exception as e:
            logger.error(f"Error running OnBarThread once: {e}", exc_info=True)
            return None
