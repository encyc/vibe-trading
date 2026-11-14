"""
LLM 配置管理（应用层）

从 ``vibe_trading/config/llm.yaml`` 加载模型配置，构造 zenagent 的
:class:`zenagent.providers.catalog.Model`。

设计说明
--------
``llm.yaml`` 只是"选哪个模型"的清单；模型的技术参数（base_url、compat、
context_window、max_tokens、定价）从 zenagent 的 catalog 继承：

    catalog 命中   -> 用 catalog 的 Model，yaml 显式字段覆盖
    catalog 未命中 -> 用 yaml 的 base_url 造 Model，兼容标志由 sniff_compat
                      按 host 推断，yaml 显式字段再覆盖

凭证不进 Model：zenagent 的 ``Agent`` 接收 ``api_key`` 字符串，由
:func:`get_api_key_from_config` 从 ``~/.zenagent/settings.json`` 的
``api_keys``（优先）或环境变量（回退）解析，键名取自 catalog 的
``api_key_env``。

安全提示：``llm.yaml`` 历史上含明文 API key（longcat / iflow / glm_4_7 /
aliyun_* / opencode-zen），这些已进入 git 历史。迁移后本文件不再保存凭证，
轮换需要另行处理。
"""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml

from zenagent.providers.catalog import Model, ProviderConfig, load_catalog
from zenagent.providers.compat import CompatFlags, sniff_compat
from zenagent.types import Cost

try:
    from pi_logger import get_logger

    logger = get_logger("LLMConfig")
except Exception:  # pragma: no cover - logger 可选
    import logging

    logger = logging.getLogger("LLMConfig")


# zenagent catalog 只在进程内解析一次（含手写 YAML 子集解析器）
_CATALOG: Optional[Dict[str, ProviderConfig]] = None


def _catalog() -> Dict[str, ProviderConfig]:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = load_catalog()
    return _CATALOG


def _find_catalog_model(model_id: str) -> Optional[Model]:
    """按 model id 在 catalog 里找模型（首个匹配胜，与 zenagent 的 find_model 一致）。"""
    for provider in _catalog().values():
        for model in provider.models:
            if model.id == model_id:
                return model
    return None


def _default_config_path() -> str:
    """默认配置文件路径：本模块同目录下的 llm.yaml。"""
    return str(Path(__file__).parent / "llm.yaml")


#: yaml 里 provider 名 -> zenagent 协议适配器 key。
#: catalog 命中时用 catalog 的 api（那里是按供应商实测过的）；未命中时才看这里。
_PROVIDER_TO_API: Dict[str, str] = {
    "openai": "openai-completions",
    "anthropic": "anthropic-messages",
    "google": "google-generative-ai",
}


def _resolve_env_ref(raw: str) -> Optional[str]:
    """解析 ``${VAR}`` / ``${VAR:default}`` 形式的显式凭证引用（向后兼容）。"""
    if "${" not in raw:
        return raw or None
    inner = raw.split("${", 1)[1].split("}", 1)[0]
    var_name, _, default = inner.partition(":")
    return os.environ.get(var_name, default) or None


