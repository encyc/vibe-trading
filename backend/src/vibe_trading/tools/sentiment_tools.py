"""
情绪分析工具

为 Agent 提供市场情绪分析相关的工具函数。
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
    获取社交媒体情绪 (使用 CryptoCompare API)

    Args:
        symbol: 交易对符号 (如 BTCUSDT -> BTC)

    Returns:
        社交媒体情绪数据
    """
    from vibe_trading.config.settings import get_settings

    settings = get_settings()
    api_key = settings.cryptocmp_api_key

    # 映射交易对符号
    symbol_map = {
        "BTCUSDT": "BTC",
        "ETHUSDT": "ETH",
        "BNBUSDT": "BNB",
        "SOLUSDT": "SOL",
    }
    cc_symbol = symbol_map.get(symbol, symbol.replace("USDT", "")) if symbol else "BTC"

    if not api_key:
        # 没有配置 API key 时返回模拟数据
        return await _get_simulated_social_sentiment(symbol)

    try:
        async with httpx.AsyncClient() as client:
            # CryptoCompare Social Stats API
            # 免费版可能不包含社交数据，尝试使用替代方案
            headers = {
                "authorization": f"Apikey {api_key}"
            }

            # 尝试不同的社交数据端点
            endpoints = [
                # 端点1: 最新社交统计 (legacy)
                f"https://min-api.cryptocompare.com/data/social/coin/latest/",
                # 端点2: 历史社交统计
                f"https://min-api.cryptocompare.com/data/social/coin/histo/day/",
            ]

            for endpoint_base in endpoints:
                try:
                    response = await client.get(
                        endpoint_base,
                        params={"coinId": cc_symbol},
                        headers=headers,
                        timeout=10.0
                    )

                    if response.status_code == 200:
                        data = response.json()
                        if data.get("Data") and len(data["Data"]) > 0:
                            # 成功获取数据
                            stats = data["Data"][0] if isinstance(data["Data"], list) else data["Data"]

                            # 解析社交数据
                            twitter_followers = stats.get("twitter_followers", 0)
                            reddit_users = stats.get("reddit_users", 0)
                            total_followers = twitter_followers + reddit_users

                            # 根据粉丝增长计算情绪
                            # 这里使用简化的逻辑，实际可以更复杂
                            sentiment_score = 0
                            if total_followers > 0:
                                sentiment = "neutral"
                            else:
                                sentiment = "neutral"

                            return {
                                "symbol": symbol,
                                "cc_symbol": cc_symbol,
                                "sentiment": sentiment,
                                "sentiment_score": sentiment_score,
                                "social_stats": {
                                    "twitter_followers": twitter_followers,
                                    "reddit_users": reddit_users,
                                    "total_followers": total_followers,
                                },
                                "mentions": {
                                    "total": total_followers,
                                },
                                "source": "CryptoCompare",
                            }
                except Exception as e:
                    logger.debug(f"Endpoint {endpoint_base} failed: {e}")
                    continue

            # 所有端点都失败
            logger.warning("All CryptoCompare social endpoints failed, using simulated data")
            return await _get_simulated_social_sentiment(symbol)

            stats = data["Data"][0]

            # 解析数据
            twitter_followers = stats.get("twitter_followers", 0)
            reddit_users = stats.get("reddit_users", 0)
            facebook_users = stats.get("facebook_users", 0)

            # 计算情绪分数
            total_mentions = stats.get("code_repo_mentions", 0) + stats.get("followers", 0)

            # 获取更多社交媒体数据
            social_stats = {
                "twitter_followers": twitter_followers,
                "reddit_users": reddit_users,
                "facebook_users": facebook_users,
                "total_followers": twitter_followers + reddit_users + facebook_users,
            }

            # 计算情绪趋势 (基于24小时变化)
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
                "cc_symbol": cc_symbol,
                "sentiment": sentiment,
                "sentiment_score": sentiment_score,
                "change_24h": change_24h,
                "social_stats": social_stats,
                "mentions": {
                    "total": total_mentions,
                    "code_repo": stats.get("code_repo_mentions", 0),
                    "followers": stats.get("followers", 0),
                },
                "source": "CryptoCompare",
            }

    except Exception as e:
        logger.error(f"Error fetching social sentiment from CryptoCompare: {e}")
        return await _get_simulated_social_sentiment(symbol)


async def _get_simulated_social_sentiment(symbol: str) -> dict:
    """获取模拟社交媒体情绪数据（后备方案）"""
    import random

    positive_mentions = random.randint(100, 1000)
    negative_mentions = random.randint(50, 500)
    neutral_mentions = random.randint(200, 800)

    total_mentions = positive_mentions + negative_mentions + neutral_mentions

    if total_mentions > 0:
        positive_ratio = positive_mentions / total_mentions
        negative_ratio = negative_mentions / total_mentions
        neutral_ratio = neutral_mentions / total_mentions
    else:
        positive_ratio = negative_ratio = neutral_ratio = 0.33

    sentiment_score = (positive_ratio - negative_ratio) * 100

    if sentiment_score > 30:
        sentiment = "very_bullish"
    elif sentiment_score > 10:
        sentiment = "bullish"
    elif sentiment_score > -10:
        sentiment = "neutral"
    elif sentiment_score > -30:
        sentiment = "bearish"
    else:
        sentiment = "very_bearish"

    return {
        "symbol": symbol,
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "mentions": {
            "positive": positive_mentions,
            "negative": negative_mentions,
            "neutral": neutral_mentions,
            "total": total_mentions,
        },
        "ratios": {
            "positive": positive_ratio,
            "negative": negative_ratio,
            "neutral": neutral_ratio,
        },
        "source": "Simulated",
        "note": "Using simulated data. Configure CRYPTOCOMPARE_API_KEY for real data.",
    }


