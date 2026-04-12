"""
增强的回测系统

提供多策略对比、参数优化、并行回测等功能。
"""
import asyncio
import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from pi_logger import get_logger

from vibe_trading.backtest.engine import BacktestEngine
from vibe_trading.backtest.models import BacktestConfig, BacktestResult, LLMMode
from vibe_trading.backtest.metrics import BacktestMetrics
from vibe_trading.backtest.reporter import BacktestReporter


logger = get_logger(__name__)


class OptimizationMethod(str, Enum):
    """参数优化方法"""
    GRID_SEARCH = "grid_search"  # 网格搜索
    RANDOM_SEARCH = "random_search"  # 随机搜索
    BAYESIAN = "bayesian"  # 贝叶斯优化（需要额外库）


@dataclass
class ParameterRange:
    """参数范围定义"""
    name: str
    values: Optional[List[Any]] = None  # 离散值列表
    min_value: Optional[float] = None  # 连续值最小值
    max_value: Optional[float] = None  # 连续值最大值
    step: Optional[float] = None  # 连续值步长

    def __post_init__(self):
        if self.values is None and (self.min_value is None or self.max_value is None):
            raise ValueError("必须指定 values 或 min_value/max_value")


@dataclass
class StrategyConfig:
    """策略配置"""
    name: str
    description: str
    base_config: BacktestConfig
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationConfig:
    """优化配置"""
    method: OptimizationMethod = OptimizationMethod.GRID_SEARCH
    max_iterations: int = 100
    parameter_ranges: List[ParameterRange] = field(default_factory=list)
    optimization_target: str = "sharpe_ratio"  # 优化目标
    minimize: bool = False  # 是否最小化目标


@dataclass
class ComparisonResult:
    """策略对比结果"""
    strategy_name: str
    metrics: BacktestMetrics
    result: BacktestResult
    rank: int = 0
    score: float = 0.0


@dataclass
class OptimizationResult:
    """参数优化结果"""
    best_parameters: Dict[str, Any]
    best_metrics: BacktestMetrics
    best_result: BacktestResult
    all_results: List[Tuple[Dict[str, Any], BacktestMetrics]] = field(default_factory=list)
    optimization_history: List[Dict[str, Any]] = field(default_factory=list)