class LLMConfig:
    """LLM 配置管理器。"""

    def __init__(self, config_path: Optional[str] = None):
        self._config: Dict[str, Any] = {}
        self._config_path = config_path or _default_config_path()
        self.load(self._config_path)

    def load(self, config_path: str) -> None:
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"配置文件不存在: {config_path}")
            return
        with open(path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}
        logger.info(f"加载 LLM 配置: {config_path}")
        logger.debug(f"可用模型: {list(self._config.get('llms', {}).keys())}")

    def get_current_name(self) -> str:
        return self._config.get("use_llm", "glm_5_3_flash")

    def get_config(self, name: Optional[str] = None) -> Dict[str, Any]:
        name = name or self.get_current_name()
        llms = self._config.get("llms", {})
        if name not in llms:
            raise ValueError(
                f"LLM 配置不存在: {name}\n可用配置: {list(llms.keys())}"
            )
        return llms[name]

    def get_model(self, name: Optional[str] = None) -> Model:
        """根据配置名构造 zenagent :class:`Model`。

        优先级：yaml 显式字段 > catalog 命中值 > sniff_compat 推断。
        """
        name = name or self.get_current_name()
        cfg = self.get_config(name)

        model_id = cfg.get("model")
        if not model_id:
            raise ValueError(f"LLM 配置 {name} 缺少 model 字段")

        # 1. catalog 命中：直接复用（带上供应商的 compat / 上下文窗口 / 定价）
        base = _find_catalog_model(model_id)

        # 2. 未命中：用 yaml 的 base_url 造一个，compat 按 host 推断
        if base is None:
            base_url = cfg.get("base_url", "")
            if not base_url:
                raise ValueError(
                    f"LLM 配置 {name} 的 model={model_id!r} 不在 zenagent catalog 中，"
                    f"必须显式提供 base_url"
                )
            base = Model(
                id=model_id,
                provider=cfg.get("provider", "custom"),
                api=cfg.get(
                    "api",
                    _PROVIDER_TO_API.get(cfg.get("provider", ""), "openai-completions"),
                ),
                base_url=base_url,
                context_window=0,
                max_tokens=0,
                reasoning=False,
                cost=Cost(),
                compat=sniff_compat(base_url),
            )

        # 3. yaml 显式字段覆盖 catalog
        overrides: Dict[str, Any] = {}
        if cfg.get("base_url"):
            overrides["base_url"] = cfg["base_url"]
        if cfg.get("context_window") is not None:
            overrides["context_window"] = int(cfg["context_window"])
        if cfg.get("max_tokens") is not None:
            overrides["max_tokens"] = int(cfg["max_tokens"])
        if cfg.get("compat"):
            known = {k: v for k, v in cfg["compat"].items()
                     if k in CompatFlags.__dataclass_fields__}
            if known:
                overrides["compat"] = replace(base.compat, **known)
        return replace(base, **overrides) if overrides else base

    def get_api_key_env(self, name: Optional[str] = None) -> Optional[str]:
        """该配置对应的凭证环境变量名（catalog 的 api_key_env）。"""
        cfg = self.get_config(name)
        base = _find_catalog_model(cfg.get("model", ""))
        if base is not None:
            provider = _catalog().get(base.provider)
            if provider is not None:
                return provider.api_key_env
        return cfg.get("api_key_env")

    def get_api_key(self, name: Optional[str] = None) -> Optional[str]:
        """返回配置对应的 api_key。

        顺序：yaml 显式 ``api_key``（支持 ``${VAR}``）> zenagent settings 的
        ``api_keys`` > 环境变量。
        """
        cfg = self.get_config(name)
        explicit = cfg.get("api_key")
        if explicit:
            return _resolve_env_ref(str(explicit))

        env_name = self.get_api_key_env(name)
        if not env_name:
            return None
        try:
            from zenagent.settings import get_api_key

            # zenagent 的 settings 存储优先于环境变量
            return get_api_key(env_name)
        except Exception:  # pragma: no cover - zenagent 异常时的回退
            value = os.environ.get(env_name, "")
            return value.strip() or None

    def get_temperature(self, name: Optional[str] = None) -> Optional[float]:
        """该配置的采样温度（None = 用服务商默认）。"""
        value = self.get_config(name).get("temperature")
        return float(value) if value is not None else None

    def list_configs(self) -> Dict[str, str]:
        llms = self._config.get("llms", {})
        return {n: c.get("description", n) for n, c in llms.items()}

    @property
    def is_loaded(self) -> bool:
        return bool(self._config)


# =============================================================================
# 全局单例 + 便捷函数
# =============================================================================

_default_config: Optional[LLMConfig] = None


def get_llm_config(config_path: Optional[str] = None) -> LLMConfig:
    """获取全局 LLMConfig 单例。"""
    global _default_config
    if _default_config is None:
        _default_config = LLMConfig(config_path)
    return _default_config


def get_model_from_config(name: Optional[str] = None) -> Model:
    """从配置构造 zenagent Model。"""
    return get_llm_config().get_model(name)


def get_api_key_from_config(name: Optional[str] = None) -> Optional[str]:
    """从配置读取 api_key。"""
    return get_llm_config().get_api_key(name)


def make_get_api_key() -> Callable[[str], Optional[str]]:
    """构造一个按 provider 名取 api_key 的回调。

    回调签名 ``(provider: str) -> str | None``。当前实现忽略传入的 provider，
    统一返回默认配置的 key —— 与迁移前一致，因为 12 个 agent 都跑同一个模型。
    将来要按 provider 分派时改这里。
    """
    cfg = get_llm_config()
    current = cfg.get_current_name()

    def _get_api_key(provider: str) -> Optional[str]:
        return cfg.get_api_key(current)

    return _get_api_key
