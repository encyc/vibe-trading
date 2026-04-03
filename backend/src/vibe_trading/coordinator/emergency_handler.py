"""
Emergency Handler

Handles emergency event processing and coordination.
"""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass

from vibe_trading.triggers.base_trigger import TriggerEvent, TriggerSeverity
from vibe_trading.triggers.trigger_registry import TriggerRegistry
from vibe_trading.agents.risk_mgmt.emergency_agent import (
    EmergencyRiskAgent,
    EmergencyAssessment,
)
from vibe_trading.agents.decision.emergency_agent import (
    EmergencyDecisionAgent,
    EmergencyDecision,
)
from vibe_trading.coordinator.thread_manager import ThreadManager, get_thread_manager
from vibe_trading.coordinator.shared_state import SharedStateManager, get_shared_state_manager
from vibe_trading.coordinator.event_queue import EventQueue, get_event_queue

logger = logging.getLogger(__name__)


@dataclass
class EmergencyAction:
    """Emergency action result"""
    action: str  # EXECUTED/DEFERRED/IGNORED
    decision: EmergencyDecision
    execution_result: Optional[Dict] = None
    error: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "action": self.action,
            "decision": self.decision.to_dict() if self.decision else None,
            "execution_result": self.execution_result,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class EmergencyHandler:
    """
    Emergency event handler
    
    Coordinates emergency response including:
    - Trigger event processing
    - Risk assessment
    - Decision making
    - Action execution
    - Thread coordination
    """
    
    def __init__(
        self,
        thread_manager: Optional[ThreadManager] = None,
        shared_state: Optional[SharedStateManager] = None,
        event_queue: Optional[EventQueue] = None,
    ):
        """
        Initialize emergency handler
        
        Args:
            thread_manager: Thread manager instance
            shared_state: Shared state manager instance
            event_queue: Event queue instance
        """
        self.thread_manager = thread_manager or get_thread_manager()
        self.shared_state = shared_state or get_shared_state_manager()
        self.event_queue = event_queue or get_event_queue()
        
        # Initialize agents
        self._risk_agent: Optional[EmergencyRiskAgent] = None
        self._decision_agent: Optional[EmergencyDecisionAgent] = None
        
        # Statistics
        self._total_handled = 0
        self._executed = 0
        self._deferred = 0
        self._ignored = 0
        self._errors = 0
        
        logger.info("EmergencyHandler initialized")
    
    async def initialize(self, symbol: str = "BTCUSDT") -> None:
        """
        Initialize emergency agents
        
        Args:
            symbol: Trading symbol
        """
        # Create tool context
        from vibe_trading.agents.agent_factory import ToolContext
        
        tool_context = ToolContext(
            symbol=symbol,
            interval="1m",
        )
        
        # Initialize agents
        self._risk_agent = EmergencyRiskAgent()
        await self._risk_agent.initialize(tool_context, enable_streaming=False)
        
        self._decision_agent = EmergencyDecisionAgent()
        await self._decision_agent.initialize(tool_context, enable_streaming=False)
        
        logger.info(f"EmergencyHandler agents initialized for {symbol}")
    
    async def handle_emergency_event(
        self,
        trigger_event: TriggerEvent,
        current_positions: List[Dict],
        account_balance: float,
        market_data: Optional[Dict] = None,
    ) -> EmergencyAction:
        """
        Handle emergency event with分级权限
        
        Args:
            trigger_event: Trigger event
            current_positions: Current positions
            account_balance: Account balance
            market_data: Optional market data
            
        Returns:
            EmergencyAction result
        """
        try:
            self._total_handled += 1
            
            logger.warning(f"Handling emergency event: {trigger_event.trigger_name} (severity={trigger_event.severity.value})")
            
            # Step 1: Risk assessment
            risk_assessment = await self._run_risk_assessment(
                trigger_event, current_positions, account_balance, market_data
            )
            
            # Step 2: Make decision based on severity
            if trigger_event.severity == TriggerSeverity.CRITICAL:
                # CRITICAL: Direct operation
                action = await self._handle_critical_event(
                    trigger_event, risk_assessment, current_positions, account_balance
                )
            elif trigger_event.severity == TriggerSeverity.HIGH:
                # HIGH: Suggestion authority
                action = await self._handle_high_event(
                    trigger_event, risk_assessment, current_positions, account_balance
                )
            else:
                # MEDIUM/LOW: Log only
                action = await self._handle_normal_event(
                    trigger_event, risk_assessment
                )
            
            # Update statistics
            if action.action == "EXECUTED":
                self._executed += 1
            elif action.action == "DEFERRED":
                self._deferred += 1
            elif action.action == "IGNORED":
                self._ignored += 1
            
            return action
            
        except Exception as e:
            self._errors += 1
            logger.error(f"Error handling emergency event: {e}", exc_info=True)
            
            return EmergencyAction(
                action="ERROR",
                decision=None,
                error=str(e),
            )
    
    async def _run_risk_assessment(
        self,
        trigger_event: TriggerEvent,
        current_positions: List[Dict],
        account_balance: float,
        market_data: Optional[Dict],
    ) -> EmergencyAssessment:
        """Run emergency risk assessment"""
        if not self._risk_agent:
            raise RuntimeError("Risk agent not initialized")
        
        assessment = await self._risk_agent.emergency_assess(
            trigger_event=trigger_event,
            current_positions=current_positions,
            account_balance=account_balance,
            market_data=market_data,
        )
        
        logger.info(f"Risk assessment: {assessment.action_type} (should_act={assessment.should_act})")
        return assessment
    
    async def _run_decision(
        self,
        trigger_event: TriggerEvent,
        risk_assessment: EmergencyAssessment,
        current_positions: List[Dict],
        account_balance: float,
    ) -> EmergencyDecision:
        """Run emergency decision"""
        if not self._decision_agent:
            raise RuntimeError("Decision agent not initialized")
        
        decision = await self._decision_agent.emergency_decide(
            trigger_event=trigger_event,
            risk_assessment=risk_assessment,
            current_positions=current_positions,
            account_balance=account_balance,
        )
        
        logger.info(f"Decision: {decision.decision_type} (action={decision.action})")
        return decision
    
    async def _handle_critical_event(
        self,
        trigger_event: TriggerEvent,
        risk_assessment: EmergencyAssessment,
        current_positions: List[Dict],
        account_balance: float,
    ) -> EmergencyAction:
        """
        Handle CRITICAL severity event (direct operation)
        
        Args:
            trigger_event: Trigger event
            risk_assessment: Risk assessment
            current_positions: Current positions
            account_balance: Account balance
            
        Returns:
            EmergencyAction result
        """
        logger.critical(f"CRITICAL event: {trigger_event.trigger_name} - Executing immediately")
        
        # Notify thread manager to enter emergency mode
        await self.thread_manager.notify_emergency_mode(trigger_event.to_dict())
        
        try:
            # Make decision
            decision = await self._run_decision(
                trigger_event, risk_assessment, current_positions, account_balance
            )
            
            # Execute action
            execution_result = await self._execute_emergency_action(decision, current_positions)
            
            # Notify emergency mode complete
            await self.thread_manager.notify_emergency_complete()
            
            return EmergencyAction(
                action="EXECUTED",
                decision=decision,
                execution_result=execution_result,
            )
            
        except Exception as e:
            logger.error(f"Error executing critical action: {e}", exc_info=True)
            await self.thread_manager.notify_emergency_complete()
            
            return EmergencyAction(
                action="ERROR",
                decision=None,
                error=str(e),
            )
    
    async def _handle_high_event(
        self,
        trigger_event: TriggerEvent,
        risk_assessment: EmergencyAssessment,
        current_positions: List[Dict],
        account_balance: float,
    ) -> EmergencyAction:
        """
        Handle HIGH severity event (suggestion authority)
        
        Args:
            trigger_event: Trigger event
            risk_assessment: Risk assessment
            current_positions: Current positions
            account_balance: Account balance
            
        Returns:
            EmergencyAction result
        """
        logger.warning(f"HIGH event: {trigger_event.trigger_name} - Creating suggestion")
        
        # Create suggestion
        if not self._decision_agent:
            raise RuntimeError("Decision agent not initialized")
        
        suggestion = await self._decision_agent.create_suggestion(
            trigger_event=trigger_event,
            risk_assessment=risk_assessment,
            current_positions=current_positions,
        )
        
        # Send suggestion to main thread
        from vibe_trading.agents.messaging import get_message_broker, MessageType
        
        message_broker = get_message_broker()
        message_broker.send(
            sender="emergency_handler",
            receiver="main_thread",
            message_type=MessageType.WARNING,
            content={
                "type": "emergency_suggestion",
                "suggestion": suggestion,
            },
            correlation_id=trigger_event.event_id,
        )
        
        logger.info(f"Suggestion sent to main thread: {suggestion.get('suggested_action')}")
        
        return EmergencyAction(
            action="DEFERRED",
            decision=None,
            execution_result={"suggestion": suggestion},
        )
    
    async def _handle_normal_event(
        self,
        trigger_event: TriggerEvent,
        risk_assessment: EmergencyAssessment,
    ) -> EmergencyAction:
        """
        Handle MEDIUM/LOW severity event (log only)
        
        Args:
            trigger_event: Trigger event
            risk_assessment: Risk assessment
            
        Returns:
            EmergencyAction result
        """
        logger.info(f"Normal event: {trigger_event.trigger_name} - Logging only")
        
        return EmergencyAction(
            action="IGNORED",
            decision=None,
            execution_result={"message": "Event logged, no action taken"},
        )
    
    async def _execute_emergency_action(
        self,
        decision: EmergencyDecision,
        current_positions: List[Dict],
    ) -> Dict:
        """
        Execute emergency action
        
        Args:
            decision: Emergency decision
            current_positions: Current positions
            
        Returns:
            Execution result
        """
        logger.info(f"Executing emergency action: {decision.decision_type}")
        
        # TODO: Implement actual order execution
        # This would integrate with OrderExecutor to close positions, hedge, etc.
        
        execution_result = {
            "decision_type": decision.decision_type,
            "positions_affected": len(current_positions),
            "timestamp": datetime.now().isoformat(),
            "status": "simulated",  # Change to "executed" when real execution is implemented
        }
        
        logger.info(f"Emergency action executed: {execution_result}")
        return execution_result
    
    async def process_event_queue(self) -> None:
        """Process events from the priority queue"""
        while True:
            try:
                # Get event from queue
                event = await self.event_queue.get()
                if event is None:
                    await asyncio.sleep(1)
                    continue
                
                # Handle event
                # Note: We need current_positions and account_balance from context
                # This is a placeholder - in real implementation, these would be passed
                current_positions = []
                account_balance = 0.0
                
                action = await self.handle_emergency_event(
                    trigger_event=event,
                    current_positions=current_positions,
                    account_balance=account_balance,
                )
                
                # Mark event as processed
                if action.action == "EXECUTED":
                    await self.event_queue.mark_completed(event.event_id, success=True)
                elif action.action == "ERROR":
                    await self.event_queue.mark_completed(event.event_id, success=False)
                else:
                    await self.event_queue.mark_ignored(event.event_id)
                
            except asyncio.CancelledError:
                logger.info("Event queue processing cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing event queue: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    def get_statistics(self) -> Dict:
        """
        Get handler statistics
        
        Returns:
            Dictionary of statistics
        """
        return {
            "total_handled": self._total_handled,
            "executed": self._executed,
            "deferred": self._deferred,
            "ignored": self._ignored,
            "errors": self._errors,
        }