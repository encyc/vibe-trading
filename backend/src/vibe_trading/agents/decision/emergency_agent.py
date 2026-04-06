"""
Emergency Decision Agent

Handles emergency trading decisions for trigger events.
"""
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from pi_agent_core import Agent, AgentOptions
from pi_ai.config import get_model_from_config

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import TRADER_PROMPT
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext, create_trading_agent
from vibe_trading.triggers.base_trigger import TriggerEvent, TriggerSeverity
from vibe_trading.agents.risk_mgmt.emergency_agent import EmergencyAssessment

logger = logging.getLogger(__name__)


@dataclass
class EmergencyDecision:
    """Emergency trading decision result"""
    action: str  # EXECUTE/IGNORE/DEFER
    decision_type: str  # CLOSE_ALL/CLOSE_PARTIAL/HEDGE/REDUCE
    execution_plan: Optional[Dict] = None
    rationale: str = ""
    confidence: float = 0.0
    estimated_impact: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "action": self.action,
            "decision_type": self.decision_type,
            "execution_plan": self.execution_plan,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "estimated_impact": self.estimated_impact,
            "timestamp": datetime.now().isoformat(),
        }


class EmergencyDecisionAgent:
    """
    Emergency decision agent
    
    Makes rapid trading decisions for emergency situations.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """
        Initialize emergency decision agent
        
        Args:
            config: Agent configuration (optional, uses default if not provided)
        """
        if config is None:
            config = AgentConfig(
                role=AgentRole.TRADER,
                name="EmergencyDecisionAgent",
                model=get_settings().llm_config_name,
            )
        
        self.config = config
        self._system_prompt = self._get_emergency_prompt()
        self._agent: Optional[Agent] = None
        self._tool_context: Optional[ToolContext] = None
    
    def _get_emergency_prompt(self) -> str:
        """Get emergency-specific system prompt"""
        return """You are an Emergency Decision Agent for cryptocurrency trading.

Your role is to make rapid, decisive trading decisions in emergency situations.

EMERGENCY DECISION PRINCIPLES:
1. Capital preservation is the #1 priority
2. Act decisively when action is required
3. Consider the risk/reward of each decision
4. Provide clear execution plans

DECISION TYPES:
- CLOSE_ALL: Close all positions immediately
- CLOSE_PARTIAL: Close partial positions (e.g., 50-80%)
- HEDGE: Open hedge positions to offset risk
- REDUCE: Reduce position sizes
- DEFER: Defer decision for human review

EXECUTION PRIORITY:
1. CRITICAL triggers: Execute immediately (no confirmation needed)
2. HIGH triggers: Execute with rapid confirmation
3. MEDIUM triggers: Execute after brief review
4. LOW triggers: Manual review required

When making emergency decisions, consider:
1. Risk assessment recommendation
2. Trigger severity and urgency
3. Current positions and exposure
4. Market conditions and liquidity
5. Potential slippage and impact

Provide your decision in a clear, structured format."""
    
    async def initialize(self, tool_context: ToolContext, enable_streaming: bool = False) -> None:
        """
        Initialize agent
        
        Args:
            tool_context: Tool context
            enable_streaming: Whether to enable streaming (disabled for emergencies)
        """
        self._tool_context = tool_context
        
        # Get model
        model = get_model_from_config(self.config.model)
        
        # Create agent with emergency prompt
        agent_options = AgentOptions(
            initial_state={
                "system_prompt": self._system_prompt,
                "model": model,
            }
        )
        
        self._agent = Agent(agent_options)
        logger.info("EmergencyDecisionAgent initialized")
    
    async def emergency_decide(
        self,
        trigger_event: TriggerEvent,
        risk_assessment: EmergencyAssessment,
        current_positions: List[Dict],
        account_balance: float,
    ) -> EmergencyDecision:
        """
        Make emergency trading decision
        
        Args:
            trigger_event: Trigger event that initiated emergency
            risk_assessment: Risk assessment from emergency risk agent
            current_positions: Current positions
            account_balance: Account balance
            
        Returns:
            EmergencyDecision result
        """
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")
        
        # Build decision prompt
        prompt = self._build_decision_prompt(
            trigger_event, risk_assessment, current_positions, account_balance
        )
        
        # Get agent response
        response = await self._agent.run(prompt)
        
        # Parse response
        decision = self._parse_decision(response, trigger_event, risk_assessment)
        
        logger.info(f"Emergency decision made: {decision.decision_type} (confidence={decision.confidence:.2f})")
        return decision
    
    def _build_decision_prompt(
        self,
        trigger_event: TriggerEvent,
        risk_assessment: EmergencyAssessment,
        current_positions: List[Dict],
        account_balance: float,
    ) -> str:
        """Build decision prompt"""
        prompt = f"""EMERGENCY TRADING DECISION REQUEST