class MultiStrategyBacktester:
    """
    多策略回测器

    支持多个策略同时回测和对比。
    """

    def __init__(
        self,
        strategies: List[StrategyConfig],
        parallel: bool = True,
        max_parallel: int = 3,
    ):
        """
        初始化多策略回测器

        Args:
            strategies: 策略配置列表
            parallel: 是否并行执行
            max_parallel: 最大并行数
        """
        self.strategies = strategies
        self.parallel = parallel
        self.max_parallel = max_parallel

    async def run_all(self) -> List[ComparisonResult]:
        """
        运行所有策略回测

        Returns:
            策略对比结果列表
        """
        logger.info(f"开始多策略回测，共 {len(self.strategies)} 个策略")

        if self.parallel:
            results = await self._run_parallel()
        else:
            results = await self._run_sequential()

        # 计算排名
        ranked_results = self._rank_results(results)

        logger.info(f"多策略回测完成")
        return ranked_results

    async def _run_sequential(self) -> List[ComparisonResult]:
        """顺序执行回测"""
        results = []

        for i, strategy in enumerate(self.strategies, 1):
            logger.info(f"执行策略 {i}/{len(self.strategies)}: {strategy.name}")

            try:
                result = await self._run_single_strategy(strategy)
                results.append(result)

            except Exception as e:
                logger.error(f"策略 {strategy.name} 回测失败: {e}")
                continue

        return results

    async def _run_parallel(self) -> List[ComparisonResult]:
        """并行执行回测"""
        semaphore = asyncio.Semaphore(self.max_parallel)

        async def run_with_limit(strategy: StrategyConfig) -> ComparisonResult:
            async with semaphore:
                return await self._run_single_strategy(strategy)

        tasks = [run_with_limit(s) for s in self.strategies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"策略 {self.strategies[i].name} 回测失败: {result}")
            else:
                valid_results.append(result)

        return valid_results

    async def _run_single_strategy(self, strategy: StrategyConfig) -> ComparisonResult:
        """运行单个策略"""
        logger.info(f"回测策略: {strategy.name}")

        # 创建引擎
        engine = BacktestEngine(strategy.base_config)

        # 运行回测
        result = await engine.run_backtest()

        # 创建对比结果
        return ComparisonResult(
            strategy_name=strategy.name,
            metrics=result.metrics,
            result=result,
        )

    def _rank_results(self, results: List[ComparisonResult]) -> List[ComparisonResult]:
        """对结果进行排名"""
        if not results:
            return results

        # 按夏普比率排名（可配置其他指标）
        sorted_results = sorted(
            results,
            key=lambda r: r.metrics.sharpe_ratio,
            reverse=True,
        )

        # 分配排名
        for i, result in enumerate(sorted_results, 1):
            result.rank = i
            result.score = result.metrics.sharpe_ratio

        return sorted_results

    def generate_comparison_report(self, results: List[ComparisonResult]) -> str:
        """生成策略对比报告"""
        if not results:
            return "无结果"

        lines = [
            "=" * 80,
            "多策略回测对比报告",
            "=" * 80,
            "",
            f"回测策略数量: {len(results)}",
        ]

        # 添加时间范围（如果有有效的result）
        if results and results[0].result is not None:
            lines.append(f"回测时间范围: {results[0].result.config.start_time} ~ {results[0].result.config.end_time}")

        lines.extend([
            "",
            "=" * 80,
            "排名结果",
            "=" * 80,
            "",
        ])

        # 添加排名表格
        lines.extend([
            f"{'排名':<6} {'策略名称':<20} {'收益率':<12} {'夏普比率':<12} {'胜率':<10} {'最大回撤':<12}",
            "-" * 80,
        ])

        for result in results:
            lines.append(
                f"{result.rank:<6} "
                f"{result.strategy_name:<20} "
                f"{result.metrics.total_return:>10.2%}  "
                f"{result.metrics.sharpe_ratio:>10.2f}  "
                f"{result.metrics.win_rate:>8.1%}  "
                f"{result.metrics.max_drawdown:>10.2%}"
            )

        # 添加详细对比
        lines.extend([
            "",
            "=" * 80,
            "详细指标",
            "=" * 80,
            "",
        ])

        for result in results:
            lines.extend([
                f"策略: {result.strategy_name} (排名: #{result.rank})",
                "-" * 40,
                f"  总收益率:      {result.metrics.total_return:.2%}",
                f"  夏普比率:      {result.metrics.sharpe_ratio:.2f}",
                f"  索提诺比率:    {result.metrics.sortino_ratio:.2f}",
                f"  最大回撤:      {result.metrics.max_drawdown:.2%}",
                f"  胜率:          {result.metrics.win_rate:.1%}",
                f"  盈亏比:        {result.metrics.profit_factor:.2f}",
                f"  总交易次数:    {result.metrics.total_trades}",
                f"  平均收益:      ${result.metrics.avg_trade_pnl:.2f}",
                f"  VaR (95%):     ${result.metrics.var_95:.2f}",
                "",
            ])

        # 添加最佳策略建议
        best_result = results[0]
        lines.extend([
            "=" * 80,
            "推荐策略",
            "=" * 80,
            "",
            f"最佳策略: {best_result.strategy_name}",
            f"推荐理由: 夏普比率 {best_result.metrics.sharpe_ratio:.2f}, "
            f"收益率 {best_result.metrics.total_return:.2%}",
            "",
        ])

        return "\n".join(lines)


