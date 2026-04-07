"""
模型路由器 - 根据调用意图（推理/生成）自动选择不同 LLM 模型。

设计思路：
- deep_thinking_model: 深度思考模型，用于复杂推理、工具调用
- quick_thinking_model: 快速思考模型，用于数据获取和简单分析
- agent_model_mapping: Agent角色到模型的映射配置

路由判据:
  1. Agent角色映射（优先级最高）
  2. 是否有工具调用（工具调用使用deep_thinking_model）
  3. 默认使用quick_thinking_model（无工具时）
"""

from dataclasses import dataclass
from typing import Dict, Optional
from pi_logger import get_logger

from .llm import Model

logger = get_logger("model_router")


@dataclass
class ModelRouter:
    """模型路由器 - 根据调用意图选择不同模型"""
    # 双模型架构
    deep_thinking_model: Model       # 深度思考模型（复杂推理、工具调用）
    quick_thinking_model: Model       # 快速思考模型（数据获取、简单分析）
    deep_thinking_config_name: str   # 深度思考模型配置名
    quick_thinking_config_name: str   # 快速思考模型配置名

    # 别名（向后兼容API）
    reasoning_model: Model           # 别名，同deep_thinking_model
    generation_model: Model          # 别名，同quick_thinking_model
    reasoning_config_name: str       # 别名配置
    generation_config_name: str      # 别名配置

    # Agent角色映射
    agent_model_mapping: Dict[str, str] = None  # Agent角色 -> 模型类型

    def select_model(self, has_tools: bool = False, agent_role: Optional[str] = None) -> Model:
        """
        根据多个条件选择模型

        优先级:
        1. Agent角色映射（最高优先级）
        2. 是否有工具调用（工具调用使用deep_thinking_model）
        3. 默认使用深度思考模型

        Args:
            has_tools: 当前 LLM 调用是否包含 tools
            agent_role: Agent角色（可选）

        Returns:
            选中的 Model 实例
        """
        # 1. 检查Agent角色映射
        if agent_role and self.agent_model_mapping:
            model_type = self.agent_model_mapping.get(agent_role)
            if model_type == "deep_thinking_model":
                # logger.debug(f"路由选择: deep_thinking_model ({self.deep_thinking_config_name}) - Agent: {agent_role}")
                return self.deep_thinking_model
            elif model_type == "quick_thinking_model":
                # logger.debug(f"路由选择: quick_thinking_model ({self.quick_thinking_config_name}) - Agent: {agent_role}")
                return self.quick_thinking_model

        # 2. 工具调用使用深度思考模型
        if has_tools:
            logger.debug(f"路由选择: deep_thinking_model ({self.deep_thinking_config_name}) - has_tools")
            return self.deep_thinking_model
        else:
            logger.debug(f"路由选择: quick_thinking_model ({self.quick_thinking_config_name}) - no tools")
            return self.quick_thinking_model

    def get_model_config_name(self, has_tools: bool = False, agent_role: Optional[str] = None) -> str:
        """获取对应的模型配置名（用于计费）"""
        # 1. 检查Agent角色映射
        if agent_role and self.agent_model_mapping:
            model_type = self.agent_model_mapping.get(agent_role)
            if model_type == "deep_thinking_model":
                return self.deep_thinking_config_name
            elif model_type == "quick_thinking_model":
                return self.quick_thinking_config_name

        # 2. 工具调用使用深度思考模型
        return self.deep_thinking_config_name if has_tools else self.quick_thinking_config_name


def create_model_router_from_config() -> Optional[ModelRouter]:
    """从 llm.yaml 配置创建模型路由器

    使用双模型架构配置：
    - deep_thinking_model: 深度思考模型
    - quick_thinking_model: 快速思考模型
    - agent_model_mapping: Agent角色到模型的映射

    Returns:
        ModelRouter 实例，或 None
    """
    from .config import get_llm_config

    config = get_llm_config()
    router_config = config.get_model_router()

    if not router_config:
        logger.info("未配置模型路由，使用单一模型模式")
        return None

    # 读取双模型配置
    deep_name = router_config.get("deep_thinking_model")
    quick_name = router_config.get("quick_thinking_model")
    agent_mapping = router_config.get("agent_model_mapping", {})

    # 验证必需的配置
    if not deep_name or not quick_name:
        logger.warning("模型路由配置不完整，需要 deep_thinking_model 和 quick_thinking_model")
        return None

    try:
        # 创建模型实例
        deep_model = config.get_model(deep_name)
        quick_model = config.get_model(quick_name)

    except Exception as e:
        logger.error(f"创建模型路由器失败: {e}")
        return None

    # 转换Agent模型映射（从配置中的模型名映射到模型类型）
    processed_mapping = {}
    for agent_role, model_ref in agent_mapping.items():
        if model_ref == "deep_thinking_model":
            processed_mapping[agent_role] = "deep_thinking_model"
        elif model_ref == "quick_thinking_model":
            processed_mapping[agent_role] = "quick_thinking_model"
        else:
            # 直接使用模型名
            processed_mapping[agent_role] = model_ref

    return ModelRouter(
        deep_thinking_model=deep_model,
        quick_thinking_model=quick_model,
        deep_thinking_config_name=deep_name,
        quick_thinking_config_name=quick_name,
        # reasoning_model和generation_model作为别名
        reasoning_model=deep_model,
        generation_model=quick_model,
        reasoning_config_name=deep_name,
        generation_config_name=quick_name,
        agent_model_mapping=processed_mapping if processed_mapping else None,
    )
