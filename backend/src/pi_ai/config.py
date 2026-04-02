"""
LLM 配置管理

从 YAML 文件加载 LLM 配置，提供便捷的模型获取方法。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .llm import Model
from pi_logger import get_logger


class LLMConfig:
    """LLM 配置管理器"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化 LLM 配置管理器。

        Args:
            config_path: 配置文件路径，默认为 llm.yaml
        """
        self.logger = get_logger("LLMConfig")
        self._config: Dict[str, Any] = {}
        self._config_path = config_path

        if config_path:
            self.load(config_path)

    def load(self, config_path: str) -> None:
        """
        加载 YAML 配置文件。

        Args:
            config_path: 配置文件路径
        """
        self._config_path = config_path
        path = Path(config_path)

        if not path.exists():
            self.logger.warning(f"配置文件不存在: {config_path}")
            return

        with open(path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

        self.logger.info(f"加载配置: {config_path}")
        self.logger.debug(f"可用配置: {list(self._config.get('llms', {}).keys())}")

    def get_current_name(self) -> str:
        """获取当前使用的 LLM 配置名称"""
        return self._config.get("use_llm", "iflow")

    def set_current(self, name: str) -> None:
        """
        设置当前使用的 LLM 配置。

        Args:
            name: 配置名称
        """
        if name not in self._config.get("llms", {}):
            available = list(self._config.get("llms", {}).keys())
            raise ValueError(
                f"LLM 配置不存在: {name}\n"
                f"可用配置: {available}"
            )

        self._config["use_llm"] = name
        self.logger.info(f"切换到配置: {name}")

    def get_model(self, name: Optional[str] = None) -> Model:
        """
        根据配置获取 Model 实例。

        Args:
            name: 配置名称，为空则使用当前配置

        Returns:
            Model 实例
        """
        if name is None:
            name = self.get_current_name()

        llms = self._config.get("llms", {})
        if name not in llms:
            available = list(llms.keys())
            raise ValueError(
                f"LLM 配置不存在: {name}\n"
                f"可用配置: {available}"
            )

        config = llms[name]

        # 环境变量替换
        api_key = config.get("api_key", "")
        if api_key and api_key.endswith(":") and "$" in api_key:
            # 处理 ${VAR:default} 格式
            var_name = api_key.split("${")[1].split("}")[0].split(":")[0]
            api_key = os.environ.get(var_name, "")

        # 如果 API key 为空，尝试从环境变量获取
        if not api_key:
            provider = config.get("provider", "")
            if provider == "openai":
                api_key = os.environ.get("OPENAI_API_KEY", "")
            elif provider == "anthropic":
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            elif provider == "google":
                api_key = os.environ.get("GOOGLE_API_KEY", "")

        model = Model(
            provider=config.get("provider", "openai"),
            id=config.get("model", "gpt-4o"),
            api_key=api_key or None,
            base_url=config.get("base_url"),
        )

        self.logger.info(
            f"加载模型: {name} -> {model.id}",
            tag=config.get("provider", "")
        )

        return model

    def list_configs(self) -> Dict[str, str]:
        """
        列出所有可用配置。

        Returns:
            配置名称到描述的映射
        """
        llms = self._config.get("llms", {})
        return {
            name: cfg.get("description", name)
            for name, cfg in llms.items()
        }

    def get_config(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取原始配置。

        Args:
            name: 配置名称，为空则使用当前配置

        Returns:
            配置字典
        """
        if name is None:
            name = self.get_current_name()

        llms = self._config.get("llms", {})
        if name not in llms:
            raise ValueError(f"LLM 配置不存在: {name}")

        return llms[name]

    @property
    def is_loaded(self) -> bool:
        """检查配置是否已加载"""
        return bool(self._config)

    def get_model_router(self) -> Optional[Dict[str, str]]:
        """获取模型路由配置"""
        return self._config.get("model_router", None)


# =============================================================================
# 全局配置实例
# =============================================================================

_default_config: Optional[LLMConfig] = None


def get_llm_config(config_path: Optional[str] = None) -> LLMConfig:
    """
    获取 LLM 配置管理器实例。

    Args:
        config_path: 配置文件路径，首次调用时设置

    Returns:
        LLMConfig 实例
    """
    global _default_config

    if _default_config is None:
        if config_path is None:
            # 默认路径
            import inspect
            pi_ai_dir = Path(inspect.getfile(lambda: None)).parent
            config_path = str(pi_ai_dir / "llm.yaml")

        _default_config = LLMConfig(config_path)

    return _default_config


def get_model_from_config(name: Optional[str] = None) -> Model:
    """
    从配置获取 Model 实例的便捷函数。

    Args:
        name: 配置名称，为空则使用当前配置

    Returns:
        Model 实例
    """
    return get_llm_config().get_model(name)


def set_current_llm(name: str) -> None:
    """
    设置当前使用的 LLM 配置。

    Args:
        name: 配置名称
    """
    get_llm_config().set_current(name)


def list_llm_configs() -> Dict[str, str]:
    """
    列出所有可用的 LLM 配置。

    Returns:
        配置名称到描述的映射
    """
    return get_llm_config().list_configs()
