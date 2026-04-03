"""
结构化日志配置

使用structlog实现结构化日志，便于分析和监控。
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import structlog
from structlog.types import EventDict, Processor


def configure_logging(
    log_level: str = "INFO",
    log_file: str = "./vibe_trading.log",
    json_output: bool = True,
    enable_file_logging: bool = True,
):
    """
    配置结构化日志

    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径
        json_output: 是否输出JSON格式
        enable_file_logging: 是否启用文件日志
    """
    # 创建日志目录
    if enable_file_logging:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # 配置structlog处理器
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # 添加上下文信息
    def add_context(_: logging.Logger, __: str, event_dict: EventDict) -> EventDict:
        """添加应用上下文"""
        event_dict["app"] = "vibe_trading"
        event_dict["environment"] = "production"  # 可配置
        return event_dict

    processors.append(add_context)

    # 输出格式
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        # 控制台友好格式
        processors.append(ConsoleRenderer())

    # 配置structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 配置标准库logging（用于兼容）
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level),
    )

    # 文件日志处理器
    if enable_file_logging:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, log_level))

        if json_output:
            file_formatter = logging.Formatter("%(message)s")
        else:
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        file_handler.setFormatter(file_formatter)

        # 获取root logger并添加处理器
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)


class ConsoleRenderer(Processor):
    """控制台友好的日志渲染器"""

    def __call__(self, logger: logging.Logger, name: str, event_dict: EventDict) -> Any:
        # 提取关键信息
        timestamp = event_dict.pop("timestamp", datetime.now())
        level = event_dict.pop("level", "INFO").upper()
        event = event_dict.pop("event", "")
        logger_name = event_dict.pop("logger_name", name)

        # 构建日志前缀
        prefix = f"{timestamp} | {level:5} | {logger_name}"

        # 添加额外上下文
        context_parts = []
        for key, value in event_dict.items():
            if key not in ["app", "environment"]:
                context_parts.append(f"{key}={value}")

        # 组合输出
        output = f"{prefix} | {event}"

        if context_parts:
            output += f" | {' '.join(context_parts)}"

        return output + "\n"


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    获取结构化日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        配置好的日志记录器
    """
    return structlog.get_logger(name)


# 预定义的日志记录器
def get_trading_logger() -> structlog.stdlib.BoundLogger:
    """获取交易日志记录器"""
    return get_logger("trading")


def get_agent_logger(agent_name: str) -> structlog.stdlib.BoundLogger:
    """
    获取Agent日志记录器

    Args:
        agent_name: Agent名称

    Returns:
        配置好的Agent日志记录器
    """
    return get_logger(f"agent.{agent_name}")


def get_system_logger() -> structlog.stdlib.BoundLogger:
    """获取系统日志记录器"""
    return get_logger("system")


# 日志使用示例
def log_decision_made(
    decision_id: str,
    symbol: str,
    action: str,
    confidence: float,
    position_size: float,
):
    """记录决策"""
    logger = get_trading_logger()
    logger.info(
        "decision_made",
        decision_id=decision_id,
        symbol=symbol,
        action=action,
        confidence=confidence,
        position_size_usdt=position_size,
    )


def log_agent_started(agent_name: str, phase: str, symbol: str):
    """记录Agent启动"""
    logger = get_agent_logger(agent_name)
    logger.info(
        "agent_started",
        agent_name=agent_name,
        phase=phase,
        symbol=symbol,
    )


def log_agent_completed(
    agent_name: str,
    phase: str,
    duration_seconds: float,
    success: bool,
):
    """记录Agent完成"""
    logger = get_agent_logger(agent_name)
    logger.info(
        "agent_completed",
        agent_name=agent_name,
        phase=phase,
        duration_seconds=duration_seconds,
        success=success,
    )


def log_error(
    error_type: str,
    error_message: str,
    context: Dict[str, Any],
):
    """记录错误"""
    logger = get_system_logger()
    logger.error(
        "error_occurred",
        error_type=error_type,
        error_message=error_message,
        **context,
    )


def log_trade_executed(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    order_id: str,
):
    """记录交易执行"""
    logger = get_trading_logger()
    logger.info(
        "trade_executed",
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        order_id=order_id,
    )


def log_risk_warning(
    warning_type: str,
    symbol: str,
    current_value: float,
    threshold: float,
):
    """记录风险警告"""
    logger = get_system_logger()
    logger.warning(
        "risk_warning",
        warning_type=warning_type,
        symbol=symbol,
        current_value=current_value,
        threshold=threshold,
    )


# 性能日志
class PerformanceLogger:
    """性能日志记录器"""

    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.logger = get_system_logger()
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.now()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()

            self.logger.info(
                "operation_completed",
                operation=self.operation_name,
                duration_seconds=duration,
                success=exc_type is None,
                error=str(exc_type) if exc_type else None,
            )


# 使用示例
def example_usage():
    """使用示例"""

    # 基本日志
    logger = get_logger("example")
    logger.info("message", key1="value1", key2="value2")

    # 交易日志
    log_decision_made(
        decision_id="123",
        symbol="BTCUSDT",
        action="BUY",
        confidence=0.85,
        position_size=1000.0,
    )

    # Agent日志
    log_agent_started("TechnicalAnalyst", "Phase 1", "BTCUSDT")

    # 错误日志
    log_error(
        error_type="APIError",
        error_message="Failed to fetch data",
        context={"endpoint": "/api/v1/klines", "symbol": "BTCUSDT"},
    )

    # 性能日志
    with PerformanceLogger("phase_1_execution"):
        # 执行操作
        pass
