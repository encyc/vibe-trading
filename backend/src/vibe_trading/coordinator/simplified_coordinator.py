"""
Simplified Trading Coordinator

Implements a 3-phase simplified decision flow:
1. Technical Analysis
2. Researcher Debate
3. Decision
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from pi_logger import get_logger, step, done, info

from vibe_trading.config.agent_config import AgentConfig, AgentRole, AgentTeamConfig
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext, create_trading_agent
from vibe_trading.agents.analysts.technical_analyst import create_technical_analyst
from vibe_trading.agents.researchers.researcher_agents import (
    BullResearcherAgent,
    BearResearcherAgent,
    ResearchManagerAgent,
    run_debate_round,
)
from vibe_trading.agents.decision.decision_agents import (
    create_trader,
    create_portfolio_manager,
)
from vibe_trading.data_sources.macro_storage import MacroStorage, get_macro_storage
from vibe_trading.data_sources.macro_storage import MacroState

logger = logging.getLogger(__name__)
log = get_logger("SimplifiedCoordinator")


@dataclass
class TradingContext:
    """Trading context"""
    symbol: str
    interval: str
    current_price: float
    klines: list
    indicators: dict
    market_data: dict
    timestamp: int


@dataclass
class TradingDecision:
    """Trading decision result"""
    symbol: str
    timestamp: int
    decision: str  # STRONG BUY/BUY/WEAK BUY/HOLD/WEAK SELL/SELL/STRONG SELL
    rationale: str
    execution_instructions: Optional[dict] = None
    agent_outputs: dict = field(default_factory=dict)
    macro_state: Optional[MacroState] = None


class SimplifiedTradingCoordinator:
    """
    Simplified trading coordinator
    
    Implements a 3-phase decision flow:
    1. Technical Analysis (only technical analyst)
    2. Researcher Debate (includes macro state)
    3. Decision (includes risk check)
    """
    
    def __init__(
        self,
        symbol: str,
        interval: str = "30m",
        macro_storage: Optional[MacroStorage] = None,
        agent_config: Optional[AgentTeamConfig] = None,
    ):
        """
        Initialize simplified coordinator
        
        Args:
            symbol: Trading symbol
            interval: Time interval
            macro_storage: Macro storage instance
            agent_config: Agent configuration
        """
        self.symbol = symbol
        self.interval = interval
        self.macro_storage = macro_storage or get_macro_storage()
        self.agent_config = agent_config or AgentTeamConfig()
        
        # Agent instances
        self._tool_context: Optional[ToolContext] = None
        self._technical_analyst = None
        self._bull_researcher: Optional[BullResearcherAgent] = None
        self._bear_researcher: Optional[BearResearcherAgent] = None
        self._research_manager: Optional[ResearchManagerAgent] = None
        self._portfolio_manager = None
        
        logger.info(f"SimplifiedTradingCoordinator initialized for {symbol}")
    
    async def initialize(self) -> None:
        """Initialize all agents"""
        self._tool_context = ToolContext(
            symbol=self.symbol,
            interval=self.interval,
        )
        
        # Initialize technical analyst
        if self.agent_config.technical_analyst.enabled:
            self._technical_analyst = await create_technical_analyst(self._tool_context)
            logger.info("Technical analyst initialized")
        
        # Initialize researchers
        if self.agent_config.bull_researcher.enabled:
            self._bull_researcher = BullResearcherAgent()
            await self._bull_researcher.initialize(self._tool_context)
        
        if self.agent_config.bear_researcher.enabled:
            self._bear_researcher = BearResearcherAgent()
            await self._bear_researcher.initialize(self._tool_context)
        
        if self.agent_config.research_manager.enabled:
            self._research_manager = ResearchManagerAgent()
            await self._research_manager.initialize(self._tool_context)
        
        # Initialize portfolio manager
        if self.agent_config.portfolio_manager.enabled:
            self._portfolio_manager = await create_portfolio_manager(
                self._tool_context
            )
        
        logger.info("Simplified coordinator agents initialized")
    
    async def simplified_decision_flow(
        self,
        current_price: float,
        account_balance: float = 10000.0,
        current_positions: Optional[List[Dict]] = None,
    ) -> TradingDecision:
        """
        Execute simplified 3-phase decision flow
        
        Args:
            current_price: Current price
            account_balance: Account balance
            current_positions: Current positions
            
        Returns:
            Trading decision
        """
        start_time = datetime.now()
        decision_id = f"{self.symbol}_{int(start_time.timestamp() * 1000)}"
        
        logger.info(f"Starting simplified decision flow for {self.symbol} @ ${current_price:.2f}")
        
        # Prepare context
        context = await self._prepare_context(current_price)
        current_positions = current_positions or []
        
        # Agent outputs
        agent_outputs = {}
        
        # Phase 1: Technical Analysis
        logger.info("Phase 1: Technical Analysis")
        tech_reports = await self._run_technical_analysis(context)
        agent_outputs["technical"] = tech_reports
        
        # Phase 2: Load Macro State
        logger.info("Loading macro state")
        macro_state = await self._load_macro_state()
        agent_outputs["macro_state"] = macro_state
        
        # Phase 3: Researcher Debate
        logger.info("Phase 2: Researcher Debate")
        debate_result = await self._run_research_debate(
            context,
            tech_reports,
            macro_state,
        )
        agent_outputs["debate"] = debate_result
        
        # Phase 4: Decision
        logger.info("Phase 3: Decision")
        final_decision = await self._make_final_decision(
            tech_reports,
            debate_result,
            macro_state,
            account_balance,
            current_positions,
        )
        
        logger.info(f"Simplified decision flow completed: {final_decision.decision}")
        
        return TradingDecision(
            symbol=self.symbol,
            timestamp=int(datetime.now().timestamp() * 1000),
            decision=final_decision.decision,
            rationale=final_decision.rationale,
            execution_instructions=final_decision.execution_instructions,
            agent_outputs=agent_outputs,
            macro_state=macro_state,
        )
    
    async def _prepare_context(self, current_price: float) -> TradingContext:
        """Prepare trading context"""
        # This would normally fetch klines and indicators
        # For now, return a basic context
        return TradingContext(
            symbol=self.symbol,
            interval=self.interval,
            current_price=current_price,
            klines=[],
            indicators={},
            market_data={"price": current_price},
            timestamp=int(datetime.now().timestamp() * 1000),
        )
    
    async def _run_technical_analysis(
        self,
        context: TradingContext,
    ) -> Dict:
        """
        Run technical analysis
        
        Args:
            context: Trading context
            
        Returns:
            Technical analysis reports
        """
        if not self._technical_analyst:
            return {}
        
        try:
            report = await self._technical_analyst.analyze(
                price=context.current_price,
                klines=context.klines,
                indicators=context.indicators,
            )
            return {"technical": report}
        except Exception as e:
            logger.error(f"Error in technical analysis: {e}", exc_info=True)
            return {"technical": f"Error: {str(e)}"}
    
    async def _load_macro_state(self) -> Optional[MacroState]:
        """Load latest macro state"""
        try:
            macro_state = await self.macro_storage.get_latest_state(self.symbol)
            if macro_state:
                logger.info(
                    f"Loaded macro state: {macro_state.market_regime} "
                    f"(trend={macro_state.trend_direction}, "
                    f"sentiment={macro_state.overall_sentiment})"
                )
            else:
                logger.warning("No macro state found")
            return macro_state
        except Exception as e:
            logger.error(f"Error loading macro state: {e}", exc_info=True)
            return None
    
    async def _run_research_debate(
        self,
        context: TradingContext,
        tech_reports: Dict,
        macro_state: Optional[MacroState],
    ) -> Dict:
        """
        Run researcher debate with macro state
        
        Args:
            context: Trading context
            tech_reports: Technical analysis reports
            macro_state: Macro state
            
        Returns:
            Debate result
        """
        if not (self._bull_researcher and self._bear_researcher and self._research_manager):
            return {}
        
        try:
            # Build research context
            research_context = {
                "symbol": context.symbol,
                "price": context.current_price,
                "technical_analysis": tech_reports,
                "macro_state": macro_state.to_dict() if macro_state else None,
            }
            
            # Run debate
            debate_result = await run_debate_round(
                bull_researcher=self._bull_researcher,
                bear_researcher=self._bear_researcher,
                research_manager=self._research_manager,
                research_context=research_context,
                round_number=1,
            )
            
            return {"debate": debate_result}
        except Exception as e:
            logger.error(f"Error in research debate: {e}", exc_info=True)
            return {"debate": f"Error: {str(e)}"}
    
    async def _make_final_decision(
        self,
        tech_reports: Dict,
        debate_result: Dict,
        macro_state: Optional[MacroState],
        account_balance: float,
        current_positions: List[Dict],
    ) -> Dict:
        """
        Make final decision with risk check
        
        Args:
            tech_reports: Technical reports
            debate_result: Debate result
            macro_state: Macro state
            account_balance: Account balance
            current_positions: Current positions
            
        Returns:
            Final decision
        """
        if not self._portfolio_manager:
            return {
                "decision": "HOLD",
                "rationale": "No portfolio manager available",
            }
        
        try:
            # Build decision context
            decision_context = {
                "symbol": self.symbol,
                "account_balance": account_balance,
                "positions": current_positions,
                "technical_analysis": tech_reports,
                "debate_result": debate_result,
                "macro_state": macro_state.to_dict() if macro_state else None,
            }
            
            # Basic risk check
            risk_assessment = self._perform_risk_check(
                account_balance,
                current_positions,
                macro_state,
            )
            
            # Make decision
            decision = await self._portfolio_manager.make_final_decision(
                analyst_reports=tech_reports,
                research_recommendation=debate_result,
                risk_assessment=risk_assessment,
                current_positions=current_positions,
                account_balance=account_balance,
            )
            
            return decision
        except Exception as e:
            logger.error(f"Error making final decision: {e}", exc_info=True)
            return {
                "decision": "HOLD",
                "rationale": f"Error: {str(e)}",
            }
    
    def _perform_risk_check(
        self,
        account_balance: float,
        current_positions: List[Dict],
        macro_state: Optional[MacroState],
    ) -> Dict:
        """
        Perform basic risk check
        
        Args:
            account_balance: Account balance
            current_positions: Current positions
            macro_state: Macro state
            
        Returns:
            Risk assessment
        """
        risk_level = "LOW"
        position_size_pct = 0.0
        stop_loss_pct = 5.0
        
        # Check macro risk
        if macro_state:
            if macro_state.market_regime == "BEAR":
                risk_level = "HIGH"
                position_size_pct = 0.2  # Reduce position size
            elif macro_state.market_regime == "BULL":
                risk_level = "LOW"
                position_size_pct = 0.5  # Increase position size
            else:
                risk_level = "MEDIUM"
                position_size_pct = 0.3  # Normal position size
        
        # Check current positions
        total_exposure = sum(
            pos.get("position_amount", 0) for pos in current_positions
        )
        
        if total_exposure > account_balance * 0.8:
            risk_level = "HIGH"
            position_size_pct = 0.1  # Very conservative
        
        return {
            "risk_level": risk_level,
            "position_size_pct": position_size_pct,
            "stop_loss_pct": stop_loss_pct,
            "total_exposure": total_exposure,
            "account_balance": account_balance,
        }