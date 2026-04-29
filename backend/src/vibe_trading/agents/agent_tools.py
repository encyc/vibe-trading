"""
Pi Agent Core Tools 包装器

将现有的tools函数包装成pi_agent_core框架的AgentTool格式
"""
import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from pi_agent_core import AgentTool, AgentToolResult
from pi_agent_core.types import TextContent

from vibe_trading.tools import market_data_tools, technical_tools, fundamental_tools, sentiment_tools

logger = logging.getLogger(__name__)


# =============================================================================
# 参数模型定义
# =============================================================================

class GetCurrentPriceParams(BaseModel):
    """获取当前价格参数"""
    symbol: str = Field(description="交易对符号，如BTCUSDT")


class Get24hrTickerParams(BaseModel):
    """获取24小时ticker参数"""
    symbol: str = Field(description="交易对符号")


class GetFundingRateParams(BaseModel):
    """获取资金费率参数"""
    symbol: str = Field(description="交易对符号")


class GetLongShortRatioParams(BaseModel):
    """获取多空比参数"""
    symbol: str = Field(description="交易对符号")


class GetOpenInterestParams(BaseModel):
    """获取持仓量参数"""
    symbol: str = Field(description="交易对符号")


class GetFearAndGreedParams(BaseModel):
    """获取恐惧贪婪指数参数"""
    pass


class GetNewsSentimentParams(BaseModel):
    """获取新闻情绪参数"""
    symbol: str = Field(description="交易对符号")
    limit: int = Field(default=15, description="获取数量")


class GetOrderBookParams(BaseModel):
    """获取订单簿参数"""
    symbol: str = Field(description="交易对符号")
    limit: int = Field(default=20, description="深度级别")


class GetSocialSentimentParams(BaseModel):
    """获取社交媒体情绪参数"""
    symbol: str = Field(description="交易对符号")


class GetTakerBuySellRatioParams(BaseModel):
    """获取买卖比例参数"""
    symbol: str = Field(description="交易对符号")


class GetTopTraderLongShortRatioParams(BaseModel):
    """获取大户多空比参数"""
    symbol: str = Field(description="交易对符号")


class GetLiquidationOrdersParams(BaseModel):
    """获取清算订单参数"""
    symbol: Optional[str] = Field(default=None, description="交易对符号，不填则获取全部")


class GetTrendingSymbolsParams(BaseModel):
    """获取热门交易对参数"""
    pass


class GetComprehensiveSentimentParams(BaseModel):
    """获取综合情绪参数"""
    symbol: str = Field(description="交易对符号")


# =============================================================================
# 技术分析工具参数模型
# =============================================================================

class GetTechnicalIndicatorsParams(BaseModel):
    """获取技术指标参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")


class GetKlineDataParams(BaseModel):
    """获取K线数据参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")
    limit: int = Field(default=100, description="获取数量")


class GetComprehensiveTechnicalAnalysisParams(BaseModel):
    """获取综合技术分析参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")


class AnalyzeTrendParams(BaseModel):
    """分析趋势参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")


class DetectSupportResistanceParams(BaseModel):
    """检测支撑阻力参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")


class CalculatePivotsParams(BaseModel):
    """计算枢轴点参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")


class DetectCandlestickPatternsParams(BaseModel):
    """检测K线形态参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")


class DetectDivergenceParams(BaseModel):
    """检测背离参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")


class AnalyzeVolumePatternsParams(BaseModel):
    """分析成交量模式参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")


class SubmitTradeOrderParams(BaseModel):
    """提交交易订单参数"""
    symbol: str = Field(description="交易对符号，如 BTCUSDT")
    side: str = Field(description="订单方向：BUY 或 SELL")
    order_type: str = Field(default="MARKET", description="订单类型：MARKET、LIMIT、STOP_MARKET、TAKE_PROFIT_MARKET")
    quantity: float = Field(gt=0, description="下单数量，币本位数量，例如 BTC 数量")
    position_side: str = Field(default="BOTH", description="持仓方向：BOTH、LONG 或 SHORT")
    price: Optional[float] = Field(default=None, description="限价单价格；市价单不填")
    stop_price: Optional[float] = Field(default=None, description="止损/止盈触发价格")
    rationale: str = Field(default="", description="Portfolio Manager 对本次下单的最终理由")


# =============================================================================
# 执行函数
# =============================================================================

async def execute_get_current_price(
    name: str,
    args: GetCurrentPriceParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取当前价格"""
    result = await market_data_tools.get_current_price(args.symbol)
    return AgentToolResult(
        content=[TextContent(text=f"当前价格: {result.get('price', 'N/A')}")]
    )


