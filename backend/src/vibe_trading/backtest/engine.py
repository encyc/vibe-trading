"""
回测引擎核心

协调整个回测流程，管理数据加载、决策执行、指标计算和报告生成。
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pi_logger import get_logger

from vibe_trading.backtest.checkpoint import CheckpointManager, BacktestCheckpoint
from vibe_trading.backtest.data_loader import BacktestDataLoader, DataSource
from vibe_trading.backtest.executor import BacktestExecutor
from vibe_trading.backtest.llm_optimizer import LLMOptimizer
from vibe_trading.backtest.metrics import BacktestMetricsCalculator
from vibe_trading.backtest.models import (
    BacktestConfig,
    BacktestResult,
    LLMMode,
    ReportFormat,
)
from vibe_trading.backtest.reporter import BacktestReporter
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator
from vibe_trading.memory.memory import PersistentMemory

logger = get_logger(__name__)


class BacktestEngine:
    """
    回测引擎核心

    完整的回测流程：
    1. 加载历史数据
    2. 逐根K线执行决策和交易
    3. 计算性能指标
    4. 生成报告
    """

    def __init__(self, config: BacktestConfig):
        """
        初始化回测引擎

        Args:
            config: 回测配置
        """
        self.config = config

        # 初始化组件
        self.data_loader = BacktestDataLoader(default_source=DataSource.HYBRID)
        self.llm_optimizer = LLMOptimizer(mode=config.llm_mode)
        self.metrics_calculator = BacktestMetricsCalculator()
        self.reporter = BacktestReporter()

        # 检查点管理器
        self.checkpoint_manager: Optional[CheckpointManager] = None
        if config.save_checkpoints or config.resume_from_checkpoint:
            self.checkpoint_manager = CheckpointManager(checkpoint_dir=config.checkpoint_dir)

        # 延迟初始化（在run_backtest中）
        self.executor: Optional[BacktestExecutor] = None
        self.coordinator: Optional[TradingCoordinator] = None

    async def run_backtest(self) -> BacktestResult:
        """
        运行回测

        Returns:
            BacktestResult: 回测结果
        """
        started_at = datetime.now()
        logger.info(f"开始回测: {self.config.symbol} {self.config.interval}")
        logger.info(f"时间范围: {self.config.start_time} ~ {self.config.end_time}")
        logger.info(f"LLM模式: {self.config.llm_mode.value}")

        try:
            # 0. 尝试从检查点恢复
            start_index = 0
            if self.config.resume_from_checkpoint and self.checkpoint_manager:
                logger.info(f"从检查点恢复: {self.config.resume_from_checkpoint}")
                checkpoint = await self.checkpoint_manager.load_checkpoint(
                    self.config.resume_from_checkpoint
                )

                # 恢复执行器状态
                from vibe_trading.backtest.checkpoint import CheckpointManager

                # 创建临时manager来反序列化状态
                temp_manager = CheckpointManager()
                execution_state = temp_manager._deserialize_execution_state(
                    checkpoint.execution_state
                )

                # 初始化组件
                memory = PersistentMemory() if self.config.save_trades else None
                self.coordinator = TradingCoordinator(
                    symbol=self.config.symbol,
                    interval=self.config.interval,
                    memory=memory,
                )
                await self.coordinator.initialize()

                # 创建执行器并恢复状态
                self.executor = BacktestExecutor(
                    config=self.config,
                    coordinator=self.coordinator,
                )
                self.executor.state = execution_state
                start_index = checkpoint.current_kline_index

                logger.info(f"已从检查点恢复，从第 {start_index} 根K线继续")

            # 1. 计算技术指标所需的lookback
            from vibe_trading.data_sources.technical_indicators import TechnicalIndicators

            lookback_periods = TechnicalIndicators.get_required_lookback()
            logger.info(f"技术指标需要 {lookback_periods} 周期的lookback数据")

            # 2. 加载包含lookback的数据
            load_result = await self.data_loader.load_with_lookback(
                symbol=self.config.symbol,
                start_time=self.config.start_time,
                end_time=self.config.end_time,
                interval=self.config.interval,
                lookback_periods=lookback_periods,
            )

            all_klines = load_result.klines
            total_klines = len(all_klines)

            logger.info(f"总共加载了 {total_klines} 根K线数据（含lookback）")

            if total_klines == 0:
                raise ValueError("没有可用的K线数据")

            # 3. 分离lookback数据和回测数据
            backtest_start_ms = int(self.config.start_time.timestamp() * 1000)

            lookback_klines = [
                k for k in all_klines
                if k.open_time < backtest_start_ms
            ]
            backtest_klines = [
                k for k in all_klines
                if k.open_time >= backtest_start_ms
            ]

            logger.info(
                f"数据分离完成: {len(lookback_klines)} 根lookback数据, "
                f"{len(backtest_klines)} 根回测数据"
            )

            # 4. 初始化执行器和协调器（如果没有从检查点恢复）
            if not self.config.resume_from_checkpoint or not self.executor:
                memory = PersistentMemory() if self.config.save_trades else None
                self.coordinator = TradingCoordinator(
                    symbol=self.config.symbol,
                    interval=self.config.interval,
                    memory=memory,
                )

                await self.coordinator.initialize()

                # 将lookback数据传递给coordinator（如果支持）
                if lookback_klines and hasattr(self.coordinator, 'set_historical_lookback'):
                    await self.coordinator.set_historical_lookback(lookback_klines)
                    logger.info(f"已将 {len(lookback_klines)} 根lookback数据传递给coordinator")

                self.executor = BacktestExecutor(
                    config=self.config,
                    coordinator=self.coordinator,
                )

            # 5. 逐根K线执行（只使用回测数据，不使用lookback数据）
            logger.info("开始执行回测迭代...")

            for i in range(start_index, len(backtest_klines)):
                kline = backtest_klines[i]

                if self.config.enable_progress_bar and i % 100 == 0:
                    progress = (i + 1) / len(backtest_klines) * 100
                    logger.info(f"进度: {progress:.1f}% ({i + 1}/{len(backtest_klines)})")

                await self.executor.process_kline(kline)

                # 定期保存检查点
                if self.config.save_checkpoints and self.checkpoint_manager:
                    if (i + 1) % self.config.checkpoint_interval == 0:
                        await self._save_checkpoint(i + 1, backtest_klines)

            # 6. 平掉所有剩余持仓
            if backtest_klines:
                last_kline = backtest_klines[-1]
                last_price = last_kline.close
                last_time = datetime.fromtimestamp(last_kline.close_time / 1000)

                await self.executor.close_all_positions(last_price, last_time)

            # 7. 计算指标
            logger.info("计算回测指标...")
            metrics = await self.metrics_calculator.calculate(
                executor=self.executor,
                config=self.config,
            )

            # 8. 构建结果
            completed_at = datetime.now()
            execution_time = (completed_at - started_at).total_seconds()

            result = BacktestResult(
                config=self.config,
                metrics=metrics,
                trades=self.executor.state.trade_history,
                decisions=self.executor.state.decision_history,
                execution_time=execution_time,
                total_klines=len(backtest_klines),  # 只统计回测K线数量
                llm_calls=0,  # TODO: 从LLM优化器获取
                llm_cache_hits=0,
                cache_hit_rate=0.0,
                started_at=started_at,
                completed_at=completed_at,
            )

            logger.info(f"回测完成! 耗时: {execution_time:.2f}秒")
            logger.info(f"总收益率: {metrics.total_return:.2%}")
            logger.info(f"夏普比率: {metrics.sharpe_ratio:.2f}")
            logger.info(f"最大回撤: {metrics.max_drawdown:.2%}")
            logger.info(f"胜率: {metrics.win_rate:.2%}")
            logger.info(f"总交易: {metrics.total_trades}")

            # 9. 生成报告
            if self.config.report_formats:
                await self._generate_reports(result)

            return result

        except Exception as e:
            logger.error(f"回测执行失败: {e}", exc_info=True)

            return BacktestResult(
                config=self.config,
                metrics=None,
                trades=[],
                decisions=[],
                execution_time=(datetime.now() - started_at).total_seconds(),
                total_klines=0,
                llm_calls=0,
                llm_cache_hits=0,
                cache_hit_rate=0.0,
                started_at=started_at,
                completed_at=datetime.now(),
                error_message=str(e),
            )

    async def _generate_reports(self, result: BacktestResult) -> None:
        """生成报告"""
        try:
            # 1. 导出交易记录到CSV（总是导出）
            if result.trades:
                await self._export_trades_to_csv(result)

            # 2. 生成其他格式的报告
            reports = await self.reporter.generate_reports(
                result=result,
                formats=self.config.report_formats,
            )

            for format_type, content in reports.items():
                if format_type == ReportFormat.TEXT:
                    print("\n" + "=" * 60)
                    print("回测报告")
                    print("=" * 60)
                    print(content)

                elif format_type == ReportFormat.HTML:
                    from pathlib import Path

                    output_dir = Path("./backtest_results")
                    output_dir.mkdir(exist_ok=True)

                    timestamp = int(result.started_at.timestamp())
                    output_path = output_dir / f"report_{self.config.symbol}_{timestamp}.html"
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.info(f"HTML报告已保存: {output_path}")

                elif format_type == ReportFormat.JSON:
                    from pathlib import Path

                    output_dir = Path("./backtest_results")
                    output_dir.mkdir(exist_ok=True)

                    timestamp = int(result.started_at.timestamp())
                    output_path = output_dir / f"result_{self.config.symbol}_{timestamp}.json"
                    import json
                    with open(output_path, "w", encoding="utf-8") as f:
                        # 序列化结果
                        result_dict = self._serialize_result(result)
                        json.dump(result_dict, f, indent=2, default=str)
                    logger.info(f"JSON结果已保存: {output_path}")

        except Exception as e:
            logger.error(f"生成报告失败: {e}", exc_info=True)

    def _serialize_result(self, result: BacktestResult) -> Dict:
        """序列化回测结果"""
        import platform
        import sys

        # 序列化配置
        config_data = {
            "symbol": result.config.symbol,
            "interval": result.config.interval,
            "start_time": result.config.start_time.isoformat(),
            "end_time": result.config.end_time.isoformat(),
            "initial_balance": result.config.initial_balance,
            "llm_mode": result.config.llm_mode.value,
            "prompt_id": result.config.prompt_id,
            "prompt_version": result.config.prompt_version,
            "decision_interval": result.config.decision_interval,
            "significant_change_threshold": result.config.significant_change_threshold,
        }

        # 序列化指标
        metrics_data = None
        if result.metrics:
            metrics_data = {
                "total_return": result.metrics.total_return,
                "win_rate": result.metrics.win_rate,
                "sharpe_ratio": result.metrics.sharpe_ratio,
                "sortino_ratio": result.metrics.sortino_ratio,
                "max_drawdown": result.metrics.max_drawdown,
                "profit_factor": result.metrics.profit_factor,
                "avg_trade_pnl": result.metrics.avg_trade_pnl,
                "avg_win_pnl": result.metrics.avg_win_pnl,
                "avg_loss_pnl": result.metrics.avg_loss_pnl,
                "total_trades": result.metrics.total_trades,
                "profitable_trades": result.metrics.profitable_trades,
                "losing_trades": result.metrics.losing_trades,
                "var_95": result.metrics.var_95,
                "var_99": result.metrics.var_99,
                "expected_shortfall_95": result.metrics.expected_shortfall_95,
                "max_consecutive_losses": result.metrics.max_consecutive_losses,
                "avg_hold_duration_hours": result.metrics.avg_hold_duration_hours,
            }

        # 序列化交易
        trades_data = []
        for t in result.trades:
            trade_data = {
                "trade_id": t.trade_id,
                "symbol": t.symbol,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "side": t.side,
                "pnl": t.pnl,
                "pnl_percentage": t.pnl_percentage,
                "decision_id": t.decision_id,
                "signal": t.signal.value if hasattr(t.signal, 'value') else str(t.signal),
                "confidence": t.confidence,
                "market_condition": t.market_condition,
                "hold_duration_hours": t.hold_duration_hours,
            }
            trades_data.append(trade_data)

        # 环境信息
        environment = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "hostname": platform.node(),
        }

        return {
            "config": config_data,
            "metrics": metrics_data,
            "trades": trades_data,
            "execution_time": result.execution_time,
            "total_klines": result.total_klines,
            "llm_calls": result.llm_calls,
            "llm_cache_hits": result.llm_cache_hits,
            "cache_hit_rate": result.cache_hit_rate,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat(),
            "error_message": result.error_message,
            "environment": environment,
        }

    async def _save_checkpoint(self, current_index: int, backtest_klines: list) -> None:
        """
        保存检查点

        Args:
            current_index: 当前K线索引
            backtest_klines: 回测K线列表
        """
        if not self.checkpoint_manager:
            return

        try:
            # 序列化执行状态
            from vibe_trading.backtest.checkpoint import CheckpointManager

            temp_manager = CheckpointManager()
            execution_state_dict = temp_manager._serialize_execution_state(self.executor.state)

            # 生成检查点ID
            checkpoint_id = self.checkpoint_manager.generate_checkpoint_id(
                symbol=self.config.symbol,
                interval=self.config.interval,
                current_index=current_index,
            )

            # 创建检查点对象
            checkpoint = BacktestCheckpoint(
                checkpoint_id=checkpoint_id,
                config=self.config,
                current_kline_index=current_index,
                execution_state=execution_state_dict,
                coordinator_state=None,  # 暂不保存coordinator状态
            )

            # 保存检查点
            checkpoint_path = await self.checkpoint_manager.save_checkpoint(checkpoint)
            logger.info(f"检查点已保存: {checkpoint_path}")

        except Exception as e:
            logger.error(f"保存检查点失败: {e}", exc_info=True)

    async def _export_trades_to_csv(self, result: BacktestResult) -> str:
        """
        导出交易记录到CSV文件

        Args:
            result: 回测结果

        Returns:
            CSV文件路径
        """
        import csv
        from pathlib import Path

        output_dir = Path("./backtest_results")
        output_dir.mkdir(exist_ok=True)

        timestamp = int(result.started_at.timestamp())
        output_path = output_dir / f"trades_{self.config.symbol}_{timestamp}.csv"

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            if not result.trades:
                logger.warning("没有交易记录可导出")
                return str(output_path)

            writer = csv.writer(f)
            # 写入表头
            writer.writerow([
                "Trade ID",
                "Symbol",
                "Side",
                "Entry Time",
                "Exit Time",
                "Entry Price",
                "Exit Price",
                "Quantity",
                "PnL",
                "PnL %",
                "Hold Duration (hours)",
                "Signal",
                "Confidence",
                "Market Condition",
            ])

            # 写入数据
            for t in result.trades:
                writer.writerow([
                    t.trade_id,
                    t.symbol,
                    t.side,
                    t.entry_time.isoformat() if t.entry_time else "",
                    t.exit_time.isoformat() if t.exit_time else "",
                    t.entry_price,
                    t.exit_price,
                    t.quantity,
                    t.pnl,
                    t.pnl_percentage,
                    t.hold_duration_hours,
                    t.signal.value if hasattr(t.signal, 'value') else str(t.signal),
                    t.confidence,
                    t.market_condition,
                ])

        logger.info(f"交易记录已导出到CSV: {output_path}")
        return str(output_path)


# ============================================================================
# 便捷函数
# ============================================================================

async def run_backtest(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    interval: str = "30m",
    llm_mode: LLMMode = LLMMode.CACHED,
    initial_balance: float = 10000.0,
) -> BacktestResult:
    """
    便捷函数：运行回测

    Args:
        symbol: 交易品种
        start_time: 开始时间
        end_time: 结束时间
        interval: K线间隔
        llm_mode: LLM模式
        initial_balance: 初始余额

    Returns:
        BacktestResult
    """
    config = BacktestConfig(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        initial_balance=initial_balance,
        llm_mode=llm_mode,
    )

    engine = BacktestEngine(config)
    return await engine.run_backtest()