================================
Symbol: {trigger_event.symbol or 'N/A'}
Timestamp: {datetime.fromtimestamp(trigger_event.timestamp / 1000).isoformat()}
Severity: {trigger_event.severity.value}
Trigger: {trigger_event.trigger_name}

TRIGGER DATA:
{trigger_event.data}

RISK ASSESSMENT:
Action: {risk_assessment.action_type}
Should Act: {risk_assessment.should_act}
Urgency: {risk_assessment.urgency}
Confidence: {risk_assessment.confidence:.2f}
Rationale: {risk_assessment.rationale}
"""
        
        if risk_assessment.recommended_action:
            prompt += f"\nRecommended Action:\n{risk_assessment.recommended_action}\n"
        
        prompt += f"""
CURRENT POSITIONS:
"""
        
        if current_positions:
            for i, pos in enumerate(current_positions, 1):
                prompt += f"""
{i}. {pos.get('symbol', 'N/A')}
   Side: {pos.get('side', 'N/A')}
   Size: {pos.get('position_amount', 'N/A')}
   Entry: {pos.get('entry_price', 'N/A')}
   Current: {pos.get('mark_price', 'N/A')}
   PnL: {pos.get('unrealized_profit', 'N/A')}
"""
        else:
            prompt += "No open positions\n"
        
        prompt += f"""
ACCOUNT STATUS:
Balance: {account_balance} USDT

Please provide your emergency decision in the following format:

ACTION: [EXECUTE/IGNORE/DEFER]
DECISION_TYPE: [CLOSE_ALL/CLOSE_PARTIAL/HEDGE/REDUCE]
CONFIDENCE: [0.0-1.0]
RATIONALE: [Clear explanation]

EXECUTION_PLAN: (if action is EXECUTE)
{{
  "orders": [
    {{
      "symbol": "BTCUSDT",
      "side": "SELL",
      "type": "MARKET",
      "quantity": 0.1,
      "reason": "Close position due to price drop"
    }}
  ],
  "timing": "immediate",
  "estimated_impact": {{
    "pnl_impact": "estimated pnl impact",
    "capital_preserved": "amount"
  }}
}}

For CRITICAL severity events, EXECUTE is expected without DEFER.
For HIGH severity events, EXECUTE is expected with proper justification.
For MEDIUM/LOW severity events, DEFER or careful EXECUTE is expected.
"""
        
        return prompt
    
    def _parse_decision(
        self,
        response: str,
        trigger_event: TriggerEvent,
        risk_assessment: EmergencyAssessment
    ) -> EmergencyDecision:
        """
        Parse agent response into EmergencyDecision
        
        Args:
            response: Agent response text
            trigger_event: Original trigger event
            risk_assessment: Risk assessment
            
        Returns:
            EmergencyDecision instance
        """
        # Parse response (simple parsing, can be enhanced)
        lines = response.strip().split('\n')
        
        action = "DEFER"
        decision_type = "DEFER"
        confidence = 0.5
        rationale = response
        execution_plan = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("ACTION:"):
                action = line.split(":", 1)[1].strip().upper()
            elif line.startswith("DECISION_TYPE:"):
                decision_type = line.split(":", 1)[1].strip().upper()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("RATIONALE:"):
                rationale = line.split(":", 1)[1].strip()
        
        # For CRITICAL events, force execute
        if trigger_event.severity == TriggerSeverity.CRITICAL:
            action = "EXECUTE"
            if decision_type == "DEFER":
                decision_type = "CLOSE_ALL"
            confidence = max(confidence, 0.9)
        
        # For HIGH events with should_act=True, recommend execute
        elif trigger_event.severity == TriggerSeverity.HIGH and risk_assessment.should_act:
            if action == "DEFER":
                action = "EXECUTE"
            confidence = max(confidence, 0.8)
        
        # Build simple execution plan if action is EXECUTE
        if action == "EXECUTE" and not execution_plan:
            execution_plan = {
                "action": decision_type,
                "reason": rationale,
                "trigger": trigger_event.trigger_name,
                "urgency": risk_assessment.urgency,
            }
        
        return EmergencyDecision(
            action=action,
            decision_type=decision_type,
            execution_plan=execution_plan,
            rationale=rationale,
            confidence=confidence,
        )
    
    async def create_suggestion(
        self,
        trigger_event: TriggerEvent,
        risk_assessment: EmergencyAssessment,
        current_positions: List[Dict],
    ) -> Dict:
        """
        Create a suggestion (not a decision) for HIGH severity events
        
        Args:
            trigger_event: Trigger event
            risk_assessment: Risk assessment
            current_positions: Current positions
            
        Returns:
            Suggestion dictionary
        """
        return {
            "trigger_name": trigger_event.trigger_name,
            "severity": trigger_event.severity.value,
            "risk_assessment": risk_assessment.to_dict(),
            "suggested_action": risk_assessment.action_type,
            "urgency": risk_assessment.urgency,
            "positions_affected": len(current_positions),
            "requires_confirmation": True,
            "timestamp": datetime.now().isoformat(),
        }
