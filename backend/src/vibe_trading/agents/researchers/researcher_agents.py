"""
研究员团队 Agent

包括看涨研究员、看跌研究员和研究经理（增强版）。
"""
from typing import Dict, List, Optional

from pi_agent_core import Agent, AgentOptions
from pi_ai.config import get_model_from_config
from pi_logger import get_logger

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import (
    BULL_RESEARCHER_PROMPT,
    BEAR_RESEARCHER_PROMPT,
    RESEARCH_MANAGER_PROMPT,
)
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext, setup_streaming
from vibe_trading.agents.researchers.debate_analyzer import (
    ArgumentExtractor,
    DebateEvaluator,
    RecommendationEngine,
    DebateScorecard,
    InvestmentRecommendation,
    Argument,
    ArgumentCategory,
    ArgumentStrength,
)

logger = get_logger(__name__)


class ResearcherAgent:
    """研究员 Agent 基类"""

    def __init__(self, config: AgentConfig, system_prompt: str):
        self.config = config
        self._system_prompt = system_prompt
        self._agent: Optional[Agent] = None
        self._tool_context: Optional[ToolContext] = None

        # 添加辩论分析工具
        self._argument_extractor = ArgumentExtractor()
        self._my_arguments: List[Argument] = []

    async def initialize(self, tool_context: ToolContext, enable_streaming: bool = True) -> None:
        """初始化 Agent"""
        self._tool_context = tool_context

        # ========== 改进: 使用create_trading_agent以获得tools支持 ==========
        from vibe_trading.agents.agent_factory import create_trading_agent
        from vibe_trading.config.agent_config import AgentConfig

        # 从角色推断
        role_map = {
            "Bull Researcher": "bull_researcher",
            "Bear Researcher": "bear_researcher",
        }

        role = role_map.get(self.config.name, "researcher")

        config = AgentConfig(
            name=self.config.name,
            role=role,
            temperature=0.7,
        )

        self._agent = await create_trading_agent(
            config=config,
            tool_context=tool_context,
            enable_streaming=enable_streaming,
            agent_name=self.config.name,
        )

        logger.info(f"{self.config.name} Agent initialized for {tool_context.symbol}")

    async def respond(
        self,
        context: str,
        debate_history: Optional[str] = None,
        opponent_argument: Optional[str] = None,
        extract_arguments: bool = True,
    ) -> str:
        """生成回应（增强版）"""
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # 构建提示
        prompt = self._build_debate_prompt(context, debate_history, opponent_argument)

        await self._agent.prompt(prompt)

        # 获取响应
        messages = self._agent.state.messages
        if messages:
            last_assistant = [m for m in messages if getattr(m, "role", None) == "assistant"]
            if last_assistant:
                content = last_assistant[-1].content
                if isinstance(content, list):
                    response = "".join(getattr(c, "text", str(c)) for c in content)
                else:
                    response = str(content)

                # 提取论点
                if extract_arguments:
                    self._my_arguments = self._argument_extractor.extract_arguments(
                        response,
                        "bull" if "bull" in self.config.role.value.lower() else "bear"
                    )

                return response

        return "Response failed - no response from agent"

    def _build_debate_prompt(
        self,
        context: str,
        debate_history: Optional[str] = None,
        opponent_argument: Optional[str] = None,
    ) -> str:
        """构建辩论提示"""
        prompt = f"""Market Context for {self._tool_context.symbol}:

{context}

"""

        if debate_history:
            prompt += f"""
Previous Debate History:
{debate_history}

"""

        if opponent_argument:
            prompt += f"""
Opponent's Argument:
{opponent_argument}

请针对对方观点进行有针对性的反驳。
"""

        prompt += f"""
Please provide your {self.config.role.value.replace('_', ' ')} perspective.

你的发言应:
1. 观点明确，逻辑清晰
2. 提供具体数据或证据支持
3. 回应对方的核心论点
4. 指出对方论点的潜在问题
"""

        return prompt

    def get_my_arguments(self) -> List[Argument]:
        """获取我提出的论点"""
        return self._my_arguments

    def get_argument_summary(self) -> Dict:
        """获取论点摘要"""
        if not self._my_arguments:
            return {"total": 0, "by_category": {}, "by_strength": {}}

        # 按类别统计
        by_category = {}
        for arg in self._my_arguments:
            cat = arg.category.value
            by_category[cat] = by_category.get(cat, 0) + 1

        # 按强度统计
        by_strength = {s.value: 0 for s in ArgumentStrength}
        for arg in self._my_arguments:
            by_strength[arg.strength.value] += 1

        return {
            "total": len(self._my_arguments),
            "by_category": by_category,
            "by_strength": by_strength,
        }


