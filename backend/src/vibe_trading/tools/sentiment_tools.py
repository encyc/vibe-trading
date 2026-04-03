"""
情绪分析工具

为 Agent 提供市场情绪分析相关的工具函数。

注意: 本模块只使用真实数据源。如果 API 不可用或需要付费，将返回错误而非模拟数据。
"""
import logging
from typing import Optional
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# 工具参数模型
# =============================================================================

class GetMarketSentimentParams(BaseModel):
    """获取市场情绪参数"""
    symbol: Optional[str] = Field(default=None, description="交易对符号（可选）")


# =============================================================================
# 工具函数
# =============================================================================

async def get_fear_and_greed_index() -> dict:
    """
    获取加密货币恐惧与贪婪指数

    Returns:
        恐惧与贪婪指数数据
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.alternative.me/fng/", timeout=10.0)
            data = response.json()

            value = int(data["data"][0]["value"])
            classification = data["data"][0]["value_classification"]

            # 添加情绪解读
            if value <= 20:
                sentiment = "extreme_fear"
                interpretation = "市场极度恐惧，可能是反向买入机会"
            elif value <= 40:
                sentiment = "fear"
                interpretation = "市场恐惧，投资者谨慎"
            elif value <= 60:
                sentiment = "neutral"
                interpretation = "市场中性，观望为主"
            elif value <= 80:
                sentiment = "greed"
                interpretation = "市场贪婪，注意风险"
            else:
                sentiment = "extreme_greed"
                interpretation = "市场极度贪婪，可能是反向卖出信号"

            return {
                "value": value,
                "classification": classification,
                "sentiment": sentiment,
                "interpretation": interpretation,
                "timestamp": data["data"][0]["timestamp"],
            }
    except Exception as e:
        logger.error(f"Error fetching Fear & Greed Index: {e}")
        return {"error": str(e)}


async def get_social_sentiment(symbol: str) -> dict:
    """
    获取社交媒体情绪 (优先使用 LunarCrush，备用 CryptoCompare)

    LunarCrush: 免费层可用 (100请求/天)
    CryptoCompare: 需要付费订阅

    Args:
        symbol: 交易对符号 (如 BTCUSDT -> BTC)

    Returns:
        社交媒体情绪数据，或错误信息
    """
    from vibe_trading.config.settings import get_settings

    settings = get_settings()

    # 映射交易对符号
    symbol_map = {
        "BTCUSDT": "BTC",
        "ETHUSDT": "ETH",
        "BNBUSDT": "BNB",
        "SOLUSDT": "SOL",
    }
    coin = symbol_map.get(symbol, symbol.replace("USDT", "")) if symbol else "BTC"

    # 优先尝试 LunarCrush (免费)
    lunarcrush_key = settings.lunarcrush_api_key
    if lunarcrush_key:
        try:
            async with httpx.AsyncClient() as client:
                # LunarCrush API v4
                # 文档: https://github.com/lunarcrush/api
                # Base URL: https://lunarcrush.com/api4
                # 注意: v4 API 可能需要付费订阅，免费 tier 可能无法访问所有端点

                # 尝试多个端点格式
                endpoints_to_try = [
                    f"https://lunarcrush.com/api4/public/feed/social/v2/{coin}",
                    f"https://lunarcrush.com/api4/public/feeds/social/v2/{coin}",
                    f"https://lunarcrush.com/api4/feed/social/v2/{coin}",
                ]

                for endpoint_url in endpoints_to_try:
                    headers = {"Authorization": f"Bearer {lunarcrush_key}"}
                    response = await client.get(endpoint_url, headers=headers, timeout=10.0)

                    if response.status_code == 200:
                        data = response.json()
                        if data.get("data") and len(data["data"]) > 0:
                            asset = data["data"][0]

                            # 提取社交媒体指标
                            sentiment_score = asset.get("sentiment", 0)
                            social_score = asset.get("social_score", 0)
                            galaxy_score = asset.get("galaxy_score", 0)
                            close_price = asset.get("close", 0)

                            # 提取社交媒体统计
                            social_volume = asset.get("social_volume", 0)
                            social_volume_24h_change = asset.get("social_volume_24h_change", 0)
                            social_contributors = asset.get("social_contributors", 0)
                            social_score_global_ranking = asset.get("social_score_global_ranking", 0)

                            # 计算情绪分类
                            if sentiment_score > 5:
                                sentiment = "very_bullish"
                            elif sentiment_score > 2:
                                sentiment = "bullish"
                            elif sentiment_score > -2:
                                sentiment = "neutral"
                            elif sentiment_score > -5:
                                sentiment = "bearish"
                            else:
                                sentiment = "very_bearish"

                            return {
                                "symbol": symbol,
                                "coin": coin,
                                "sentiment": sentiment,
                                "sentiment_score": sentiment_score,
                                "social_metrics": {
                                    "social_score": social_score,
                                    "galaxy_score": galaxy_score,
                                    "social_volume": social_volume,
                                    "social_volume_24h_change": social_volume_24h_change,
                                    "social_contributors": social_contributors,
                                    "global_ranking": social_score_global_ranking,
                                },
                                "price": close_price,
                                "mentions": {
                                    "total": social_volume,
                                    "contributors": social_contributors,
                                },
                                "source": "LunarCrush",
                                "available": True,
                            }

                # 如果所有端点都失败了，记录日志继续下一个数据源
                logger.debug(f"LunarCrush API: All endpoints returned non-200 status codes")
        except Exception as e:
            logger.debug(f"LunarCrush API failed: {e}")

    # 备用: 尝试 CryptoCompare (需要付费)
    cryptocmp_key = settings.cryptocmp_api_key
    if cryptocmp_key:
        try:
            async with httpx.AsyncClient() as client:
                headers = {"authorization": f"Apikey {cryptocmp_key}"}

                # 尝试不同的社交数据端点
                endpoints = [
                    f"https://min-api.cryptocompare.com/data/social/coin/latest/",
                    f"https://min-api.cryptocompare.com/data/social/coin/histo/day/",
                ]

                for endpoint_base in endpoints:
                    try:
                        response = await client.get(
                            endpoint_base,
                            params={"coinId": coin},
                            headers=headers,
                            timeout=10.0
                        )

                        if response.status_code == 200:
                            data = response.json()
                            if data.get("Data") and len(data["Data"]) > 0:
                                stats = data["Data"][0] if isinstance(data["Data"], list) else data["Data"]

                                twitter_followers = stats.get("twitter_followers", 0)
                                reddit_users = stats.get("reddit_users", 0)
                                total_followers = twitter_followers + reddit_users

                                change_24h = stats.get("change", 0)
                                if change_24h > 5:
                                    sentiment = "very_bullish"
                                    sentiment_score = min(50, change_24h * 5)
                                elif change_24h > 2:
                                    sentiment = "bullish"
                                    sentiment_score = min(30, change_24h * 3)
                                elif change_24h > -2:
                                    sentiment = "neutral"
                                    sentiment_score = change_24h * 2
                                elif change_24h > -5:
                                    sentiment = "bearish"
                                    sentiment_score = max(-30, change_24h * 3)
                                else:
                                    sentiment = "very_bearish"
                                    sentiment_score = max(-50, change_24h * 5)

                                return {
                                    "symbol": symbol,
                                    "coin": coin,
                                    "sentiment": sentiment,
                                    "sentiment_score": sentiment_score,
                                    "change_24h": change_24h,
                                    "social_stats": {
                                        "twitter_followers": twitter_followers,
                                        "reddit_users": reddit_users,
                                        "total_followers": total_followers,
                                    },
                                    "mentions": {
                                        "total": total_followers,
                                        "code_repo": stats.get("code_repo_mentions", 0),
                                        "followers": stats.get("followers", 0),
                                    },
                                    "source": "CryptoCompare",
                                    "available": True,
                                }
                    except Exception as e:
                        logger.debug(f"Endpoint {endpoint_base} failed: {e}")
                        continue
        except Exception as e:
            logger.debug(f"CryptoCompare social API failed: {e}")

    # 所有数据源都失败
    return {
        "error": "Social sentiment data not available",
        "available": False,
        "symbol": symbol,
        "lunarcrush_status": "configured but unavailable - v4 API may require paid subscription or the API key needs to be regenerated",
        "cryptocompare_status": "requires paid subscription for social data",
        "message": "To enable social sentiment: (1) Upgrade LunarCrush subscription at https://lunarcrush.com/ or (2) Subscribe to CryptoCompare Hobby tier at https://www.cryptocompare.com/",
    }


async def get_news_sentiment(symbol: Optional[str] = None, limit: int = 10) -> dict:
    """
    获取加密货币新闻 (使用 CryptoCompare API)

    Args:
        symbol: 可选的交易对符号 (如 BTC, ETH)
        limit: 返回新闻数量

    Returns:
        新闻情绪数据，或错误信息
    """
    from vibe_trading.config.settings import get_settings

    settings = get_settings()
    api_key = settings.cryptocmp_api_key

    if not api_key:
        return {
            "error": "CRYPTOCOMPARE_API_KEY not configured",
            "available": False,
            "symbol": symbol,
        }

    # 映射交易对符号到 CryptoCompare 格式
    symbol_map = {
        "BTCUSDT": "BTC",
        "ETHUSDT": "ETH",
        "BNBUSDT": "BNB",
        "SOLUSDT": "SOL",
    }
    cc_symbol = symbol_map.get(symbol, "BTC") if symbol else "BTC"

    try:
        async with httpx.AsyncClient() as client:
            # CryptoCompare News API v2
            # 文档: https://min-api.cryptocompare.com/data/v2/news/
            params = {
                "lang": "EN",
                "sortOrder": "latest",
                "limit": limit * 3,  # 获取更多，然后过滤
            }
            # 注意: authorization header 格式是 "Apikey {key}" (不是 "Bearer")
            headers = {
                "authorization": f"Apikey {api_key}"
            }

            response = await client.get(
                "https://min-api.cryptocompare.com/data/v2/news/",
                params=params,
                headers=headers,
                timeout=10.0
            )
            data = response.json()

            # 检查响应
            if response.status_code != 200 or not data.get("Data"):
                logger.warning(f"CryptoCompare News API error: status={response.status_code}")
                return {
                    "error": f"API returned error status {response.status_code}",
                    "available": False,
                    "symbol": symbol,
                }

            news_list = data.get("Data", [])
            if not news_list:
                logger.warning("CryptoCompare returned empty news list")
                return {
                    "error": "No news data available",
                    "available": False,
                    "symbol": symbol,
                }

            # 如果指定了 symbol，过滤相关新闻
            filtered_news = []
            keywords = [cc_symbol, "crypto", "bitcoin", "ethereum", "blockchain", "trading"]

            for item in news_list:
                title = item.get("title", "").lower()
                body = item.get("body", "").lower()
                combined = title + " " + body

                # 检查是否包含相关关键词
                if any(keyword.lower() in combined for keyword in keywords):
                    filtered_news.append({
                        "title": item.get("title"),
                        "body": item.get("body", "")[:200],  # 只取前200字符
                        "source": item.get("source"),
                        "url": item.get("url"),
                        "published_at": item.get("published_on"),
                        "categories": item.get("categories", []),
                    })

                if len(filtered_news) >= limit:
                    break

            # 计算情绪倾向
            positive_words = ["surge", "rally", "gain", "rise", "bullish", "growth", "high", "breakthrough", "adoption", "launch", "partnership"]
            negative_words = ["crash", "fall", "drop", "decline", "bearish", "loss", "low", "concern", "risk", "ban", "regulation"]

            positive_count = 0
            negative_count = 0
            neutral_count = 0

            for news in filtered_news:
                text = (news["title"] + " " + news["body"]).lower()
                pos_score = sum(1 for word in positive_words if word in text)
                neg_score = sum(1 for word in negative_words if word in text)

                if pos_score > neg_score:
                    positive_count += 1
                elif neg_score > pos_score:
                    negative_count += 1
                else:
                    neutral_count += 1

            overall_sentiment = "neutral"
            if positive_count > negative_count + neutral_count:
                overall_sentiment = "positive"
            elif negative_count > positive_count + neutral_count:
                overall_sentiment = "negative"

            return {
                "symbol": symbol or "crypto",
                "overall_sentiment": overall_sentiment,
                "news_count": len(filtered_news),
                "sentiment_breakdown": {
                    "positive": positive_count,
                    "negative": negative_count,
                    "neutral": neutral_count,
                },
                "news": filtered_news,
                "source": "CryptoCompare",
                "available": True,
            }

    except Exception as e:
        logger.error(f"Error fetching news from CryptoCompare: {e}")
        return {"error": str(e), "available": False, "symbol": symbol}


async def get_comprehensive_sentiment(symbol: str) -> dict:
    """
    获取综合情绪分析

    结合多个情绪指标给出综合分析。

    Args:
        symbol: 交易对符号

    Returns:
        综合情绪分析
    """
    # 获取各项情绪数据
    fng_data = await get_fear_and_greed_index()
    social_data = await get_social_sentiment(symbol)
    news_data = await get_news_sentiment(symbol)

    # 计算综合情绪分数
    scores = []
    weights = []
    available_sources = []

    # 恐惧贪婪指数 (-50 to +50)
    if "value" in fng_data:
        fng_score = (fng_data["value"] - 50)
        scores.append(fng_score)
        weights.append(0.3)
        available_sources.append("fear_greed")

    # 社交媒体情绪 (-100 to +100)
    if social_data.get("available") and "sentiment_score" in social_data:
        scores.append(social_data["sentiment_score"])
        weights.append(0.4)
        available_sources.append("social")

    # 新闻情绪 (-100 to +100)
    news_sentiment_map = {"positive": 50, "neutral": 0, "negative": -50}
    if news_data.get("available") and "overall_sentiment" in news_data:
        news_score = news_sentiment_map.get(news_data["overall_sentiment"], 0)
        scores.append(news_score)
        weights.append(0.3)
        available_sources.append("news")

    # 计算加权平均
    if scores and weights:
        total_weight = sum(weights)
        weighted_score = sum(s * w for s, w in zip(scores, weights)) / total_weight
    else:
        weighted_score = 0

    # 确定综合情绪
    if weighted_score > 30:
        overall_sentiment = "very_bullish"
        signal = "Strong Buy"
    elif weighted_score > 10:
        overall_sentiment = "bullish"
        signal = "Buy"
    elif weighted_score > -10:
        overall_sentiment = "neutral"
        signal = "Hold"
    elif weighted_score > -30:
        overall_sentiment = "bearish"
        signal = "Sell"
    else:
        overall_sentiment = "very_bearish"
        signal = "Strong Sell"

    return {
        "symbol": symbol,
        "overall_sentiment": overall_sentiment,
        "sentiment_score": weighted_score,
        "signal": signal,
        "available_sources": available_sources,
        "components": {
            "fear_greed_index": fng_data,
            "social_sentiment": social_data,
            "news_sentiment": news_data,
        },
    }


async def get_trending_symbols() -> dict:
    """
    获取热门交易对

    Returns:
        热门交易对列表，或错误信息
    """
    # 此功能需要接入真实数据源
    return {
        "error": "Trending symbols data not available - requires integration with a real data source",
        "available": False,
    }
