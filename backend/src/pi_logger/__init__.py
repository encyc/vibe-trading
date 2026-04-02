"""
Pi Logger - 简单的彩色日志系统

提供带颜色的日志输出，支持不同级别和标签。
支持链路追踪上下文（session_id, task_id, request_id 等）。

基本用法:
    from pi_logger import get_logger, info, success, error

    # 使用全局函数
    info("系统启动")
    success("操作完成", tag="Writer")
    error("发生错误", error_code=500)

    # 使用日志器
    logger = get_logger("MyModule")
    logger.info("模块初始化")
    logger.success("任务完成", tag="Agent")
    logger.step("开始处理")
    logger.done("处理完成")
    
    # 使用追踪上下文
    task_logger = logger.with_context(session_id="abc", task_id="task_1")
    task_logger.info("开始执行")  # 输出: [sid:abc][tid:task_1] MyModule: 开始执行
"""

from .logger import (
    Logger,
    get_logger,
    configure,
    set_global_log_file,
    close_global_log_file,
    # 全局便捷函数
    debug,
    info,
    success,
    warning,
    error,
    step,
    done,
    fail,
    separator,
    header,
)

from .colors import (
    AnsiColor,
    colorize,
    style,
    LEVEL_COLORS,
    DEFAULT_TAG_COLORS,
)

from .formatter import (
    LogFormatter,
    CompactFormatter,
    JsonFormatter,
)

__all__ = [
    # 主要接口
    "Logger",
    "get_logger",
    "configure",
    "set_global_log_file",
    "close_global_log_file",
    # 便捷函数
    "debug",
    "info",
    "success",
    "warning",
    "error",
    "step",
    "done",
    "fail",
    "separator",
    "header",
    # 颜色
    "AnsiColor",
    "colorize",
    "style",
    "LEVEL_COLORS",
    "DEFAULT_TAG_COLORS",
    # 格式化器
    "LogFormatter",
    "CompactFormatter",
    "JsonFormatter",
]
