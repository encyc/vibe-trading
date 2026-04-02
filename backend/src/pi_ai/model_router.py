"""
模型路由器 - 根据调用意图（推理/生成）自动选择不同 LLM 模型。

设计思路：
- reasoning_model: 用于 Agent 推理、工具调用等场景（低成本模型如 glm_4_7）
- generation_model: 用于文档生成、正文写作等场景（高质量模型如 gemini3_flash）
- 路由判据: 当前 LLM 调用是否包含 tools 参数
  - 有 tools → reasoning_model（推理阶段）
  - 无 tools → generation_model（生成阶段）
"""

from dataclasses import dataclass
from typing import Optional
from pi_logger import get_logger

from .llm import Model

logger = get_logger("model_router")


@dataclass
class ModelRouter:
    """模型路由器 - 根据调用意图选择不同模型"""
    reasoning_model: Model          # 推理/工具调用模型（低成本）
    generation_model: Model         # 文档生成模型（高质量）
    reasoning_config_name: str      # 推理模型配置名（用于计费）
    generation_config_name: str     # 生成模型配置名（用于计费）

    def select_model(self, has_tools: bool) -> Model:
        """根据是否有工具调用选择模型
        
        Args:
            has_tools: 当前 LLM 调用是否包含 tools
            
        Returns:
            选中的 Model 实例
        """
        if has_tools:
            logger.debug(f"路由选择: reasoning_model ({self.reasoning_config_name})")
            return self.reasoning_model
        else:
            logger.debug(f"路由选择: generation_model ({self.generation_config_name})")
            return self.generation_model

    def get_model_config_name(self, has_tools: bool) -> str:
        """获取对应的模型配置名（用于计费）
        
        Args:
            has_tools: 当前 LLM 调用是否包含 tools
            
        Returns:
            模型配置名字符串
        """
        return self.reasoning_config_name if has_tools else self.generation_config_name


def create_model_router_from_config() -> Optional[ModelRouter]:
    """从 llm.yaml 配置创建模型路由器
    
    如果配置中没有 model_router 段，返回 None（向后兼容）。
    
    Returns:
        ModelRouter 实例，或 None
    """
    from .config import get_llm_config
    
    config = get_llm_config()
    router_config = config.get_model_router()
    
    if not router_config:
        logger.info("未配置模型路由，使用单一模型模式")
        return None
    
    reasoning_name = router_config.get("reasoning_model")
    generation_name = router_config.get("generation_model")
    
    if not reasoning_name or not generation_name:
        logger.warning("模型路由配置不完整，需要 reasoning_model 和 generation_model")
        return None
    
    try:
        reasoning_model = config.get_model(reasoning_name)
        generation_model = config.get_model(generation_name)
    except Exception as e:
        logger.error(f"创建模型路由器失败: {e}")
        return None
    
    logger.info(
        f"模型路由器已创建: reasoning={reasoning_name} ({reasoning_model.id}), "
        f"generation={generation_name} ({generation_model.id})"
    )
    
    return ModelRouter(
        reasoning_model=reasoning_model,
        generation_model=generation_model,
        reasoning_config_name=reasoning_name,
        generation_config_name=generation_name,
    )