class BullResearcherAgent(ResearcherAgent):
    """看涨研究员 Agent (增强版)"""

    def __init__(self, config: Optional[AgentConfig] = None):
        config = config or AgentConfig(
            name="Bull Researcher",
            role=AgentRole.BULL_RESEARCHER,
            temperature=0.8,
        )
        super().__init__(config, BULL_RESEARCHER_PROMPT)


class BearResearcherAgent(ResearcherAgent):
    """看跌研究员 Agent (增强版)"""

    def __init__(self, config: Optional[AgentConfig] = None):
        config = config or AgentConfig(
            name="Bear Researcher",
            role=AgentRole.BEAR_RESEARCHER,
            temperature=0.8,
        )
        super().__init__(config, BEAR_RESEARCHER_PROMPT)


class ResearchManagerAgent:
    """研究经理 Agent (增强版)"""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig(
            name="Research Manager",
            role=AgentRole.RESEARCH_MANAGER,
            temperature=0.5,
        )
        self._agent: Optional[Agent] = None
        self._tool_context: Optional[ToolContext] = None

        # 添加辩论评估和建议引擎
        self._debate_evaluator = DebateEvaluator()
        self._recommendation_engine = RecommendationEngine()

    async def initialize(self, tool_context: ToolContext) -> None:
        """初始化 Agent"""
        self._tool_context = tool_context

        # ========== 改进: 使用create_trading_agent以获得tools支持 ==========
        from vibe_trading.agents.agent_factory import create_trading_agent

        self._agent = await create_trading_agent(
            config=self.config,
            tool_context=tool_context,
            enable_streaming=False,
        )

        logger.info(f"Research Manager Agent initialized for {tool_context.symbol}")

    async def make_decision(
        self,
        context: str,
        bull_agent: ResearcherAgent,
        bear_agent: ResearcherAgent,
        bull_history: str,
        bear_history: str,
        analyst_reports: Dict[str, str],
        market_data: Optional[Dict] = None,
    ) -> Dict:
        """
        做出投资决策（增强版）

        Returns:
            {
                "recommendation": InvestmentRecommendation,
                "scorecard": DebateScorecard,
                "decision_text": str,
                "analysis_summary": dict
            }
        """
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # 1. 评估辩论
        bull_messages = bull_history.split("\n") if bull_history else []
        bear_messages = bear_history.split("\n") if bear_history else []

        scorecard = self._debate_evaluator.evaluate_debate(
            bull_messages,
            bear_messages,
            market_data
        )

        # 2. 生成投资建议
        recommendation = self._recommendation_engine.generate_recommendation(
            scorecard,
            analyst_reports,
            market_data
        )

        # 3. 构建LLM提示获取详细决策
        prompt = self._build_decision_prompt(
            context,
            scorecard,
            recommendation,
            analyst_reports,
            bull_agent,
            bear_agent
        )

        await self._agent.prompt(prompt)

        # 获取决策文本
        decision_text = ""
        messages = self._agent.state.messages
        if messages:
            last_assistant = [m for m in messages if getattr(m, "role", None) == "assistant"]
            if last_assistant:
                content = last_assistant[-1].content
                if isinstance(content, list):
                    decision_text = "".join(getattr(c, "text", str(c)) for c in content)
                else:
                    decision_text = str(content)

        # 4. 生成分析摘要
        analysis_summary = self._generate_analysis_summary(scorecard, recommendation)

        return {
            "recommendation": recommendation,
            "scorecard": scorecard,
            "decision_text": decision_text,
            "analysis_summary": analysis_summary,
        }

    def _build_decision_prompt(
        self,
        context: str,
        scorecard: DebateScorecard,
        recommendation: InvestmentRecommendation,
        analyst_reports: Dict[str, str],
        bull_agent: ResearcherAgent,
        bear_agent: ResearcherAgent
    ) -> str:
        """构建决策提示"""
        prompt = f"""As the Research Manager, please review the debate analysis and provide your final decision for {self._tool_context.symbol}.

=== 市场环境 ===
{context}

=== 辩论评分分析 ===
看涨得分: {scorecard.bull_score:.1f}/100
看跌得分: {scorecard.bear_score:.1f}/100
主导观点: {scorecard.dominant_view}
共识度: {scorecard.consensus_level:.2%}

=== 维度得分 ===
"""
        # 添加维度得分
        for dim, scores in scorecard.dimension_scores.items():
            prompt += f"{dim.upper()}: 看涨 {scores['bull']:.1f}% vs 看跌 {scores['bear']:.1f}%\n"

        prompt += f"""
=== 量化投资建议 ===
行动: {recommendation.action}
置信度: {recommendation.confidence:.1%}
总分: {recommendation.overall_score:.1f} (-100=强烈看跌, +100=强烈看涨)
技术面得分: {recommendation.technical_score:.1f}
基本面得分: {recommendation.fundamental_score:.1f}
情绪面得分: {recommendation.sentiment_score:.1f}

关键因素:
"""
        for factor in recommendation.key_factors[:5]:
            prompt += f"- {factor}\n"

        if recommendation.risk_factors:
            prompt += "\n风险因素:\n"
            for risk in recommendation.risk_factors[:5]:
                prompt += f"- {risk}\n"

        prompt += f"""
=== 分析师团队观点 ===
"""
        for role, report in analyst_reports.items():
            prompt += f"\n{role.upper()}:\n{report[:200]}...\n"

        prompt += """
请基于以上分析，提供你的最终裁决，包括:
1. 你的最终投资建议 (BUY/SELL/HOLD)
2. 建议的置信度
3. 具体的投资计划 (入场价位、目标价位、止损价位、仓位建议)
4. 理由说明 (综合各方观点后的理由)
5. 风险提示
"""

        return prompt

    def _generate_analysis_summary(
        self,
        scorecard: DebateScorecard,
        recommendation: InvestmentRecommendation
    ) -> Dict:
        """生成分析摘要"""
        return {
            "dominant_view": scorecard.dominant_view,
            "view_strength": abs(scorecard.bull_score - scorecard.bear_score),
            "consensus_level": scorecard.consensus_level,
            "recommendation": recommendation.action,
            "confidence": recommendation.confidence,
            "overall_score": recommendation.overall_score,
            "key_dimensions": {
                "technical": recommendation.technical_score,
                "fundamental": recommendation.fundamental_score,
                "sentiment": recommendation.sentiment_score,
            },
            "total_arguments": len(scorecard.bull_arguments) + len(scorecard.bear_arguments),
            "strong_arguments": (
                scorecard.bull_strength_count.get("strong", 0) +
                scorecard.bull_strength_count.get("very_strong", 0) +
                scorecard.bear_strength_count.get("strong", 0) +
                scorecard.bear_strength_count.get("very_strong", 0)
            ),
        }


