"""
Pi AI 异常类

定义所有 AI 相关的自定义异常。
"""


class PiAIError(Exception):
    """Pi AI 基础异常类"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | details: {self.details}"
        return self.message


# =============================================================================
# LLM 相关异常
# =============================================================================

class LLMError(PiAIError):
    """LLM 相关异常基类"""
    pass


class LLMConnectionError(LLMError):
    """LLM 连接错误"""
    
    def __init__(self, provider: str, message: str = None):
        super().__init__(
            message or f"无法连接到 LLM 提供商: {provider}",
            {"provider": provider}
        )
        self.provider = provider


class LLMRateLimitError(LLMError):
    """LLM 速率限制错误"""
    
    def __init__(self, provider: str, retry_after: int = None):
        super().__init__(
            f"LLM API 速率限制，请稍后重试",
            {"provider": provider, "retry_after": retry_after}
        )
        self.provider = provider
        self.retry_after = retry_after


class LLMResponseError(LLMError):
    """LLM 响应错误"""
    
    def __init__(self, message: str, response_id: str = None):
        super().__init__(
            message,
            {"response_id": response_id}
        )
        self.response_id = response_id


class LLMStreamError(LLMError):
    """LLM 流式响应错误"""
    
    def __init__(self, message: str = "流式响应未产生结果"):
        super().__init__(message)


class LLMTimeoutError(LLMError):
    """LLM 超时错误"""
    
    def __init__(self, timeout: float, operation: str = "请求"):
        super().__init__(
            f"LLM {operation}超时 ({timeout}s)",
            {"timeout": timeout, "operation": operation}
        )
        self.timeout = timeout
        self.operation = operation


class LLMAuthenticationError(LLMError):
    """LLM 认证错误"""
    
    def __init__(self, provider: str):
        super().__init__(
            f"LLM API 认证失败，请检查 API 密钥",
            {"provider": provider}
        )
        self.provider = provider


# =============================================================================
# Agent 相关异常
# =============================================================================

class AgentError(PiAIError):
    """Agent 相关异常基类"""
    pass


class AgentToolError(AgentError):
    """Agent 工具执行错误"""
    
    def __init__(self, tool_name: str, message: str, tool_call_id: str = None):
        super().__init__(
            f"工具 '{tool_name}' 执行失败: {message}",
            {"tool_name": tool_name, "tool_call_id": tool_call_id}
        )
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id


class AgentValidationError(AgentError):
    """Agent 参数验证错误"""
    
    def __init__(self, message: str, field: str = None):
        super().__init__(
            message,
            {"field": field}
        )
        self.field = field


class AgentCancelledError(AgentError):
    """Agent 执行被取消"""
    
    def __init__(self, reason: str = None):
        super().__init__(
            f"Agent 执行被取消: {reason}" if reason else "Agent 执行被取消"
        )
        self.reason = reason


# =============================================================================
# 重试相关
# =============================================================================

class RetryableError(PiAIError):
    """可重试的错误"""
    
    def __init__(self, message: str, original_error: Exception = None, attempts: int = 0):
        super().__init__(message)
        self.original_error = original_error
        self.attempts = attempts


class MaxRetriesExceededError(PiAIError):
    """超过最大重试次数"""
    
    def __init__(self, max_retries: int, last_error: Exception = None):
        super().__init__(
            f"超过最大重试次数 ({max_retries})",
            {"max_retries": max_retries, "last_error": str(last_error) if last_error else None}
        )
        self.max_retries = max_retries
        self.last_error = last_error
