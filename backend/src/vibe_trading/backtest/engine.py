"""
回测引擎核心

协调整个回测流程，管理数据加载、决策执行、指标计算和报告生成。
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pi_logger import get_logger

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
            # 1. 加载数据
            load_result = await self.data_loader.load_klines(
                symbol=self.config.symbol,
                start_time=self.config.start_time,
                end_time=self.config.end_time,
                interval=self.config.interval,
            )

            klines = load_result.klines
            total_klines = len(klines)

            logger.info(f"加载了 {total_klines} 根K线数据")

            if total_klines == 0:
                raise ValueError("没有可用的K线数据")

            # 2. 初始化执行器和协调器
            memory = PersistentMemory() if self.config.save_trades else None
            self.coordinator = TradingCoordinator(
                symbol=self.config.symbol,
                interval=self.config.interval,
                memory=memory,
            )

            await self.coordinator.initialize()

            self.executor = BacktestExecutor(
                config=self.config,
                coordinator=self.coordinator,
            )

            # 3. 逐根K线执行
            logger.info("开始执行回测迭代...")

            for i, kline in enumerate(klines):
                if self.config.enable_progress_bar and i % 100 == 0:
                    progress = (i + 1) / total_klines * 100
                    logger.info(f"进度: {progress:.1f}% ({i + 1}/{total_klines})")

                await self.executor.process_kline(kline)

                # TODO: 集成LLM优化器
                # decision = await self.llm_optimizer.get_decision(...)

            # 4. 平掉所有剩余持仓
            if klines:
                last_kline = klines[-1]
                last_price = last_kline.close
                last_time = datetime.fromtimestamp(last_kline.close_time / 1000)

                await self.executor.close_all_positions(last_price, last_time)

            # 5. 计算指标
            logger.info("计算回测指标...")
            metrics = await self.metrics_calculator.calculate(
                executor=self.executor,
                config=self.config,
            )

            # 6. 构建结果
            completed_at = datetime.now()
            execution_time = (completed_at - started_at).total_seconds()

            result = BacktestResult(
                config=self.config,
                metrics=metrics,
                trades=self.executor.state.trade_history,
                decisions=self.executor.state.decision_history,
                execution_time=execution_time,
                total_klines=total_klines,
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

            # 7. 生成报告
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
                    output_path = f"./backtest_report_{self.config.symbol}_{int(result.started_at.timestamp())}.html"
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.info(f"HTML报告已保存: {output_path}")

                elif format_type == ReportFormat.JSON:
                    output_path = f"./backtest_result_{self.config.symbol}_{int(result.started_at.timestamp())}.json"
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
        return {
            "config": {
                "symbol": result.config.symbol,
                "interval": result.config.interval,
                "start_time": result.config.start_time.isoformat(),
                "end_time": result.config.end_time.isoformat(),
                "llm_mode": result.config.llm_mode.value,
            },
            "metrics": {
                "total_return": result.metrics.total_return if result.metrics else None,
                "win_rate": result.metrics.win_rate if result.metrics else None,
                "sharpe_ratio": result.metrics.sharpe_ratio if result.metrics else None,
                "max_drawdown": result.metrics.max_drawdown if result.metrics else None,
            },
            "trades": [
                {
                    "trade_id": t.trade_id,
                    "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                    "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl": t.pnl,
                    "pnl_percentage": t.pnl_percentage,
                }
                for t in result.trades
            ],
            "execution_time": result.execution_time,
            "total_klines": result.total_klines,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat(),
        }


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