async def run_debate_round(
    bull: BullResearcherAgent,
    bear: BearResearcherAgent,
    context: str,
    bull_history: str,
    bear_history: str,
) -> tuple:
    """执行一轮辩论"""
    from pi_logger import step, info, logger

    step("Bull 发言...", tag="Debate")
    # Bull 回应
    bull_response = await bull.respond(
        context=context,
        debate_history=f"Bull: {bull_history}\nBear: {bear_history}",
        opponent_argument=bear_history.split("\n")[-1] if bear_history else None,
    )
    info("Bull 回应完成", tag="Bull")
    
    # 记录Bull发言内容到日志
    logger.info(f"Bull: {bull_response}", tag="Bull")

    step("Bear 发言...", tag="Debate")
    # Bear 回应
    bear_response = await bear.respond(
        context=context,
        debate_history=f"Bull: {bull_history}\nBear: {bear_history}",
        opponent_argument=bull_response.split("\n")[-1] if bull_response else None,
    )
    info("Bear 回应完成", tag="Bear")
    
    # 记录Bear发言内容到日志
    logger.info(f"Bear: {bear_response}", tag="Bear")

    return bull_response, bear_response


async def run_research_phase(
    bull: BullResearcherAgent,
    bear: BearResearcherAgent,
    research_manager: ResearchManagerAgent,
    context: str,
    analyst_reports: Dict[str, str],
    rounds: int = 2,
) -> Dict:
    """
    执行完整的研究阶段

    Args:
        bull: 看涨研究员
        bear: 看跌研究员
        research_manager: 研究经理
        context: 市场环境
        analyst_reports: 分析师报告
        rounds: 辩论轮数

    Returns:
        {
            "recommendation": 投资建议,
            "scorecard": 辩论评分卡,
            "decision_text": 决策文本,
            "analysis_summary": 分析摘要
        }
    """
    bull_history = ""
    bear_history = ""

    # 执行多轮辩论
    for round_num in range(rounds):
        logger.info(f"Research debate round {round_num + 1}")

        bull_response, bear_response = await run_debate_round(
            bull=bull,
            bear=bear,
            context=context,
            bull_history=bull_history,
            bear_history=bear_history,
        )

        # 更新历史
        if bull_history:
            bull_history += f"\n\nRound {round_num + 1}:\n{bull_response}"
        else:
            bull_history = f"Round {round_num + 1}:\n{bull_response}"

        if bear_history:
            bear_history += f"\n\nRound {round_num + 1}:\n{bear_response}"
        else:
            bear_history = f"Round {round_num + 1}:\n{bear_response}"

    # 研究经理做出最终决策
    result = await research_manager.make_decision(
        context=context,
        bull_agent=bull,
        bear_agent=bear,
        bull_history=bull_history,
        bear_history=bear_history,
        analyst_reports=analyst_reports,
    )

    return result