class ParameterOptimizer:
    """
    参数优化器

    支持多种优化方法进行策略参数调优。
    """

    def __init__(
        self,
        base_config: BacktestConfig,
        optimization_config: OptimizationConfig,
        parallel: bool = True,
        max_parallel: int = 3,
    ):
        """
        初始化参数优化器

        Args:
            base_config: 基础回测配置
            optimization_config: 优化配置
            parallel: 是否并行执行
            max_parallel: 最大并行数
        """
        self.base_config = base_config
        self.opt_config = optimization_config
        self.parallel = parallel
        self.max_parallel = max_parallel

    async def optimize(self) -> OptimizationResult:
        """
        执行参数优化

        Returns:
            优化结果
        """
        logger.info(f"开始参数优化，方法: {self.opt_config.method.value}")

        if self.opt_config.method == OptimizationMethod.GRID_SEARCH:
            result = await self._grid_search()
        elif self.opt_config.method == OptimizationMethod.RANDOM_SEARCH:
            result = await self._random_search()
        elif self.opt_config.method == OptimizationMethod.BAYESIAN:
            result = await self._bayesian_optimization()
        else:
            raise ValueError(f"不支持的优化方法: {self.opt_config.method}")

        logger.info(f"参数优化完成，最佳参数: {result.best_parameters}")
        return result

    async def _grid_search(self) -> OptimizationResult:
        """网格搜索"""
        # 生成参数组合
        param_combinations = self._generate_grid_combinations()

        logger.info(f"网格搜索：总共 {len(param_combinations)} 种参数组合")

        # 运行所有组合
        all_results = await self._run_param_combinations(param_combinations)

        # 找到最佳参数
        best_result = self._find_best_result(all_results)

        return OptimizationResult(
            best_parameters=best_result[0],
            best_metrics=best_result[1],
            best_result=best_result[2],
            all_results=[(r[0], r[1]) for r in all_results],
        )

    async def _random_search(self) -> OptimizationResult:
        """随机搜索"""
        import random

        all_results = []

        for i in range(self.opt_config.max_iterations):
            # 随机生成参数
            params = self._generate_random_parameters()

            logger.info(f"随机搜索迭代 {i + 1}/{self.opt_config.max_iterations}")

            # 运行回测
            result = await self._run_single_params(params)
            all_results.append((params, result.metrics, result))

        # 找到最佳结果
        best_result = self._find_best_result(all_results)

        return OptimizationResult(
            best_parameters=best_result[0],
            best_metrics=best_result[1],
            best_result=best_result[2],
            all_results=[(r[0], r[1]) for r in all_results],
        )

    async def _bayesian_optimization(self) -> OptimizationResult:
        """贝叶斯优化（简化版，实际需要skopt等库）"""
        # 这里使用简化的实现
        logger.warning("贝叶斯优化使用简化实现")

        # 首先进行随机搜索收集初始数据
        initial_results = []
        for i in range(min(10, self.opt_config.max_iterations)):
            params = self._generate_random_parameters()
            result = await self._run_single_params(params)
            initial_results.append((params, result.metrics, result))

        # 然后在最佳结果附近进行精细搜索
        best_initial = self._find_best_result(initial_results)
        refined_results = await self._refine_search(best_initial[0])

        # 合并结果
        all_results = initial_results + refined_results
        best_result = self._find_best_result(all_results)

        return OptimizationResult(
            best_parameters=best_result[0],
            best_metrics=best_result[1],
            best_result=best_result[2],
            all_results=[(r[0], r[1]) for r in all_results],
        )

    def _generate_grid_combinations(self) -> List[Dict[str, Any]]:
        """生成网格搜索的参数组合"""
        from itertools import product

        # 为每个参数生成值列表
        param_values = {}
        for param_range in self.opt_config.parameter_ranges:
            if param_range.values:
                param_values[param_range.name] = param_range.values
            elif param_range.min_value is not None and param_range.max_value is not None:
                if param_range.step:
                    param_values[param_range.name] = [
                        param_range.min_value + i * param_range.step
                        for i in range(int((param_range.max_value - param_range.min_value) / param_range.step) + 1)
                    ]
                else:
                    # 默认生成5个值
                    param_values[param_range.name] = [
                        param_range.min_value + (param_range.max_value - param_range.min_value) * i / 4
                        for i in range(5)
                    ]

        # 生成所有组合
        keys = list(param_values.keys())
        values = list(param_values.values())

        combinations = []
        for combo in product(*values):
            combinations.append(dict(zip(keys, combo)))

        return combinations

    def _generate_random_parameters(self) -> Dict[str, Any]:
        """生成随机参数"""
        import random

        params = {}
        for param_range in self.opt_config.parameter_ranges:
            if param_range.values:
                params[param_range.name] = random.choice(param_range.values)
            elif param_range.min_value is not None and param_range.max_value is not None:
                params[param_range.name] = random.uniform(
                    param_range.min_value,
                    param_range.max_value
                )

        return params

    async def _run_param_combinations(
        self,
        combinations: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], BacktestMetrics, BacktestResult]]:
        """运行参数组合"""
        if self.parallel:
            return await self._run_parallel_combinations(combinations)
        else:
            results = []
            for i, params in enumerate(combinations):
                logger.info(f"运行参数组合 {i + 1}/{len(combinations)}: {params}")
                result = await self._run_single_params(params)
                results.append((params, result.metrics, result))
            return results

    async def _run_parallel_combinations(
        self,
        combinations: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], BacktestMetrics, BacktestResult]]:
        """并行运行参数组合"""
        semaphore = asyncio.Semaphore(self.max_parallel)

        async def run_with_limit(params: Dict[str, Any]) -> Tuple[Dict[str, Any], BacktestMetrics, BacktestResult]:
            async with semaphore:
                result = await self._run_single_params(params)
                return (params, result.metrics, result)

        tasks = [run_with_limit(params) for params in combinations]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 过滤异常
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"参数组合执行失败: {result}")
            else:
                valid_results.append(result)

        return valid_results

    async def _run_single_params(
        self,
        params: Dict[str, Any]
    ) -> BacktestResult:
        """运行单个参数组合"""
        # 创建配置
        config = copy.deepcopy(self.base_config)

        # 应用参数
        for key, value in params.items():
            setattr(config, key, value)

        # 运行回测
        engine = BacktestEngine(config)
        return await engine.run_backtest()

    def _find_best_result(
        self,
        results: List[Tuple[Dict[str, Any], BacktestMetrics, BacktestResult]]
    ) -> Tuple[Dict[str, Any], BacktestMetrics, BacktestResult]:
        """找到最佳结果"""
        if not results:
            raise ValueError("没有结果")

        # 根据优化目标排序
        target = self.opt_config.optimization_target
        reverse = not self.opt_config.minimize

        sorted_results = sorted(
            results,
            key=lambda r: getattr(r[1], target, 0),
            reverse=reverse,
        )

        return sorted_results[0]

    async def _refine_search(
        self,
        base_params: Dict[str, Any]
    ) -> List[Tuple[Dict[str, Any], BacktestMetrics, BacktestResult]]:
        """在最佳参数附近进行精细搜索"""
        results = []

        # 为每个参数生成±10%的变化
        for param_range in self.opt_config.parameter_ranges:
            param_name = param_range.name
            if param_name not in base_params:
                continue

            base_value = base_params[param_name]

            # 生成3个值：-10%, 基准, +10%
            if isinstance(base_value, (int, float)):
                variations = [
                    base_value * 0.9,
                    base_value,
                    base_value * 1.1,
                ]
            else:
                variations = [base_value]

            for variation in variations:
                params = base_params.copy()
                params[param_name] = variation

                try:
                    result = await self._run_single_params(params)
                    results.append((params, result.metrics, result))
                except Exception as e:
                    logger.error(f"精细搜索失败: {params}, 错误: {e}")

        return results

    def generate_optimization_report(self, result: OptimizationResult) -> str:
        """生成优化报告"""
        lines = [
            "=" * 80,
            "参数优化报告",
            "=" * 80,
            "",
            f"优化方法: {self.opt_config.method.value}",
            f"优化目标: {self.opt_config.optimization_target}",
            "",
            "=" * 80,
            "最佳参数",
            "=" * 80,
            "",
        ]

        for param, value in result.best_parameters.items():
            lines.append(f"  {param}: {value}")

        lines.extend([
            "",
            "=" * 80,
            "最佳指标",
            "=" * 80,
            "",
            f"  总收益率:      {result.best_metrics.total_return:.2%}",
            f"  夏普比率:      {result.best_metrics.sharpe_ratio:.2f}",
            f"  索提诺比率:    {result.best_metrics.sortino_ratio:.2f}",
            f"  最大回撤:      {result.best_metrics.max_drawdown:.2%}",
            f"  胜率:          {result.best_metrics.win_rate:.1%}",
            f"  盈亏比:        {result.best_metrics.profit_factor:.2f}",
            "",
        ])

        if result.all_results:
            lines.extend([
                "=" * 80,
                "优化历史",
                "=" * 80,
                "",
                f"总参数组合数: {len(result.all_results)}",
                "",
            ])

        return "\n".join(lines)