async def get_news_sentiment(symbol: Optional[str] = None, limit: int = 10) -> dict:
    """
    获取加密货币新闻 (使用 CryptoCompare API)

    Args:
        symbol: 可选的交易对符号 (如 BTC, ETH)
        limit: 返回新闻数量

    Returns:
        新闻情绪数据
    """
    from vibe_trading.config.settings import get_settings

    settings = get_settings()
    api_key = settings.cryptocmp_api_key

    if not api_key:
        # 没有配置 API key 时返回模拟数据
        return await _get_simulated_news(symbol, limit)

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

            # 检查响应 - News API 返回的格式不同
            if response.status_code != 200 or not data.get("Data"):
                logger.warning(f"CryptoCompare News API error: status={response.status_code}, response={data}")
                return await _get_simulated_news(symbol, limit)

            news_list = data.get("Data", [])
            if not news_list:
                logger.warning("CryptoCompare returned empty news list")
                return await _get_simulated_news(symbol, limit)

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
            }

    except Exception as e:
        logger.error(f"Error fetching news from CryptoCompare: {e}")
        return await _get_simulated_news(symbol, limit)


async def _get_simulated_news(symbol: Optional[str] = None, limit: int = 10) -> dict:
    """获取模拟新闻数据（后备方案）"""
    import random
    from datetime import datetime, timedelta

    simulated_news = []
    sentiments = ["positive", "neutral", "negative"]

    for i in range(limit):
        if random.random() > 0.5:
            title = f"{symbol or 'Crypto'} shows {'strength' if random.random() > 0.3 else 'weakness'} as market {'rallies' if random.random() > 0.5 else 'declines'}"
        else:
            title = f"Analysts see {'upside' if random.random() > 0.4 else 'downside'} for {symbol or 'crypto'} amid market volatility"

        sentiment = random.choice(sentiments)

        simulated_news.append({
            "title": title,
            "body": f"Market analysis for {symbol or 'crypto'}...",
            "source": "Simulated",
            "published_at": int((datetime.now() - timedelta(hours=random.randint(1, 24))).timestamp()),
            "categories": ["Trading"],
            "sentiment": sentiment,  # 添加缺失的字段
        })

    positive_count = sum(1 for n in simulated_news if n["sentiment"] == "positive")
    negative_count = sum(1 for n in simulated_news if n["sentiment"] == "negative")
    neutral_count = sum(1 for n in simulated_news if n["sentiment"] == "neutral")

    overall_sentiment = "neutral"
    if positive_count > negative_count + neutral_count:
        overall_sentiment = "positive"
    elif negative_count > positive_count + neutral_count:
        overall_sentiment = "negative"

    return {
        "symbol": symbol or "crypto",
        "overall_sentiment": overall_sentiment,
        "news_count": len(simulated_news),
        "sentiment_breakdown": {
            "positive": positive_count,
            "negative": negative_count,
            "neutral": neutral_count,
        },
        "news": simulated_news,
        "source": "Simulated",
        "note": "Using simulated data. Configure CRYPTOCOMPARE_API_KEY for real data.",
    }


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

    # 恐惧贪婪指数 (-50 to +50)
    if "value" in fng_data:
        fng_score = (fng_data["value"] - 50)
        scores.append(fng_score)
        weights.append(0.3)

    # 社交媒体情绪 (-100 to +100)
    if "sentiment_score" in social_data:
        scores.append(social_data["sentiment_score"])
        weights.append(0.4)

    # 新闻情绪 (-100 to +100)
    news_sentiment_map = {"positive": 50, "neutral": 0, "negative": -50}
    if "overall_sentiment" in news_data:
        news_score = news_sentiment_map.get(news_data["overall_sentiment"], 0)
        scores.append(news_score)
        weights.append(0.3)

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
        "components": {
            "fear_greed_index": fng_data,
            "social_sentiment": social_data,
            "news_sentiment": news_data,
        },
    }


async def get_trending_symbols() -> dict:
    """
    获取热门交易对（模拟）

    Returns:
        热门交易对列表
    """
    # 模拟热门交易对数据
    # 实际应用中应该接入真实的数据源

    trending = [
        {"symbol": "BTCUSDT", "volume_change": "+25%", "mentions": 5000},
        {"symbol": "ETHUSDT", "volume_change": "+18%", "mentions": 3500},
        {"symbol": "SOLUSDT", "volume_change": "+45%", "mentions": 2800},
        {"symbol": "XRPUSDT", "volume_change": "+12%", "mentions": 1500},
        {"symbol": "DOGEUSDT", "volume_change": "+8%", "mentions": 2200},
    ]

    return {
        "trending": trending,
        "note": "This is simulated data. In production, integrate with real data sources.",
    }
