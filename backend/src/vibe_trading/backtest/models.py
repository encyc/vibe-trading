"""
回测系统数据模型

定义回测配置、结果、指标等核心数据结构。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from vibe_trading.coordinator.signal_processor import ProcessedSignal, TradingSignal
from vibe_trading.coordinator.quality_tracker import AgentPerformance


class LLMMode(str, Enum):
    """LLM调用模式"""
    REAL = "real"  # 真实LLM调用
    CACHED = "cached"  # 使用缓存
    SIMULATED = "simulated"  # 模拟模式


class ReportFormat(str, Enum):
    """报告格式"""
    TEXT = "text"
    HTML = "html"
    JSON = "json"


@dataclass
class BacktestConfig:
    """回测配置"""
    # 基础配置
    symbol: str
    interval: str
    start_time: datetime
    end_time: datetime
    initial_balance: float = 10000.0

    # LLM配置
    llm_mode: LLMMode = LLMMode.CACHED
    prompt_id: Optional[str] = None
    prompt_version: Optional[str] = None

    # 存储配置
    save_trades: bool = True
    save_agent_outputs: bool = True
    save_to_database: bool = True

    # 报告配置
    report_formats: List[ReportFormat] = field(default_factory=lambda: [
        ReportFormat.TEXT, ReportFormat.HTML
    ])

    # 执行配置
    max_concurrent_decisions: int = 3  # 并发决策数（用于模拟模式）
    enable_progress_bar: bool = True

    # 检查点配置
    save_checkpoints: bool = False  # 是否保存检查点
    checkpoint_interval: int = 100  # 每N根K线保存一次检查点
    checkpoint_dir: str = "./checkpoints"  # 检查点保存目录
    resume_from_checkpoint: Optional[str] = None  # 从检查点恢复的路径

    # 决策采样配置
    decision_interval: int = 1  # 决策采样间隔（每N根K线决策一次）
    significant_change_threshold: float = 0.02  # 重要变化阈值（2%）


@dataclass
class Trade:
    """单笔交易记录"""
    trade_id: str
    symbol: str
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    side: str  # LONG/SHORT
    pnl: Optional[float]
    pnl_percentage: Optional[float]

    # 决策信息
    decision_id: str
    signal: TradingSignal
    confidence: float

    # 市场信息
    market_condition: str

    # Agent贡献
    agent_contributions: Dict[str, float] = field(default_factory=dict)

    # 元数据
    hold_duration_hours: float = 0.0
    notes: str = ""


@dataclass
class PromptMetrics:
    """Prompt效果指标"""
    accuracy: float  # 决策准确率
    consistency: float  # 决策一致性（相似条件下的稳定程度）
    improvement_rate: float  # 相比基线的改进率
    avg_confidence: float  # 平均置信度
    response_time: float  # 平均响应时间（秒）


@dataclass
class BacktestMetrics:
    """回测指标"""
    # 基础交易指标
    total_return: float
    win_rate: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    profit_factor: float
    avg_trade_pnl: float
    avg_win_pnl: float
    avg_loss_pnl: float
    total_trades: int
    profitable_trades: int
    losing_trades: int

    # 风险指标
    var_95: float  # 95%置信度VaR
    var_99: float  # 99%置信度VaR
    expected_shortfall_95: float  # 95%置信度ES
    max_consecutive_losses: int
    avg_hold_duration_hours: float

    # Agent性能指标
    agent_performances: Dict[str, AgentPerformance]
    agent_rankings: List[Tuple[str, float]]

    # Prompt效果指标
    prompt_metrics: Optional[PromptMetrics] = None

    # 时间序列数据（用于绘图）
    equity_curve: List[float] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)
    timestamps: List[datetime] = field(default_factory=list)


@dataclass
class BacktestDecision:
    """回测中的单次决策"""
    decision_id: str
    timestamp: datetime
    current_price: float

    # 决策内容
    trading_decision: Any  # TradingDecision
    processed_signal: ProcessedSignal
    agent_contributions: Dict[str, float]
    market_condition: str

    # 执行结果
    signal: TradingSignal
    confidence: float
    strength: str

    # 是否执行了交易
    executed: bool = False
    trade_id: Optional[str] = None


@dataclass
class BacktestResult:
    """回测结果"""
    config: BacktestConfig
    metrics: BacktestMetrics
    trades: List[Trade]
    decisions: List[BacktestDecision]

    # 执行信息
    execution_time: float  # 总执行时间（秒）
    total_klines: int
    llm_calls: int
    llm_cache_hits: int
    cache_hit_rate: float

    # 元数据
    started_at: datetime
    completed_at: datetime
    error_message: Optional[str] = None


@dataclass
class PromptEvaluation:
    """单个Prompt版本的评估结果"""
    agent_name: str
    prompt_version: str
    accuracy: float
    contribution: float
    total_return: float
    sharpe_ratio: float
    win_rate: float
    sample_size: int  # 测试样本数
    evaluated_at: datetime = field(default_factory=datetime.now)


@dataclass
class PromptComparisonReport:
    """Prompt版本对比报告"""
    agent_name: str
    evaluations: List[PromptEvaluation]
    best_version: str
    improvement_rate: float  # 最佳版本相比最差版本的改进幅度
    recommendation: str  # 推荐建议
    generated_at: datetime = field(default_factory=datetime.now)

    def get_rankings(self) -> List[Tuple[str, float]]:
        """获取版本排名（按夏普比率）"""
        rankings = [
            (e.prompt_version, e.sharpe_ratio)
            for e in self.evaluations
        ]
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings


@dataclass
class BacktestProgress:
    """回测进度信息"""
    task_id: str
    current_kline: int
    total_klines: int
    current_time: Optional[datetime] = None
    status: str = "running"  # running/completed/failed
    error_message: Optional[str] = None

    @property
    def progress_percentage(self) -> float:
        return (self.current_kline / self.total_klines * 100) if self.total_klines > 0 else 0
