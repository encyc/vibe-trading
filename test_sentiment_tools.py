#!/usr/bin/env python3
"""
测试情绪分析工具

测试 CryptoCompare API 的新闻和社交媒体情绪获取功能。
"""
import asyncio
import sys
import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

# 添加 backend/src 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from vibe_trading.tools.sentiment_tools import (
    get_fear_and_greed_index,
    get_social_sentiment,
    get_news_sentiment,
)

console = Console()


async def test_fear_greed():
    """测试恐惧贪婪指数"""
    console.print(Panel("[bold cyan]测试 1: 恐惧贪婪指数[/bold cyan]"))

    result = await get_fear_and_greed_index()

    if "error" in result:
        console.print(f"[red]✗ 错误: {result['error']}[/red]")
        return

    console.print(f"[green]✓ 数值: {result['value']}[/green]")
    console.print(f"[cyan]✓ 分类: {result['classification']}[/cyan]")
    console.print(f"[dim]✓ 时间戳: {result.get('timestamp', 'N/A')}[/dim]")

    # 情绪解读
    value = result['value']
    if value <= 20:
        sentiment = "极度恐惧 (买入机会)"
        color = "green"
    elif value <= 40:
        sentiment = "恐惧"
        color = "blue"
    elif value <= 60:
        sentiment = "中性"
        color = "yellow"
    elif value <= 80:
        sentiment = "贪婪"
        color = "orange"
    else:
        sentiment = "极度贪婪 (卖出信号)"
        color = "red"

    console.print(f"\n[{color}]→ 解读: {sentiment}[/{color}]")
    console.print()


async def test_news_sentiment():
    """测试新闻情绪"""
    console.print(Panel("[bold cyan]测试 2: 加密货币新闻情绪[/bold cyan]"))

    symbol = "BTCUSDT"
    console.print(f"[dim]获取 {symbol} 相关新闻...[/dim]\n")

    result = await get_news_sentiment(symbol, limit=10)

    if "error" in result:
        console.print(f"[red]✗ 错误: {result['error']}[/red]")
        return

    source = result.get("source", "Unknown")
    console.print(f"[dim]数据源: {source}[/dim]")

    # 整体情绪
    overall = result["overall_sentiment"]
    color_map = {"positive": "green", "negative": "red", "neutral": "yellow"}
    console.print(f"[{color_map.get(overall, 'white')}]✓ 整体情绪: {overall.upper()}[/{color_map.get(overall, 'white')}]")

    # 情绪分布
    breakdown = result["sentiment_breakdown"]
    console.print(f"\n情绪分布:")
    console.print(f"  [green]正面: {breakdown['positive']}[/green]")
    console.print(f"  [yellow]中性: {breakdown['neutral']}[/yellow]")
    console.print(f"  [red]负面: {breakdown['negative']}[/red]")

    # 新闻列表
    news_list = result.get("news", [])
    console.print(f"\n[bold]最新 {len(news_list)} 条新闻:[/bold]")

    for i, news in enumerate(news_list[:5], 1):
        console.print(f"\n[dim]{i}.[/dim] {news['title']}")
        console.print(f"   [dim]来源: {news.get('source', 'N/A')}[/dim]")

    console.print()


async def test_social_sentiment():
    """测试社交媒体情绪"""
    console.print(Panel("[bold cyan]测试 3: 社交媒体情绪[/bold cyan]"))

    symbol = "BTCUSDT"
    console.print(f"[dim]获取 {symbol} 社交媒体情绪...[/dim]\n")

    result = await get_social_sentiment(symbol)

    if "error" in result:
        console.print(f"[red]✗ 错误: {result['error']}[/red]")
        if not result.get("available"):
            console.print("\n[dim]提示: CryptoCompare 社交数据需要付费订阅。[/dim]")
        console.print()
        return

    source = result.get("source", "Unknown")
    console.print(f"[dim]数据源: {source}[/dim]")

    # 情绪状态
    sentiment = result.get("sentiment", "unknown")
    score = result.get("sentiment_score", 0)

    color_map = {
        "very_bullish": "bold green",
        "bullish": "green",
        "neutral": "yellow",
        "bearish": "red",
        "very_bearish": "bold red",
    }
    console.print(f"[{color_map.get(sentiment, 'white')}]✓ 情绪: {sentiment.upper()} ({score:+.1f})[/{color_map.get(sentiment, 'white')}]")

    # 24h变化
    if "change_24h" in result:
        change = result["change_24h"]
        change_color = "green" if change > 0 else "red"
        console.print(f"[{change_color}]✓ 24h变化: {change:+.2f}%[/{change_color}]")

    # 提及统计
    mentions = result.get("mentions", {})
    if "total" in mentions:
        console.print(f"\n[bold]社交媒体提及:[/bold]")
        console.print(f"  总提及: {mentions['total']:,}")
        if "code_repo" in mentions:
            console.print(f"  代码仓库: {mentions['code_repo']:,}")
        if "followers" in mentions:
            console.print(f"  粉丝数: {mentions['followers']:,}")

    # 社交统计
    if "social_stats" in result:
        stats = result["social_stats"]
        console.print(f"\n[bold]社交统计:[/bold]")
        console.print(f"  Twitter粉丝: {stats.get('twitter_followers', 0):,}")
        console.print(f"  Reddit用户: {stats.get('reddit_users', 0):,}")
        console.print(f"  总粉丝数: {stats.get('total_followers', 0):,}")

    console.print()


async def main():
    """主测试函数"""
    console.print()
    console.print(Panel("[bold yellow]🧪 Vibe Trading 情绪分析工具测试[/bold yellow]", padding=(1, 1)))
    console.print()

    # 测试1: 恐惧贪婪指数
    await test_fear_greed()

    # 测试2: 新闻情绪
    await test_news_sentiment()

    # 测试3: 社交媒体情绪
    await test_social_sentiment()

    # 汇总
    console.print(Panel("[bold green]✅ 测试完成[/bold green]"))
    console.print()
    console.print("[dim]提示: 社交情绪数据需要 CryptoCompare 付费订阅。新闻数据免费可用。[/dim]")
    console.print()


if __name__ == "__main__":
    asyncio.run(main())