# =============================================================================
# 便捷函数
# =============================================================================

async def compare_strategies(
    strategies: List[StrategyConfig],
    parallel: bool = True,
    max_parallel: int = 3,
) -> List[ComparisonResult]:
    """
    比较多个策略

    Args:
        strategies: 策略配置列表
        parallel: 是否并行执行
        max_parallel: 最大并行数

    Returns:
        策略对比结果列表
    """
    backtester = MultiStrategyBacktester(strategies, parallel, max_parallel)
    return await backtester.run_all()


async def optimize_parameters(
    base_config: BacktestConfig,
    parameter_ranges: List[ParameterRange],
    optimization_target: str = "sharpe_ratio",
    method: OptimizationMethod = OptimizationMethod.GRID_SEARCH,
    max_iterations: int = 100,
    parallel: bool = True,
) -> OptimizationResult:
    """
    优化策略参数

    Args:
        base_config: 基础回测配置
        parameter_ranges: 参数范围列表
        optimization_target: 优化目标指标
        method: 优化方法
        max_iterations: 最大迭代次数
        parallel: 是否并行执行

    Returns:
        优化结果
    """
    opt_config = OptimizationConfig(
        method=method,
        max_iterations=max_iterations,
        parameter_ranges=parameter_ranges,
        optimization_target=optimization_target,
    )

    optimizer = ParameterOptimizer(base_config, opt_config, parallel)
    return await optimizer.optimize()
