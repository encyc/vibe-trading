"""
Emergency Risk Agent

Handles emergency risk assessment for trigger events.
"""
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from pi_agent_core import Agent, AgentOptions
from pi_ai.config import get_model_from_config

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import (
    CONSERVATIVE_DEBATOR_PROMPT,
)
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext, create_trading_agent
from vibe_trading.triggers.base_trigger import TriggerEvent, TriggerSeverity

logger = logging.getLogger(__name__)


@dataclass
class EmergencyAssessment:
    """Emergency risk assessment result"""
    should_act: bool  # Whether immediate action is required
    action_type: str  # CLOSE_POSITION/HEDGE/REDUCE/MANUAL
    urgency: str  # IMMEDIATE/URGENT/MODERATE
    rationale: str  # Explanation of the assessment
    recommended_action: Optional[Dict] = None  # Detailed action plan
    confidence: float = 0.0  # 0 to 1
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "should_act": self.should_act,
            "action_type": self.action_type,
            "urgency": self.urgency,
            "rationale": self.rationale,
            "recommended_action": self.recommended_action,
            "confidence": self.confidence,
            "timestamp": datetime.now().isoformat(),
        }


class EmergencyRiskAgent:
    """
    Emergency risk assessment agent
    
    Provides rapid risk assessment for emergency situations.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """
        Initialize emergency risk agent
        
        Args:
            config: Agent configuration (optional, uses default if not provided)
        """
        if config is None:
            config = AgentConfig(
                role=AgentRole.CONSERVATIVE_DEBATOR,
                name="EmergencyRiskAgent",
                model_name=get_settings().llm_config_name,
            )
        
        self.config = config
        self._system_prompt = self._get_emergency_prompt()
        self._agent: Optional[Agent] = None
        self._tool_context: Optional[ToolContext] = None
    
    def _get_emergency_prompt(self) -> str:
        """Get emergency-specific system prompt"""
        return """You are an Emergency Risk Agent for cryptocurrency trading.

Your role is to rapidly assess emergency situations and provide immediate risk recommendations.

EMERGENCY RESPONSE PRINCIPLES:
1. Capital preservation is the #1 priority
2. Act quickly but rationally - avoid panic decisions
3. Consider the severity and urgency of the situation
4. Provide clear, actionable recommendations

SEVERITY LEVELS:
- CRITICAL: Immediate action required (e.g., liquidation risk, 5%+ price drop)
- HIGH: Urgent action needed (e.g., margin ratio > 50%, 3% price drop)
- MEDIUM: Monitor closely (e.g., support breakout, volatility spike)
- LOW: Normal risk levels

ACTIONS:
- CLOSE_POSITION: Immediately close all positions
- HEDGE: Open hedge position to offset risk
- REDUCE: Reduce position size by 50-80%
- MANUAL: Requires human review

When assessing emergencies, consider:
1. Trigger severity and data
2. Current positions and exposure
3. Account balance and margin status
4. Market conditions and volatility
5. Risk/reward ratio of action vs inaction

Provide your assessment in a clear, structured format."""
    
    async def initialize(self, tool_context: ToolContext, enable_streaming: bool = False) -> None:
        """
        Initialize agent
        
        Args:
            tool_context: Tool context
            enable_streaming: Whether to enable streaming (disabled for emergencies)
        """
        self._tool_context = tool_context
        
        # Override system prompt
        from vibe_trading.agents.agent_factory import create_trading_agent
        from pi_agent_core import Agent
        
        # Get model
        model = get_model_from_config(self.config.model_name)
        
        # Create agent with emergency prompt
        agent_options = AgentOptions(
            initial_state={
                "system_prompt": self._system_prompt,
                "model": model,
            }
        )
        
        self._agent = Agent(agent_options)
        logger.info("EmergencyRiskAgent initialized")
    
    async def emergency_assess(
        self,
        trigger_event: TriggerEvent,
        current_positions: List[Dict],
        account_balance: float,
        market_data: Optional[Dict] = None,
    ) -> EmergencyAssessment:
        """
        Perform emergency risk assessment
        
        Args:
            trigger_event: Trigger event that initiated emergency
            current_positions: Current positions
            account_balance: Account balance
            market_data: Optional market data
            
        Returns:
            EmergencyAssessment result
        """
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")
        
        # Build assessment prompt
        prompt = self._build_assessment_prompt(
            trigger_event, current_positions, account_balance, market_data
        )
        
        # Get agent response
        response = await self._agent.run(prompt)
        
        # Parse response
        assessment = self._parse_assessment(response, trigger_event)
        
        logger.info(f"Emergency assessment completed: {assessment.action_type} (confidence={assessment.confidence:.2f})")
        return assessment
    
    def _build_assessment_prompt(
        self,
        trigger_event: TriggerEvent,
        current_positions: List[Dict],
        account_balance: float,
        market_data: Optional[Dict],
    ) -> str:
        """Build assessment prompt"""
        prompt = f"""EMERGENCY RISK ASSESSMENT REQUEST
