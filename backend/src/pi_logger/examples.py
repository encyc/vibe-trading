#!/usr/bin/env python3
"""
Pi Logger 使用示例
"""

from pi_logger import (
    get_logger,
    info,
    success,
    error,
    warning,
    step,
    done,
    fail,
)


def example_basic():
    """基本用法示例"""
    print("=== 基本用法 ===\n")

    # 使用全局便捷函数
    info("系统启动中...")
    success("连接成功", tag="Database")
    warning("配置文件未找到，使用默认配置")
    error("连接超时", retry=3)

    print()


def example_logger():
    """使用 Logger 对象"""
    print("=== Logger 对象 ===\n")

    # 创建带名字的日志器
    logger = get_logger("Writer")
    logger.info("Writer Agent 初始化")
    logger.step("开始生成内容")
    logger.done("内容生成完成")
    logger.file("保存到文件: chapter1.txt")

    print()


def example_tags():
    """使用标签区分不同模块"""
    print("=== 标签系统 ===\n")

    # 不同 Agent 使用不同标签
    step("开始分析角色设定", tag="Character")
    done("角色分析完成", tag="Character")

    step("开始构建世界观", tag="WorldBuilder")
    done("世界观构建完成", tag="WorldBuilder")

    step("开始生成章节大纲", tag="Chapter")
    done("大纲生成完成", tag="Chapter")

    print()


def example_progress():
    """进度上下文"""
    print("=== 进度跟踪 ===\n")

    logger = get_logger("Agency")

    # 使用 progress 上下文自动处理开始/结束
    with logger.progress("初始化 AI 模型"):
        # 模拟工作
        pass

    with logger.progress("加载配置文件"):
        # 模拟工作
        pass

    # 如果发生异常
    try:
        with logger.progress("处理用户请求"):
            raise ValueError("模拟错误")
    except ValueError:
        pass

    print()


def example_header():
    """标题和分隔线"""
    print("=== 标题和分隔线 ===\n")

    logger = get_logger()

    logger.header("灵器AI")
    info("系统版本: 1.0.0")
    info("Python 版本: 3.11")
    logger.separator()
    logger.header("开始创作")

    print()


def example_custom_colors():
    """自定义颜色"""
    print("=== 自定义颜色 ===\n")

    from pi_logger import AnsiColor, colorize, style

    # 直接使用颜色函数
    print(colorize("这是红色文本", AnsiColor.BRIGHT_RED))
    print(style("这是粗体文本", AnsiColor.BOLD))
    print(style("这是粗体斜体", AnsiColor.BOLD, AnsiColor.ITALIC))

    print()


def example_configuration():
    """配置日志器"""
    print("=== 日志配置 ===\n")

    from pi_logger import configure, get_logger

    # 配置全局日志器
    configure(
        min_level="SUCCESS",  # 只输出 SUCCESS 及以上级别
    )

    info("这条不会显示（DEBUG 级别被过滤）")
    success("这条会显示")
    error("这条也会显示")

    print()


if __name__ == "__main__":
    example_basic()
    example_logger()
    example_tags()
    example_progress()
    example_header()
    example_custom_colors()
    example_configuration()
