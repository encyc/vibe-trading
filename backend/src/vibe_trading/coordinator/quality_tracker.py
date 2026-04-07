"""
决策质量评估系统

跟踪和评估Agent决策的质量，用于优化和A/B测试。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pi_logger import get_logger

from vibe_trading.coordinator.signal_processor import ProcessedSignal, TradingSignal

logger = get_logger(__name__)


class EvaluationMetric(str, Enum):
    """评估指标"""
    ACCURACY = "accuracy"  # 准确率
    PROFITABILITY = "profitability"  # 盈利能力
    RISK_ADJUSTED_RETURN = "risk_adjusted_return"  # 风险调整收益
    CONSISTENCY = "consistency"  # 一致性
    RESPONSE_TIME = "response_time"  # 响应时间


@dataclass
class DecisionRecord:
    """决策记录"""
    decision_id: str
    symbol: str
    timestamp: datetime

    # 决策内容
    signal: TradingSignal
    confidence: float
    strength: str

    # Agent贡献
    agent_contributions: Dict[str, float]  # agent_name -> contribution_score

    # 执行结果
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    position_size: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percentage: Optional[float] = None

    # 市场状态
    market_condition: str = "unknown"  # trending, ranging, volatile
    hold_duration_hours: float = 0.0

    # 元数据
    decision_context: Optional[Dict[str, Any]] = None


@dataclass
class AgentPerformance:
    """Agent性能统计"""
    agent_name: str
    total_decisions: int = 0
    correct_predictions: int = 0
    incorrect_predictions: int = 0
    accuracy: float = 0.0
    avg_confidence: float = 0.0
    avg_contribution: float = 0.0

    # 最近表现（最近N次决策）
    recent_accuracy: List[bool] = field(default_factory=list)

    # 性能趋势
    improving: bool = False
    stable: bool = False
    declining: bool = False


@dataclass
class QualityMetrics:
    """质量指标"""
    # 整体指标
    total_decisions: int = 0
    profitable_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # 收益指标
    total_pnl: float = 0.0
    avg_pnl_per_trade: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0

    # 风险指标
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0

    # Agent指标
    agent_performances: Dict[str, AgentPerformance] = field(default_factory=dict)


class DecisionQualityTracker:
    """
    决策质量跟踪器

    记录和评估Agent决策的质量。
    """

    def __init__(
        self,
        storage_path: str = "./decision_quality.db",
        enable_persistence: bool = True,
    ):
        """
        初始化跟踪器

        Args:
            storage_path: 存储路径
            enable_persistence: 是否启用持久化
        """
        self.storage_path = storage_path
        self.enable_persistence = enable_persistence

        # 内存存储
        self._decisions: List[DecisionRecord] = []
        self._agent_performances: Dict[str, AgentPerformance] = {}

        # 性能指标缓存
        self._metrics_cache: Optional[QualityMetrics] = None
        self._cache_timestamp: Optional[datetime] = None

    async def record_decision(
        self,
        decision_id: str,
        symbol: str,
        signal: ProcessedSignal,
        agent_contributions: Dict[str, float],
        market_condition: str = "unknown",
    ):
        """
        记录决策

        Args:
            decision_id: 决策ID
            symbol: 交易品种
            signal: 处理后的信号
            agent_contributions: Agent贡献度
            market_condition: 市场状态
        """
        record = DecisionRecord(
            decision_id=decision_id,
            symbol=symbol,
            timestamp=datetime.now(),
            signal=signal.signal,
            confidence=signal.confidence,
            strength=signal.strength.value,
            agent_contributions=agent_contributions,
            market_condition=market_condition,
        )

        self._decisions.append(record)

        # 更新Agent性能
        await self._update_agent_performances(record)

        # 使缓存失效
        self._metrics_cache = None

        # 持久化
        if self.enable_persistence:
            await self._persist_decision(record)

        logger.debug(
            f"记录决策: {decision_id} - {signal.signal.value} ({signal.confidence:.2f})",
            tag="QualityTracker"
        )

    async def record_outcome(
        self,
        decision_id: str,
        entry_price: float,
        exit_price: float,
        position_size: float,
        hold_duration_hours: float,
    ):
        """
        记录交易结果

        Args:
            decision_id: 决策ID
            entry_price: 入场价格
            exit_price: 出场价格
            position_size: 仓位大小
            hold_duration_hours: 持仓时长
        """
        # 查找决策记录
        record = next((r for r in self._decisions if r.decision_id == decision_id), None)

        if not record:
            logger.warning(f"未找到决策记录: {decision_id}", tag="QualityTracker")
            return

        # 更新结果
        record.entry_price = entry_price
        record.exit_price = exit_price
        record.position_size = position_size
        record.hold_duration_hours = hold_duration_hours

        # 计算盈亏
        if record.signal == TradingSignal.BUY:
            record.pnl = (exit_price - entry_price) * position_size
        else:  # SELL
            record.pnl = (entry_price - exit_price) * position_size

        record.pnl_percentage = (record.pnl / (entry_price * position_size)) * 100

        # 评估决策正确性
        is_correct = record.pnl > 0

        # 更新Agent性能
        for agent_name in record.agent_contributions.keys():
            if agent_name not in self._agent_performances:
                self._agent_performances[agent_name] = AgentPerformance(
                    agent_name=agent_name
                )

            agent_perf = self._agent_performances[agent_name]
            agent_perf.total_decisions += 1

            if is_correct:
                agent_perf.correct_predictions += 1
                agent_perf.recent_accuracy.append(True)
            else:
                agent_perf.incorrect_predictions += 1
                agent_perf.recent_accuracy.append(False)

            # 限制最近记录长度
            if len(agent_perf.recent_accuracy) > 20:
                agent_perf.recent_accuracy = agent_perf.recent_accuracy[-20:]

            # 更新准确率
            agent_perf.accuracy = (
                agent_perf.correct_predictions / agent_perf.total_decisions
                if agent_perf.total_decisions > 0
                else 0.0
            )

        # 使缓存失效
        self._metrics_cache = None

        # 持久化
        if self.enable_persistence:
            await self._persist_outcome(decision_id, record)

        logger.info(
            f"记录交易结果: {decision_id} - PnL: {record.pnl_percentage:.2f}% ({'盈利' if is_correct else '亏损'})",
            tag="QualityTracker"
        )

    async def get_quality_metrics(self, force_refresh: bool = False) -> QualityMetrics:
        """
        获取质量指标

        Args:
            force_refresh: 是否强制刷新缓存

        Returns:
            质量指标
        """
        if self._metrics_cache and not force_refresh:
            # 检查缓存是否过期（5分钟）
            if datetime.now() - self._cache_timestamp < timedelta(minutes=5):
                return self._metrics_cache

        # 计算指标
        metrics = QualityMetrics()

        # 基本统计
        completed_decisions = [d for d in self._decisions if d.pnl is not None]
        metrics.total_decisions = len(completed_decisions)

        if metrics.total_decisions == 0:
            return metrics

        # 盈亏统计
        profitable = [d for d in completed_decisions if d.pnl > 0]
        losing = [d for d in completed_decisions if d.pnl <= 0]

        metrics.profitable_trades = len(profitable)
        metrics.losing_trades = len(losing)
        metrics.win_rate = len(profitable) / metrics.total_decisions

        # 收益指标
        pnls = [d.pnl for d in completed_decisions]
        metrics.total_pnl = sum(pnls)
        metrics.avg_pnl_per_trade = metrics.total_pnl / metrics.total_decisions
        metrics.best_trade_pnl = max(pnls)
        metrics.worst_trade_pnl = min(pnls)

        # 最大回撤
        cumulative_pnl = []
        running_sum = 0
        running_max = 0

        for pnl in pnls:
            running_sum += pnl
            running_max = max(running_max, running_sum)
            drawdown = running_sum - running_max
            cumulative_pnl.append(drawdown)

        metrics.max_drawdown = min(cumulative_pnl) if cumulative_pnl else 0.0

        # Sharpe比率（简化版，假设无风险利率为0）
        if len(pnls) > 1:
            import statistics
            avg_pnl = statistics.mean(pnls)
            std_pnl = statistics.stdev(pnls) if len(pnls) > 1 else 0
            metrics.sharpe_ratio = avg_pnl / std_pnl if std_pnl > 0 else 0.0

        # Agent性能
        metrics.agent_performances = self._agent_performances.copy()

        self._metrics_cache = metrics
        self._cache_timestamp = datetime.now()

        return metrics

    async def _update_agent_performances(self, record: DecisionRecord):
        """更新Agent性能（基于信号）"""
        # 这里可以基于信号强度和置信度进行初步评估
        # 实际评估需要在record_outcome中进行
        pass

    async def _persist_decision(self, record: DecisionRecord):
        """持久化决策记录"""
        # TODO: 实现数据库持久化
        pass

    async def _persist_outcome(self, decision_id: str, record: DecisionRecord):
        """持久化交易结果"""
        # TODO: 实现数据库持久化
        pass

    def get_agent_ranking(self, min_decisions: int = 5) -> List[Tuple[str, float]]:
        """
        获取Agent排名（按准确率）

        Args:
            min_decisions: 最小决策次数

        Returns:
            [(agent_name, accuracy), ...] 按准确率降序排列
        """
        rankings = []

        for agent_name, perf in self._agent_performances.items():
            if perf.total_decisions >= min_decisions:
                rankings.append((agent_name, perf.accuracy))

        # 按准确率降序排列
        rankings.sort(key=lambda x: x[1], reverse=True)

        return rankings

    def get_top_performers(self, top_n: int = 3) -> List[str]:
        """
        获取表现最好的Agent

        Args:
            top_n: 返回数量

        Returns:
            Agent名称列表
        """
        rankings = self.get_agent_ranking()
        return [name for name, _ in rankings[:top_n]]

    def get_underperformers(self, threshold: float = 0.4) -> List[str]:
        """
        获取表现不佳的Agent

        Args:
            threshold: 准确率阈值

        Returns:
            Agent名称列表
        """
        underperformers = []

        for agent_name, perf in self._agent_performances.items():
            if perf.total_decisions >= 5 and perf.accuracy < threshold:
                underperformers.append(agent_name)

        return underperformers

    def generate_report(self) -> str:
        """
        生成质量报告

        Returns:
            报告文本
        """
        report = []
        report.append("=" * 60)
        report.append("决策质量报告")
        report.append("=" * 60)
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # 整体指标
        metrics = self._metrics_cache
        if metrics:
            report.append("【整体指标】")
            report.append(f"总决策数: {metrics.total_decisions}")
            report.append(f"盈利交易: {metrics.profitable_trades}")
            report.append(f"亏损交易: {metrics.losing_trades}")
            report.append(f"胜率: {metrics.win_rate:.2%}")
            report.append(f"总盈亏: {metrics.total_pnl:.2f} USDT")
            report.append(f"平均每笔: {metrics.avg_pnl_per_trade:.2f} USDT")
            report.append(f"最大回撤: {metrics.max_drawdown:.2f} USDT")
            report.append(f"Sharpe比率: {metrics.sharpe_ratio:.2f}")
            report.append("")

        # Agent排名
        rankings = self.get_agent_ranking()
        if rankings:
            report.append("【Agent排名】")
            for i, (name, accuracy) in enumerate(rankings[:10], 1):
                perf = self._agent_performances.get(name)
                if perf:
                    report.append(
                        f"{i}. {name}: {accuracy:.2%} "
                        f"({perf.correct_predictions}/{perf.total_decisions} 次)"
                    )
            report.append("")

        # 最佳和最差Agent
        if rankings:
            best_agent, best_acc = rankings[0]
            report.append(f"最佳Agent: {best_agent} ({best_acc:.2%})")

            underperformers = self.get_underperformers()
            if underperformers:
                report.append(f"需改进Agent: {', '.join(underperformers)}")
            report.append("")

        return "\n".join(report)


# ============================================================================
# 全局单例
# ============================================================================

_global_tracker: Optional[DecisionQualityTracker] = None


def get_quality_tracker() -> DecisionQualityTracker:
    """获取全局质量跟踪器"""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = DecisionQualityTracker()
    return _global_tracker


# ============================================================================
# 便捷函数
# ============================================================================

async def record_decision(
    decision_id: str,
    symbol: str,
    signal: ProcessedSignal,
    agent_contributions: Dict[str, float],
):
    """便捷函数：记录决策"""
    tracker = get_quality_tracker()
    await tracker.record_decision(
        decision_id=decision_id,
        symbol=symbol,
        signal=signal,
        agent_contributions=agent_contributions,
    )


async def record_trade_result(
    decision_id: str,
    entry_price: float,
    exit_price: float,
    position_size: float,
    hold_duration_hours: float = 1.0,
):
    """便捷函数：记录交易结果"""
    tracker = get_quality_tracker()
    await tracker.record_outcome(
        decision_id=decision_id,
        entry_price=entry_price,
        exit_price=exit_price,
        position_size=position_size,
        hold_duration_hours=hold_duration_hours,
    )


async def get_quality_report() -> str:
    """便捷函数：获取质量报告"""
    tracker = get_quality_tracker()
    await tracker.get_quality_metrics(force_refresh=True)
    return tracker.generate_report()
