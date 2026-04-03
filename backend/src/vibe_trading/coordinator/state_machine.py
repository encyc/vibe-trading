"""
决策流程状态机

管理一次完整决策流程的状态转换。
"""
import logging
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class DecisionState(str, Enum):
    """决策流程状态"""
    PENDING = "pending"
    ANALYZING = "analyzing"          # Phase 1: 分析师团队
    DEBATING = "debating"            # Phase 2: 研究员团队
    ASSESSING_RISK = "assessing_risk" # Phase 3: 风控团队
    PLANNING = "planning"            # Phase 4: 决策层
    EXECUTING = "executing"          # 执行交易
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StateTransition:
    """状态转换记录"""
    from_state: DecisionState
    to_state: DecisionState
    timestamp: datetime
    reason: str = ""
    metadata: Dict = field(default_factory=dict)


@dataclass
class DecisionContext:
    """决策上下文"""
    decision_id: str
    symbol: str
    interval: str
    start_time: datetime
    current_phase: int = 0
    analyst_reports: Dict = field(default_factory=dict)
    debate_result: Optional[Dict] = None
    risk_assessment: Dict = field(default_factory=dict)
    execution_plan: Optional[Dict] = None
    final_decision: Optional[Dict] = None
    error_message: Optional[str] = None


class DecisionStateMachine:
    """
    决策流程状态机

    管理一次完整的决策流程，包括状态转换、历史记录和错误处理。
    """

    # 定义允许的状态转换
    ALLOWED_TRANSITIONS = {
        DecisionState.PENDING: [DecisionState.ANALYZING, DecisionState.FAILED, DecisionState.CANCELLED],
        DecisionState.ANALYZING: [DecisionState.DEBATING, DecisionState.FAILED, DecisionState.CANCELLED],
        DecisionState.DEBATING: [DecisionState.ASSESSING_RISK, DecisionState.FAILED, DecisionState.CANCELLED],
        DecisionState.ASSESSING_RISK: [DecisionState.PLANNING, DecisionState.FAILED, DecisionState.CANCELLED],
        DecisionState.PLANNING: [DecisionState.EXECUTING, DecisionState.COMPLETED, DecisionState.FAILED, DecisionState.CANCELLED],
        DecisionState.EXECUTING: [DecisionState.COMPLETED, DecisionState.FAILED],
        DecisionState.COMPLETED: [],  # 终态
        DecisionState.FAILED: [],     # 终态
        DecisionState.CANCELLED: [],  # 终态
    }

    # 阶段编号映射
    PHASE_MAPPING = {
        1: DecisionState.ANALYZING,
        2: DecisionState.DEBATING,
        3: DecisionState.ASSESSING_RISK,
        4: DecisionState.PLANNING,
    }

    def __init__(self, decision_id: str, symbol: str, interval: str):
        """
        初始化状态机

        Args:
            decision_id: 决策ID
            symbol: 交易品种
            interval: K线周期
        """
        self.decision_id = decision_id
        self.symbol = symbol
        self.interval = interval

        self.current_state = DecisionState.PENDING
        self.state_history: List[StateTransition] = []
        self.context = DecisionContext(
            decision_id=decision_id,
            symbol=symbol,
            interval=interval,
            start_time=datetime.now(),
        )

        # 错误处理器
        self.error_handlers: Dict[DecisionState, Callable] = {}

        # 状态进入/退出钩子
        self.state_enter_hooks: Dict[DecisionState, List[Callable]] = {}
        self.state_exit_hooks: Dict[DecisionState, List[Callable]] = {}

        logger.info(f"StateMachine initialized for {decision_id} ({symbol} {interval})")

    def transition_to(self, new_state: DecisionState, reason: str = "", metadata: Optional[Dict] = None) -> bool:
        """
        状态转换

        Args:
            new_state: 目标状态
            reason: 转换原因
            metadata: 附加元数据

        Returns:
            是否转换成功
        """
        # 检查是否为终态
        if self.current_state in [DecisionState.COMPLETED, DecisionState.FAILED, DecisionState.CANCELLED]:
            logger.warning(f"Cannot transition from terminal state {self.current_state}")
            return False

        # 检查转换是否合法
        allowed = self.ALLOWED_TRANSITIONS.get(self.current_state, [])
        if new_state not in allowed:
            logger.error(
                f"Invalid transition: {self.current_state} -> {new_state}. "
                f"Allowed: {allowed}"
            )
            return False

        # 执行退出钩子
        self._execute_exit_hooks(self.current_state)

        # 记录转换
        transition = StateTransition(
            from_state=self.current_state,
            to_state=new_state,
            timestamp=datetime.now(),
            reason=reason,
            metadata=metadata or {},
        )
        self.state_history.append(transition)

        # 更新状态
        old_state = self.current_state
        self.current_state = new_state

        # 更新上下文
        self._update_context(new_state, metadata)

        logger.info(
            f"State transition: {old_state} -> {new_state} "
            f"(reason: {reason or 'N/A'})"
        )

        # 执行进入钩子
        self._execute_enter_hooks(new_state)

        # 检查是否需要执行错误处理
        if new_state == DecisionState.FAILED:
            self._handle_error(new_state, reason, metadata)

        return True

    def _update_context(self, new_state: DecisionState, metadata: Optional[Dict]):
        """更新决策上下文"""
        if new_state == self.PHASE_MAPPING.get(1):
            self.context.current_phase = 1
        elif new_state == self.PHASE_MAPPING.get(2):
            self.context.current_phase = 2
        elif new_state == self.PHASE_MAPPING.get(3):
            self.context.current_phase = 3
        elif new_state == self.PHASE_MAPPING.get(4):
            self.context.current_phase = 4

        # 更新元数据
        if metadata:
            if "analyst_reports" in metadata:
                self.context.analyst_reports.update(metadata["analyst_reports"])
            if "debate_result" in metadata:
                self.context.debate_result = metadata["debate_result"]
            if "risk_assessment" in metadata:
                self.context.risk_assessment.update(metadata["risk_assessment"])
            if "execution_plan" in metadata:
                self.context.execution_plan = metadata["execution_plan"]
            if "final_decision" in metadata:
                self.context.final_decision = metadata["final_decision"]
            if "error" in metadata:
                self.context.error_message = metadata["error"]

    def register_enter_hook(self, state: DecisionState, hook: Callable):
        """注册状态进入钩子"""
        if state not in self.state_enter_hooks:
            self.state_enter_hooks[state] = []
        self.state_enter_hooks[state].append(hook)

    def register_exit_hook(self, state: DecisionState, hook: Callable):
        """注册状态退出钩子"""
        if state not in self.state_exit_hooks:
            self.state_exit_hooks[state] = []
        self.state_exit_hooks[state].append(hook)

    def _execute_enter_hooks(self, state: DecisionState):
        """执行状态进入钩子"""
        hooks = self.state_enter_hooks.get(state, [])
        for hook in hooks:
            try:
                hook(self.context)
            except Exception as e:
                logger.error(f"Error in enter hook for {state}: {e}")

    def _execute_exit_hooks(self, state: DecisionState):
        """执行状态退出钩子"""
        hooks = self.state_exit_hooks.get(state, [])
        for hook in hooks:
            try:
                hook(self.context)
            except Exception as e:
                logger.error(f"Error in exit hook for {state}: {e}")

    def register_error_handler(self, state: DecisionState, handler: Callable):
        """注册错误处理器"""
        self.error_handlers[state] = handler

    def _handle_error(self, state: DecisionState, reason: str, metadata: Optional[Dict]):
        """处理错误"""
        handler = self.error_handlers.get(state)
        if handler:
            try:
                handler(self.context, reason, metadata or {})
            except Exception as e:
                logger.error(f"Error in error handler for {state}: {e}")

    def get_allowed_transitions(self) -> List[DecisionState]:
        """获取当前状态允许的转换"""
        return self.ALLOWED_TRANSITIONS.get(self.current_state, []).copy()

    def is_terminal_state(self) -> bool:
        """检查是否为终态"""
        return self.current_state in [
            DecisionState.COMPLETED,
            DecisionState.FAILED,
            DecisionState.CANCELLED,
        ]

    def get_state_summary(self) -> Dict:
        """获取状态摘要"""
        return {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "interval": self.interval,
            "current_state": self.current_state,
            "current_phase": self.context.current_phase,
            "duration_seconds": (datetime.now() - self.context.start_time).total_seconds(),
            "state_history": [
                {
                    "from": t.from_state,
                    "to": t.to_state,
                    "timestamp": t.timestamp.isoformat(),
                    "reason": t.reason,
                }
                for t in self.state_history
            ],
            "has_analyst_reports": len(self.context.analyst_reports) > 0,
            "has_debate_result": self.context.debate_result is not None,
            "has_risk_assessment": len(self.context.risk_assessment) > 0,
            "has_execution_plan": self.context.execution_plan is not None,
            "has_final_decision": self.context.final_decision is not None,
            "error_message": self.context.error_message,
        }

    def cancel(self, reason: str = ""):
        """取消决策流程"""
        return self.transition_to(DecisionState.CANCELLED, reason or "Cancelled by user")

    def fail(self, error_message: str, metadata: Optional[Dict] = None):
        """标记决策失败"""
        metadata = metadata or {}
        metadata["error"] = error_message
        return self.transition_to(DecisionState.FAILED, error_message, metadata)

    def complete(self, final_decision: Dict):
        """完成决策流程"""
        return self.transition_to(
            DecisionState.COMPLETED,
            "Decision completed",
            {"final_decision": final_decision}
        )


class StateMachineManager:
    """状态机管理器 - 管理多个决策流程的状态机"""

    def __init__(self):
        self.machines: Dict[str, DecisionStateMachine] = {}

    def create_machine(self, decision_id: str, symbol: str, interval: str) -> DecisionStateMachine:
        """创建新的状态机"""
        machine = DecisionStateMachine(decision_id, symbol, interval)
        self.machines[decision_id] = machine
        return machine

    def get_machine(self, decision_id: str) -> Optional[DecisionStateMachine]:
        """获取状态机"""
        return self.machines.get(decision_id)

    def remove_machine(self, decision_id: str):
        """移除状态机"""
        if decision_id in self.machines:
            del self.machines[decision_id]

    def get_active_machines(self) -> List[DecisionStateMachine]:
        """获取所有活跃的状态机（非终态）"""
        return [
            m for m in self.machines.values()
            if not m.is_terminal_state()
        ]

    def get_all_summaries(self) -> List[Dict]:
        """获取所有状态机摘要"""
        return [m.get_state_summary() for m in self.machines.values()]


# 全局单例
_state_machine_manager = StateMachineManager()


def get_state_machine_manager() -> StateMachineManager:
    """获取全局状态机管理器"""
    return _state_machine_manager
