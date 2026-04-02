"""
ANSI 颜色定义
"""

import re
from typing import Callable


class AnsiColor:
    """ANSI 颜色代码"""

    # 样式
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # 前景色
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # 亮色
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # 背景色
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"


def colorize(text: str, color: str) -> str:
    """给文本添加颜色"""
    return f"{color}{text}{AnsiColor.RESET}"


def style(text: str, *styles: str) -> str:
    """给文本添加样式"""
    prefix = "".join(styles)
    return f"{prefix}{text}{AnsiColor.RESET}"


def strip_ansi(text: str) -> str:
    """去除文本中的 ANSI 颜色码"""
    ansi_pattern = re.compile(r'\033\[[0-9;]*m')
    return ansi_pattern.sub('', text)


# 预设的颜色映射
LEVEL_COLORS = {
    "DEBUG": AnsiColor.DIM,
    "INFO": AnsiColor.CYAN,
    "SUCCESS": AnsiColor.BRIGHT_GREEN,
    "WARNING": AnsiColor.BRIGHT_YELLOW,
    "ERROR": AnsiColor.BRIGHT_RED,
}

# 常用标签的颜色映射
DEFAULT_TAG_COLORS = {
    # Agent 角色
    "Editor": AnsiColor.BRIGHT_CYAN,
    "WorldBuilder": AnsiColor.BRIGHT_GREEN,
    "Character": AnsiColor.BRIGHT_YELLOW,
    "Plot": AnsiColor.BRIGHT_MAGENTA,
    "Chapter": AnsiColor.BRIGHT_BLUE,
    "Writer": AnsiColor.BRIGHT_RED,

    # 系统模块
    "Agency": AnsiColor.BLUE,
    "Orchestrator": AnsiColor.MAGENTA,
    "File": AnsiColor.GREEN,
    "LLM": AnsiColor.YELLOW,
    "Tool": AnsiColor.CYAN,

    # 通用
    "System": AnsiColor.WHITE,
    "User": AnsiColor.BRIGHT_BLUE,
}
