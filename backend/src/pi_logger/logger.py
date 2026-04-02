"""
简单日志系统

提供带颜色的日志输出，支持不同级别和标签。
支持同时输出到终端和文件。
所有 logger 共享同一个日志文件。
"""

import os
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from contextlib import contextmanager

from .colors import LEVEL_COLORS, colorize, style, strip_ansi
from .formatter import LogFormatter, CompactFormatter, JsonFormatter


# =============================================================================
# 全局日志文件
# =============================================================================

_global_log_file: Optional[str] = None
_global_file_handle: Optional[Any] = None


def _init_global_log_file(path: str) -> None:
    """初始化全局日志文件"""
    global _global_log_file, _global_file_handle

    # 关闭之前的文件
    if _global_file_handle:
        _global_file_handle.close()

    _global_log_file = path

    try:
        # 确保目录存在
        log_dir = os.path.dirname(path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # 打开文件（追加模式）
        _global_file_handle = open(path, "a", encoding="utf-8")

        # 写入会话分隔
        _global_file_handle.write(f"\n{'='*60}\n")
        _global_file_handle.write(f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        _global_file_handle.write(f"{'='*60}\n\n")
        _global_file_handle.flush()
    except Exception as e:
        print(f"Warning: Failed to open log file: {e}")
        _global_file_handle = None


def _write_to_global_file(text: str) -> None:
    """写入全局日志文件"""
    global _global_file_handle
    if _global_file_handle:
        try:
            plain_text = strip_ansi(text)
            _global_file_handle.write(plain_text + "\n")
            _global_file_handle.flush()
        except Exception:
            pass


def set_global_log_file(path: str) -> None:
    """设置全局日志文件路径，所有 logger 都会写入此文件"""
    _init_global_log_file(path)


def close_global_log_file() -> None:
    """关闭全局日志文件"""
    global _global_file_handle
    if _global_file_handle:
        _global_file_handle.close()
        _global_file_handle = None


class Logger:
    """简单日志器"""

    def __init__(
        self,
        name: str = "",
        formatter: Optional[LogFormatter] = None,
        min_level: str = "DEBUG",
        enabled: bool = True,
        context: Optional[Dict[str, str]] = None,
    ):
        self.name = name
        self.formatter = formatter or CompactFormatter()
        self.min_level = min_level
        self.enabled = enabled
        self._tag_colors: Dict[str, str] = {}
        # 追踪上下文，用于存储 request_id, session_id, task_id 等
        self.context: Dict[str, str] = context.copy() if context else {}

        # 日志级别优先级
        self._level_priority = {
            "DEBUG": 0,
            "INFO": 1,
            "SUCCESS": 2,
            "WARNING": 3,
            "ERROR": 4,
        }

    def set_tag_color(self, tag: str, color: str) -> None:
        """设置标签颜色"""
        self._tag_colors[tag] = color
        if hasattr(self.formatter, 'tag_colors'):
            self.formatter.tag_colors.update(self._tag_colors)

        # 日志级别优先级
        self._level_priority = {
            "DEBUG": 0,
            "INFO": 1,
            "SUCCESS": 2,
            "WARNING": 3,
            "ERROR": 4,
        }

    def set_tag_color(self, tag: str, color: str) -> None:
        """设置标签颜色"""
        self._tag_colors[tag] = color
        if hasattr(self.formatter, 'tag_colors'):
            self.formatter.tag_colors.update(self._tag_colors)

    def _should_log(self, level: str) -> bool:
        """检查是否应该输出该级别的日志"""
        if not self.enabled:
            return False
        min_priority = self._level_priority.get(self.min_level, 0)
        level_priority = self._level_priority.get(level, 0)
        return level_priority >= min_priority

    def _format_context_prefix(self) -> str:
        """格式化追踪上下文前缀"""
        if not self.context:
            return ""
        
        # 追踪标识的简短别名映射
        alias_map = {
            "session_id": "sid",
            "task_id": "tid",
            "request_id": "rid",
        }
        
        parts = []
        for key, value in self.context.items():
            if value:  # 只输出非空值
                alias = alias_map.get(key, key)
                parts.append(f"[{alias}:{value}]")
        
        return "".join(parts)

    def _log(self, level: str, message: str, tag: Optional[str] = None, **kwargs) -> None:
        """内部日志方法"""
        if not self._should_log(level):
            return

        # 使用 logger 的名字作为默认 tag
        log_tag = tag or self.name
        
        # 附加追踪上下文前缀到消息
        context_prefix = self._format_context_prefix()
        if context_prefix:
            message = f"{context_prefix} {message}"
        
        output = self.formatter.format(level, message, tag=log_tag, **kwargs)

        # 输出到终端
        print(output)

        # 输出到全局文件
        _write_to_global_file(output)

    # ==========================================================================
    # 日志级别方法
    # ==========================================================================

    def debug(self, message: str, tag: Optional[str] = None, **kwargs) -> None:
        """调试级别日志"""
        self._log("DEBUG", message, tag, **kwargs)

    def info(self, message: str, tag: Optional[str] = None, **kwargs) -> None:
        """信息级别日志"""
        self._log("INFO", message, tag, **kwargs)

    def success(self, message: str, tag: Optional[str] = None, **kwargs) -> None:
        """成功级别日志"""
        self._log("SUCCESS", message, tag, **kwargs)

    def warning(self, message: str, tag: Optional[str] = None, **kwargs) -> None:
        """警告级别日志"""
        self._log("WARNING", message, tag, **kwargs)

    def error(self, message: str, tag: Optional[str] = None, **kwargs) -> None:
        """错误级别日志"""
        self._log("ERROR", message, tag, **kwargs)

    # 别名
    warn = warning
    ok = success

    # ==========================================================================
    # 便捷方法
    # ==========================================================================

    def step(self, message: str, tag: Optional[str] = None, **kwargs) -> None:
        """步骤日志（info 级别）"""
        self.info(f"▶ {message}", tag, **kwargs)

    def done(self, message: str, tag: Optional[str] = None, **kwargs) -> None:
        """完成日志（success 级别）"""
        self.success(f"✓ {message}", tag, **kwargs)

    def fail(self, message: str, tag: Optional[str] = None, **kwargs) -> None:
        """失败日志（error 级别）"""
        self.error(f"✗ {message}", tag, **kwargs)

    def file(self, message: str, tag: Optional[str] = None, **kwargs) -> None:
        """文件操作日志（info 级别）"""
        self.info(f"📄 {message}", tag, **kwargs)

    def detail(self, message: str, tag: Optional[str] = None, max_terminal: int = 200) -> None:
        """
        详细信息日志

        终端显示摘要（截断），日志文件记录完整内容。

        Args:
            message: 完整消息内容
            tag: 标签
            max_terminal: 终端最大显示字符数
        """
        if not self._should_log("INFO"):
            return

        log_tag = tag or self.name
        
        # 附加追踪上下文前缀
        context_prefix = self._format_context_prefix()

        # 终端显示摘要
        if len(message) > max_terminal:
            terminal_msg = message[:max_terminal] + "..."
        else:
            terminal_msg = message
        
        # 添加上下文前缀
        if context_prefix:
            terminal_msg = f"{context_prefix} {terminal_msg}"
            message = f"{context_prefix} {message}"
        
        output = self.formatter.format("INFO", terminal_msg, tag=log_tag)
        print(output)

        # 日志文件记录完整内容
        _write_to_global_file(self.formatter.format("INFO", message, tag=log_tag))

    # ==========================================================================
    # 分隔线
    # ==========================================================================

    def separator(self, char: str = "─", length: int = 60) -> None:
        """打印分隔线"""
        if not self.enabled:
            return
        line = char * length
        print(line)
        _write_to_global_file(line)

    def header(self, title: str, width: int = 50) -> None:
        """打印标题头"""
        if not self.enabled:
            return
        from .colors import AnsiColor
        border = "═" * width
        print()
        print(colorize(border, AnsiColor.BRIGHT_CYAN))
        print(style(f"  {title}  ", AnsiColor.BOLD, AnsiColor.BRIGHT_CYAN))
        print(colorize(border, AnsiColor.BRIGHT_CYAN))
        print()
        _write_to_global_file(f"\n{border}\n  {title}  \n{border}\n")

    # ==========================================================================
    # 上下文管理器
    # ==========================================================================

    @contextmanager
    def indent(self):
        """缩进输出（暂时不实现，因为终端缩进比较复杂）"""
        yield

    @contextmanager
    def progress(self, message: str, tag: Optional[str] = None):
        """进度上下文，自动输出开始和结束"""
        self.step(message, tag)
        try:
            yield
        except Exception as e:
            self.fail(f"{message} 失败: {e}", tag)
            raise
        else:
            self.done(message, tag)

    # ==========================================================================
    # 配置方法
    # ==========================================================================

    def set_level(self, level: str) -> None:
        """设置最低日志级别"""
        self.min_level = level

    def enable(self) -> None:
        """启用日志"""
        self.enabled = True

    def disable(self) -> None:
        """禁用日志"""
        self.enabled = False

    def use_compact_format(self) -> None:
        """使用紧凑格式"""
        self.formatter = CompactFormatter(
            tag_colors=getattr(self.formatter, 'tag_colors', None)
        )

    def use_full_format(self) -> None:
        """使用完整格式"""
        self.formatter = LogFormatter(
            tag_colors=getattr(self.formatter, 'tag_colors', None)
        )

    def use_json_format(self) -> None:
        """使用 JSON 格式"""
        self.formatter = JsonFormatter(
            tag_colors=getattr(self.formatter, 'tag_colors', None)
        )

    def with_context(self, **kwargs) -> 'Logger':
        """
        返回带有额外上下文的新 Logger 实例（浅拷贝，共享 formatter）
        
        Args:
            **kwargs: 追踪上下文键值对，如 session_id="abc", task_id="task_1"
            
        Returns:
            新的 Logger 实例，包含合并后的上下文
            
        Example:
            logger = get_logger("Agent")
            task_logger = logger.with_context(session_id="abc", task_id="task_1")
            task_logger.info("开始执行")  # 输出: [sid:abc][tid:task_1] Agent: 开始执行
        """
        # 合并现有上下文和新上下文
        new_context = {**self.context, **kwargs}
        
        # 创建新的 Logger 实例，共享 formatter
        new_logger = Logger(
            name=self.name,
            formatter=self.formatter,  # 共享 formatter
            min_level=self.min_level,
            enabled=self.enabled,
            context=new_context,
        )
        # 复制 tag_colors
        new_logger._tag_colors = self._tag_colors.copy()
        
        return new_logger

    def set_context(self, **kwargs) -> None:
        """
        更新当前 Logger 的上下文（原地修改）
        
        Args:
            **kwargs: 追踪上下文键值对
        """
        self.context.update(kwargs)

    def clear_context(self) -> None:
        """清除当前 Logger 的所有上下文"""
        self.context.clear()


# =============================================================================
# 全局默认日志器
# =============================================================================

_default_logger: Optional[Logger] = None


def get_logger(name: str = "", log_file: Optional[str] = None, **kwargs) -> Logger:
    """
    获取或创建日志器

    Args:
        name: 日志器名称，空字符串返回全局默认日志器
        log_file: 日志文件路径，所有日志器共享同一个文件
        **kwargs: 其他 Logger 参数

    Returns:
        Logger 实例
    """
    global _default_logger

    # 设置全局日志文件
    if log_file:
        set_global_log_file(log_file)

    if name == "":
        if _default_logger is None:
            _default_logger = Logger(**kwargs)
        return _default_logger
    return Logger(name=name, **kwargs)


def configure(log_file: Optional[str] = None, **kwargs) -> None:
    """
    配置全局日志器

    Args:
        log_file: 日志文件路径
        **kwargs: 其他 Logger 参数
    """
    global _default_logger

    # 设置全局日志文件
    if log_file:
        set_global_log_file(log_file)

    if _default_logger is None:
        _default_logger = Logger()
    for key, value in kwargs.items():
        if hasattr(_default_logger, key):
            setattr(_default_logger, key, value)


# =============================================================================
# 便捷函数
# =============================================================================

def debug(message: str, tag: Optional[str] = None, **kwargs) -> None:
    """调试日志"""
    get_logger().debug(message, tag, **kwargs)


def info(message: str, tag: Optional[str] = None, **kwargs) -> None:
    """信息日志"""
    get_logger().info(message, tag, **kwargs)


def success(message: str, tag: Optional[str] = None, **kwargs) -> None:
    """成功日志"""
    get_logger().success(message, tag, **kwargs)


def warning(message: str, tag: Optional[str] = None, **kwargs) -> None:
    """警告日志"""
    get_logger().warning(message, tag, **kwargs)


def error(message: str, tag: Optional[str] = None, **kwargs) -> None:
    """错误日志"""
    get_logger().error(message, tag, **kwargs)


def step(message: str, tag: Optional[str] = None, **kwargs) -> None:
    """步骤日志"""
    get_logger().step(message, tag, **kwargs)


def done(message: str, tag: Optional[str] = None, **kwargs) -> None:
    """完成日志"""
    get_logger().done(message, tag, **kwargs)


def fail(message: str, tag: Optional[str] = None, **kwargs) -> None:
    """失败日志"""
    get_logger().fail(message, tag, **kwargs)


def separator(char: str = "─", length: int = 60) -> None:
    """分隔线"""
    get_logger().separator(char, length)


def header(title: str, width: int = 50) -> None:
    """标题头"""
    get_logger().header(title, width)
