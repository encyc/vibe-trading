"""
日志格式化器
"""

from datetime import datetime
from typing import Optional, Dict, Any

from .colors import LEVEL_COLORS, DEFAULT_TAG_COLORS, colorize, style


class LogFormatter:
    """日志格式化器"""

    def __init__(
        self,
        show_time: bool = True,
        show_level: bool = True,
        show_tag: bool = True,
        tag_colors: Optional[Dict[str, str]] = None,
        time_format: str = "%H:%M:%S",
    ):
        self.show_time = show_time
        self.show_level = show_level
        self.show_tag = show_tag
        self.tag_colors = {**DEFAULT_TAG_COLORS, **(tag_colors or {})}
        self.time_format = time_format

    def format(
        self,
        level: str,
        message: str,
        tag: Optional[str] = None,
        **kwargs
    ) -> str:
        """格式化日志消息"""
        parts = []

        # 时间戳
        if self.show_time:
            time_str = datetime.now().strftime(self.time_format)
            parts.append(style(time_str, "\033[30m"))  # 灰色时间

        # 日志级别
        if self.show_level:
            level_color = LEVEL_COLORS.get(level, "")
            level_str = f"[{level}]"
            if level_color:
                level_str = colorize(level_str, level_color)
            parts.append(level_str)

        # 标签
        if self.show_tag and tag:
            tag_color = self.tag_colors.get(tag, "")
            tag_str = f"[{tag}]"
            if tag_color:
                tag_str = colorize(tag_str, tag_color)
            else:
                tag_str = style(tag_str, "\033[1m")  # 粗体
            parts.append(tag_str)

        # 消息
        parts.append(message)

        # 额外数据
        if kwargs:
            extra_parts = []
            for key, value in kwargs.items():
                if value is not None and value != "":
                    extra_parts.append(f"{key}={value}")
            if extra_parts:
                parts.append(style(f"({', '.join(extra_parts)})", "\033[90m"))

        return " ".join(parts)


class CompactFormatter(LogFormatter):
    """紧凑格式化器 - 更简洁的输出"""

    def format(
        self,
        level: str,
        message: str,
        tag: Optional[str] = None,
        **kwargs
    ) -> str:
        """格式化日志消息（紧凑版）"""
        parts = []

        # 只显示时间（不含日期）
        if self.show_time:
            time_str = datetime.now().strftime(self.time_format)
            parts.append(style(time_str, "\033[90m"))

        # 级别符号
        level_symbols = {
            "DEBUG": "·",
            "INFO": "→",
            "SUCCESS": "✓",
            "WARNING": "⚠",
            "ERROR": "✗",
        }
        symbol = level_symbols.get(level, "•")
        level_color = LEVEL_COLORS.get(level, "")
        if level_color:
            symbol = colorize(symbol, level_color)
        parts.append(symbol)

        # 标签（简化）
        if tag:
            tag_color = self.tag_colors.get(tag, "")
            if tag_color:
                parts.append(colorize(tag, tag_color))
            else:
                parts.append(tag)

        # 消息
        parts.append(message)

        return " ".join(parts)


class JsonFormatter(LogFormatter):
    """JSON 格式化器 - 用于结构化日志"""

    def format(
        self,
        level: str,
        message: str,
        tag: Optional[str] = None,
        **kwargs
    ) -> str:
        """格式化日志消息（JSON）"""
        import json
        from .colors import LEVEL_COLORS, DEFAULT_TAG_COLORS

        data = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
        }

        if tag:
            data["tag"] = tag

        if kwargs:
            data.update({k: v for k, v in kwargs.items() if v is not None and v != ""})

        # 输出纯 JSON（不带颜色）
        json_str = json.dumps(data, ensure_ascii=False)

        # 可选：带颜色的 JSON 输出
        level_color = LEVEL_COLORS.get(level, "")
        if level_color:
            from .colors import colorize
            return colorize(json_str, level_color)

        return json_str