================================
Symbol: {trigger_event.symbol or 'N/A'}
Timestamp: {datetime.fromtimestamp(trigger_event.timestamp / 1000).isoformat()}
Severity: {trigger_event.severity.value}
Trigger: {trigger_event.trigger_name}

TRIGGER DATA:
{trigger_event.data}

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
   Liquidation Price: {pos.get('liquidation_price', 'N/A')}
"""
        else:
            prompt += "No open positions\n"
        
        prompt += f"""
ACCOUNT STATUS:
Balance: {account_balance} USDT
"""
        
        if market_data:
            prompt += f"""
MARKET DATA:
Price: {market_data.get('price', 'N/A')}
24h Change: {market_data.get('price_change_percent', 'N/A')}%
Volume: {market_data.get('volume', 'N/A')}
"""
        
        prompt += """
Please provide your emergency assessment in the following format:

ACTION: [CLOSE_POSITION/HEDGE/REDUCE/MANUAL]
SHOULD_ACT: [true/false]
URGENCY: [IMMEDIATE/URGENT/MODERATE]
CONFIDENCE: [0.0-1.0]
RATIONALE: [Clear explanation]

RECOMMENDED_ACTION: (if applicable)
{
  "action": "specific action details",
  "positions_to_close": ["symbol1", "symbol2"],
  "position_sizes": {...},
  "timing": "immediate/within X minutes",
}
"""
        
        return prompt
    
    def _parse_assessment(self, response: str, trigger_event: TriggerEvent) -> EmergencyAssessment:
        """
        Parse agent response into EmergencyAssessment
        
        Args:
            response: Agent response text
            trigger_event: Original trigger event
            
        Returns:
            EmergencyAssessment instance
        """
        # Parse response (simple parsing, can be enhanced)
        lines = response.strip().split('\n')
        
        action_type = "MANUAL"
        should_act = False
        urgency = "MODERATE"
        confidence = 0.5
        rationale = response
        
        for line in lines:
            line = line.strip()
            if line.startswith("ACTION:"):
                action_type = line.split(":", 1)[1].strip().upper()
            elif line.startswith("SHOULD_ACT:"):
                should_act_str = line.split(":", 1)[1].strip().lower()
                should_act = should_act_str in ["true", "yes", "1"]
            elif line.startswith("URGENCY:"):
                urgency = line.split(":", 1)[1].strip().upper()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("RATIONALE:"):
                rationale = line.split(":", 1)[1].strip()
        
        # For CRITICAL events, force action
        if trigger_event.severity == TriggerSeverity.CRITICAL:
            should_act = True
            urgency = "IMMEDIATE"
            if action_type == "MANUAL":
                action_type = "CLOSE_POSITION"
        
        return EmergencyAssessment(
            should_act=should_act,
            action_type=action_type,
            urgency=urgency,
            rationale=rationale,
            confidence=confidence,
        )
    
    async def assess_liquidation_risk(
        self,
        positions: List[Dict],
        current_prices: Dict[str, float],
    ) -> EmergencyAssessment:
        """
        Assess liquidation risk for all positions
        
        Args:
            positions: Current positions
            current_prices: Current prices by symbol
            
        Returns:
            EmergencyAssessment result
        """
        high_risk_positions = []
        
        for pos in positions:
            symbol = pos.get('symbol')
            liquidation_price = pos.get('liquidation_price', 0)
            
            if liquidation_price <= 0:
                continue
            
            current_price = current_prices.get(symbol, 0)
            if current_price <= 0:
                continue
            
            # Calculate distance to liquidation
            side = pos.get('side', 'LONG')
            if side == 'LONG':
                distance_pct = (current_price - liquidation_price) / current_price
            else:
                distance_pct = (liquidation_price - current_price) / current_price
            
            # Check if within 10% of liquidation
            if distance_pct < 0.1:
                high_risk_positions.append({
                    'symbol': symbol,
                    'distance_pct': distance_pct,
                    'position': pos,
                })
        
        if high_risk_positions:
            return EmergencyAssessment(
                should_act=True,
                action_type="CLOSE_POSITION",
                urgency="IMMEDIATE",
                rationale=f"Liquidation risk detected for {len(high_risk_positions)} position(s)",
                recommended_action={
                    "positions_to_close": [p['symbol'] for p in high_risk_positions],
                    "reason": "Positions within 10% of liquidation price",
                },
                confidence=0.95,
            )
        
        return EmergencyAssessment(
            should_act=False,
            action_type="MANUAL",
            urgency="MODERATE",
            rationale="No immediate liquidation risk detected",
            confidence=0.8,
        )