async def execute_get_24hr_ticker(
    name: str,
    args: Get24hrTickerParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取24小时ticker"""
    result = await market_data_tools.get_24hr_ticker(args.symbol)
    pct = result.get('price_change_percent', 'N/A')
    vol = result.get('volume', 'N/A')
    text = f"24h价格变化: {pct}%, 成交量: {vol}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_funding_rate(
    name: str,
    args: GetFundingRateParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取资金费率"""
    result = await market_data_tools.get_funding_rate(args.symbol)
    rate = result.get('funding_rate', 'N/A')
    mark = result.get('mark_price', 'N/A')
    text = f"资金费率: {rate}, 标记价格: {mark}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_long_short_ratio(
    name: str,
    args: GetLongShortRatioParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取多空比"""
    result = await fundamental_tools.get_long_short_ratio(args.symbol)
    ratio = result.get('long_short_ratio', 'N/A')
    text = f"多空比: {ratio}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_open_interest(
    name: str,
    args: GetOpenInterestParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取持仓量"""
    result = await market_data_tools.get_open_interest(args.symbol)
    oi = result.get('open_interest', 'N/A')
    text = f"持仓量: {oi}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_fear_and_greed(
    name: str,
    args: GetFearAndGreedParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取恐惧贪婪指数"""
    result = await sentiment_tools.get_fear_and_greed_index()
    val = result.get('value', 'N/A')
    cls = result.get('value_classification', 'N/A')
    text = f"恐惧贪婪指数: {val}, 分类: {cls}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_news_sentiment(
    name: str,
    args: GetNewsSentimentParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取新闻情绪"""
    result = await sentiment_tools.get_news_sentiment(args.symbol, limit=args.limit)
    news_items = result.get("news", [])[:3] if isinstance(result, dict) else []
    text = f"最新新闻 ({len(news_items)} 条):\n"
    for item in news_items:
        title = item.get("title", "N/A")[:80]
        text += f"  - {title}...\n"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_order_book(
    name: str,
    args: GetOrderBookParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取订单簿"""
    result = await market_data_tools.get_order_book(args.symbol, limit=args.limit)
    bids = result.get("bids", [])[:5]
    asks = result.get("asks", [])[:5]
    text = f"订单簿 ({args.symbol}):\n"
    text += "买盘:\n"
    for bid in bids:
        text += f"  {bid}\n"
    text += "卖盘:\n"
    for ask in asks:
        text += f"  {ask}\n"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_social_sentiment(
    name: str,
    args: GetSocialSentimentParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取社交媒体情绪"""
    result = await sentiment_tools.get_social_sentiment(args.symbol)
    score = result.get("sentiment_score", "N/A")
    mentions = result.get("mentions", {}).get("total", "N/A")
    text = f"社交媒体情绪评分: {score}, 提及次数: {mentions}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_taker_buy_sell_ratio(
    name: str,
    args: GetTakerBuySellRatioParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取主动买卖比例"""
    result = await fundamental_tools.get_taker_buy_sell_ratio(args.symbol)
    buy_ratio = result.get("buy_ratio", "N/A")
    sell_ratio = result.get("sell_ratio", "N/A")
    text = f"主动买盘比例: {buy_ratio}, 主动卖盘比例: {sell_ratio}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_top_trader_long_short_ratio(
    name: str,
    args: GetTopTraderLongShortRatioParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取大户多空比"""
    result = await fundamental_tools.get_top_trader_long_short_ratio(args.symbol)
    long_ratio = result.get("long_short_ratio", "N/A")
    text = f"大户多空比: {long_ratio}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_liquidation_orders(
    name: str,
    args: GetLiquidationOrdersParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取清算订单"""
    result = await fundamental_tools.get_liquidation_orders(args.symbol)
    orders = result.get("orders", [])[:5] if isinstance(result, dict) else []
    text = f"清算订单 ({len(orders)} 条):\n"
    for order in orders:
        text += f"  {order}\n"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_trending_symbols(
    name: str,
    args: GetTrendingSymbolsParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取热门交易对"""
    result = await sentiment_tools.get_trending_symbols()
    symbols = result.get("symbols", [])[:10] if isinstance(result, dict) else []
    text = f"热门交易对 ({len(symbols)} 个):\n"
    for symbol_info in symbols:
        text += f"  {symbol_info}\n"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_comprehensive_sentiment(
    name: str,
    args: GetComprehensiveSentimentParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取综合情绪分析"""
    result = await sentiment_tools.get_comprehensive_sentiment(args.symbol)
    score = result.get("overall_score", "N/A")
    signal = result.get("signal", "N/A")
    text = f"综合情绪评分: {score}, 信号: {signal}"
    return AgentToolResult(content=[TextContent(text=text)])


# =============================================================================
# 技术分析工具执行函数
# =============================================================================

async def execute_get_technical_indicators(
    name: str,
    args: GetTechnicalIndicatorsParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取技术指标"""
    result = await technical_tools.get_technical_indicators(args.symbol, args.interval)
    if "error" in result:
        return AgentToolResult(content=[TextContent(text=f"错误: {result['error']}")])

    indicators = result.get("indicators", {})
    text = f"""技术指标 ({args.symbol} {args.interval}):
RSI: {indicators.get('rsi', 'N/A')}
MACD: {indicators.get('macd', 'N/A')}
布林带: [{indicators.get('bollinger_lower', 'N/A')}, {indicators.get('bollinger_upper', 'N/A')}]
ATR: {indicators.get('atr', 'N/A')}"""
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_kline_data(
    name: str,
    args: GetKlineDataParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取K线数据"""
    result = await technical_tools.get_kline_data(args.symbol, args.interval, args.limit)
    if "error" in result:
        return AgentToolResult(content=[TextContent(text=f"错误: {result['error']}")])

    klines = result.get("klines", [])
    text = f"K线数据: 共 {len(klines)} 条，最新: {klines[-1] if klines else 'N/A'}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_get_comprehensive_technical_analysis(
    name: str,
    args: GetComprehensiveTechnicalAnalysisParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行获取综合技术分析"""
    result = await technical_tools.get_comprehensive_technical_analysis(args.symbol, args.interval)
    if "error" in result:
        return AgentToolResult(content=[TextContent(text=f"错误: {result['error']}")])

    trend = result.get("trend", "N/A")
    signals = result.get("signals", [])
    text = f"趋势: {trend}\n信号: {', '.join(signals[:5])}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_analyze_trend(
    name: str,
    args: AnalyzeTrendParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行趋势分析"""
    result = await technical_tools.analyze_trend(args.symbol, args.interval)
    if "error" in result:
        return AgentToolResult(content=[TextContent(text=f"错误: {result['error']}")])

    trend = result.get("trend", "N/A")
    strength = result.get("strength", "N/A")
    text = f"趋势: {trend}, 强度: {strength}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_detect_support_resistance(
    name: str,
    args: DetectSupportResistanceParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行支撑阻力检测"""
    result = await technical_tools.detect_support_resistance(args.symbol, args.interval)
    if "error" in result:
        return AgentToolResult(content=[TextContent(text=f"错误: {result['error']}")])

    support = result.get("support_levels", [])
    resistance = result.get("resistance_levels", [])
    text = f"支撑位: {support[:3]}\n阻力位: {resistance[:3]}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_calculate_pivots(
    name: str,
    args: CalculatePivotsParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行枢轴点计算"""
    result = await technical_tools.calculate_pivots(args.symbol, args.interval)
    if "error" in result:
        return AgentToolResult(content=[TextContent(text=f"错误: {result['error']}")])

    pivots = result.get("pivots", {})
    text = f"枢轴点: {pivots}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_detect_candlestick_patterns(
    name: str,
    args: DetectCandlestickPatternsParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行K线形态检测"""
    result = await technical_tools.detect_candlestick_patterns(args.symbol, args.interval)
    if "error" in result:
        return AgentToolResult(content=[TextContent(text=f"错误: {result['error']}")])

    patterns = result.get("patterns", [])
    text = f"检测到的形态: {', '.join(patterns[:5])}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_detect_divergence(
    name: str,
    args: DetectDivergenceParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行背离检测"""
    result = await technical_tools.detect_divergence(args.symbol, args.interval)
    if "error" in result:
        return AgentToolResult(content=[TextContent(text=f"错误: {result['error']}")])

    divergences = result.get("divergences", [])
    text = f"背离信号: {divergences}"
    return AgentToolResult(content=[TextContent(text=text)])


async def execute_analyze_volume_patterns(
    name: str,
    args: AnalyzeVolumePatternsParams,
    extra: Any = None,
    callback: Any = None,
) -> AgentToolResult:
    """执行成交量模式分析"""
    result = await technical_tools.analyze_volume_patterns(args.symbol, args.interval)
    if "error" in result:
        return AgentToolResult(content=[TextContent(text=f"错误: {result['error']}")])

    pattern = result.get("pattern", "N/A")
    confirmation = result.get("confirmation", "N/A")
    text = f"成交量模式: {pattern}, 确认度: {confirmation}"
    return AgentToolResult(content=[TextContent(text=text)])


def create_submit_trade_order_tool(tool_context: Any) -> AgentTool:
    """Create a Portfolio Manager execution tool bound to a ToolContext."""

    async def execute_submit_trade_order(
        name: str,
        args: SubmitTradeOrderParams,
        extra: Any = None,
        callback: Any = None,
    ) -> AgentToolResult:
        """Submit an order through the configured executor."""
        if not getattr(tool_context, "executor", None):
            raise RuntimeError("No order executor configured for this agent context")

        from vibe_trading.data_sources.binance_client import OrderSide, OrderType, PositionSide

        side = OrderSide(args.side.upper())
        order_type = OrderType(args.order_type.upper())
        position_side = PositionSide(args.position_side.upper())

        result = await tool_context.executor.place_order(
            symbol=args.symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=args.quantity,
            price=args.price,
            stop_price=args.stop_price,
            position_side=position_side,
        )

        details = {
            "order_id": result.order_id,
            "symbol": result.symbol,
            "side": result.side.value,
            "order_type": result.order_type.value,
            "quantity": result.quantity,
            "price": result.price,
            "filled_price": result.filled_price,
            "filled_quantity": result.filled_quantity,
            "status": result.status,
            "is_paper": result.is_paper,
            "rationale": args.rationale,
        }
        text = (
            f"订单已提交: {result.status}\n"
            f"order_id={result.order_id}, symbol={result.symbol}, side={result.side.value}, "
            f"type={result.order_type.value}, quantity={result.quantity}, "
            f"filled={result.filled_quantity} @ {result.filled_price}"
        )
        return AgentToolResult(content=[TextContent(text=text)], details=details)

    return AgentTool(
        name="submit_trade_order",
        label="提交交易订单",
        description=(
            "Portfolio Manager 专用执行工具。仅在最终批准交易后调用。"
            "根据当前执行器配置提交订单；Paper/Dry-run 模式不会触发真实主网成交。"
        ),
        parameters=SubmitTradeOrderParams,
        execute=execute_submit_trade_order,
    )


def get_execution_tools(tool_context: Any) -> list[AgentTool]:
    """Get execution tools bound to the provided ToolContext."""
    return [create_submit_trade_order_tool(tool_context)]


# =============================================================================
# Tool 定义
# =============================================================================

def get_all_tools() -> list[AgentTool]:
    """获取所有可用工具 (共24个)"""
    return [
        # ========== 基础市场数据 (5个) ==========
        AgentTool(
            name="get_current_price",
            label="获取当前价格",
            description="获取指定交易对的当前市场价格",
            parameters=GetCurrentPriceParams,
            execute=execute_get_current_price,
        ),
        AgentTool(
            name="get_24hr_ticker",
            label="获取24小时行情",
            description="获取指定交易对24小时价格变动数据",
            parameters=Get24hrTickerParams,
            execute=execute_get_24hr_ticker,
        ),
        AgentTool(
            name="get_funding_rate",
            label="获取资金费率",
            description="获取永续合约的资金费率",
            parameters=GetFundingRateParams,
            execute=execute_get_funding_rate,
        ),
        AgentTool(
            name="get_long_short_ratio",
            label="获取多空比",
            description="获取账户多空持仓比",
            parameters=GetLongShortRatioParams,
            execute=execute_get_long_short_ratio,
        ),
        AgentTool(
            name="get_open_interest",
            label="获取持仓量",
            description="获取合约持仓量",
            parameters=GetOpenInterestParams,
            execute=execute_get_open_interest,
        ),

        # ========== 情绪分析工具 (3个) ==========
        AgentTool(
            name="get_fear_and_greed_index",
            label="获取恐惧贪婪指数",
            description="获取加密市场恐惧贪婪指数",
            parameters=GetFearAndGreedParams,
            execute=execute_get_fear_and_greed,
        ),
        AgentTool(
            name="get_news_sentiment",
            label="获取新闻情绪",
            description="获取最新的加密货币新闻及其情绪分析",
            parameters=GetNewsSentimentParams,
            execute=execute_get_news_sentiment,
        ),
        AgentTool(
            name="get_social_sentiment",
            label="获取社交媒体情绪",
            description="获取社交媒体上的讨论情绪和提及次数",
            parameters=GetSocialSentimentParams,
            execute=execute_get_social_sentiment,
        ),

        # ========== 深度数据工具 (4个) ==========
        AgentTool(
            name="get_order_book",
            label="获取订单簿",
            description="获取交易对的订单簿深度数据",
            parameters=GetOrderBookParams,
            execute=execute_get_order_book,
        ),
        AgentTool(
            name="get_taker_buy_sell_ratio",
            label="获取主动买卖比例",
            description="获取主动买盘和卖盘的比例",
            parameters=GetTakerBuySellRatioParams,
            execute=execute_get_taker_buy_sell_ratio,
        ),
        AgentTool(
            name="get_top_trader_long_short_ratio",
            label="获取大户多空比",
            description="获取大户(Top Trader)的多空持仓比例",
            parameters=GetTopTraderLongShortRatioParams,
            execute=execute_get_top_trader_long_short_ratio,
        ),
        AgentTool(
            name="get_liquidation_orders",
            label="获取清算订单",
            description="获取最近的清算订单数据",
            parameters=GetLiquidationOrdersParams,
            execute=execute_get_liquidation_orders,
        ),

        # ========== 综合分析工具 (2个) ==========
        AgentTool(
            name="get_trending_symbols",
            label="获取热门交易对",
            description="获取当前热门的交易对列表",
            parameters=GetTrendingSymbolsParams,
            execute=execute_get_trending_symbols,
        ),
        AgentTool(
            name="get_comprehensive_sentiment",
            label="获取综合情绪分析",
            description="获取综合情绪评分和信号",
            parameters=GetComprehensiveSentimentParams,
            execute=execute_get_comprehensive_sentiment,
        ),

        # ========== 技术分析工具 (9个) ==========
        AgentTool(
            name="get_technical_indicators",
            label="获取技术指标",
            description="获取RSI、MACD、布林带等技术指标",
            parameters=GetTechnicalIndicatorsParams,
            execute=execute_get_technical_indicators,
        ),
        AgentTool(
            name="get_kline_data",
            label="获取K线数据",
            description="获取指定交易对的K线数据",
            parameters=GetKlineDataParams,
            execute=execute_get_kline_data,
        ),
        AgentTool(
            name="get_comprehensive_technical_analysis",
            label="获取综合技术分析",
            description="获取综合技术分析包括趋势、信号等",
            parameters=GetComprehensiveTechnicalAnalysisParams,
            execute=execute_get_comprehensive_technical_analysis,
        ),
        AgentTool(
            name="analyze_trend",
            label="分析趋势",
            description="分析当前价格趋势方向和强度",
            parameters=AnalyzeTrendParams,
            execute=execute_analyze_trend,
        ),
        AgentTool(
            name="detect_support_resistance",
            label="检测支撑阻力",
            description="检测支撑位和阻力位",
            parameters=DetectSupportResistanceParams,
            execute=execute_detect_support_resistance,
        ),
        AgentTool(
            name="calculate_pivots",
            label="计算枢轴点",
            description="计算枢轴点和支撑阻力位",
            parameters=CalculatePivotsParams,
            execute=execute_calculate_pivots,
        ),
        AgentTool(
            name="detect_candlestick_patterns",
            label="检测K线形态",
            description="检测K线形态如十字星、锤子线等",
            parameters=DetectCandlestickPatternsParams,
            execute=execute_detect_candlestick_patterns,
        ),
        AgentTool(
            name="detect_divergence",
            label="检测背离",
            description="检测价格与指标的背离信号",
            parameters=DetectDivergenceParams,
            execute=execute_detect_divergence,
        ),
        AgentTool(
            name="analyze_volume_patterns",
            label="分析成交量模式",
            description="分析成交量模式和趋势确认",
            parameters=AnalyzeVolumePatternsParams,
            execute=execute_analyze_volume_patterns,
        ),
    ]


def get_agent_tools() -> list[AgentTool]:
    """获取通用工具集合 (向后兼容)"""
    return get_all_tools()


def get_tools_for_agent(agent_role: str) -> list[AgentTool]:
    """根据Agent角色分配专门的工具集合

    Args:
        agent_role: Agent角色 (technical_analyst, fundamental_analyst, etc.)

    Returns:
        该角色专用的工具列表
    """
    all_tools = {tool.name: tool for tool in get_all_tools()}

    # 分析师团队 - 专注于各自领域的数据
    if agent_role == "technical_analyst":
        # 技术分析师需要技术分析工具
        return [
            all_tools["get_current_price"],
            all_tools["get_24hr_ticker"],
            all_tools["get_order_book"],
            all_tools["get_technical_indicators"],
            all_tools["get_comprehensive_technical_analysis"],
            all_tools["analyze_trend"],
            all_tools["detect_support_resistance"],
            all_tools["detect_candlestick_patterns"],
        ]

    elif agent_role == "fundamental_analyst":
        return [
            all_tools["get_funding_rate"],
            all_tools["get_long_short_ratio"],
            all_tools["get_open_interest"],
            all_tools["get_taker_buy_sell_ratio"],
            all_tools["get_top_trader_long_short_ratio"],
        ]

    elif agent_role == "news_analyst":
        return [
            all_tools["get_news_sentiment"],
            all_tools["get_trending_symbols"],
        ]

    elif agent_role == "sentiment_analyst":
        return [
            all_tools["get_fear_and_greed_index"],
            all_tools["get_social_sentiment"],
            all_tools["get_comprehensive_sentiment"],
            all_tools["get_funding_rate"],  # 资金费率反映情绪
            all_tools["get_long_short_ratio"],  # 多空比反映情绪
        ]

    # 研究员团队 - 综合工具用于辩论
    elif agent_role in ["bull_researcher", "bear_researcher", "research_manager"]:
        return [
            all_tools["get_current_price"],
            all_tools["get_24hr_ticker"],
            all_tools["get_fear_and_greed_index"],
            all_tools["get_news_sentiment"],
            all_tools["get_funding_rate"],
            all_tools["get_long_short_ratio"],
            all_tools["get_open_interest"],
            all_tools["get_technical_indicators"],  # 添加技术指标
        ]

    # 风控团队 - 需要风险相关数据
    elif agent_role in ["aggressive_debator", "neutral_debator", "conservative_debator"]:
        return [
            all_tools["get_liquidation_orders"],
            all_tools["get_funding_rate"],
            all_tools["get_open_interest"],
            all_tools["get_taker_buy_sell_ratio"],
        ]

    # 决策团队 - 需要全面数据
    elif agent_role == "trader":
        return [
            all_tools["get_current_price"],
            all_tools["get_24hr_ticker"],
            all_tools["get_order_book"],
            all_tools["get_funding_rate"],
            all_tools["get_technical_indicators"],
        ]

    elif agent_role == "portfolio_manager":
        # 投资组合经理需要所有工具
        return get_all_tools()

    # 默认返回基础工具
    return [
        all_tools["get_current_price"],
        all_tools["get_24hr_ticker"],
        all_tools["get_fear_and_greed_index"],
    ]
