"""
LLM调用优化器

通过响应缓存和决策模拟降低回测时的LLM调用成本。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pi_logger import get_logger

from vibe_trading.backtest.models import BacktestDecision, LLMMode
from vibe_trading.coordinator.signal_processor import TradingSignal
from vibe_trading.data_sources.binance_client import Kline

logger = get_logger(__name__)


class LLMResponseCache:
    """
    LLM响应缓存

    基于输入特征哈希缓存决策结果，大幅降低回测成本。
    """

    def __init__(self, cache_path: str = "./llm_cache.db"):
        """
        初始化缓存

        Args:
            cache_path: 缓存数据库路径
        """
        self.cache_path = cache_path
        self._init_database()

    def _init_database(self):
        """初始化缓存数据库"""
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                price REAL NOT NULL,
                indicators_hash TEXT NOT NULL,
                decision_json TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at INTEGER NOT NULL,
                access_count INTEGER DEFAULT 1,
                last_accessed INTEGER NOT NULL
            )
        """)

        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_symbol_interval
            ON llm_cache(symbol, interval)
        """)

        conn.commit()
        conn.close()

    def generate_cache_key(
        self,
        symbol: str,
        price: float,
        indicators: Dict[str, Any],
        positions: List[Dict],
    ) -> str:
        """
        生成缓存键

        Args:
            symbol: 交易品种
            price: 当前价格
            indicators: 技术指标
            positions: 当前持仓

        Returns:
            缓存键（MD5哈希）
        """
        # 创建特征字符串
        features = {
            "symbol": symbol,
            "price": round(price, 2),  # 价格保留2位小数
            "indicators": {
                k: round(v, 4) if isinstance(v, float) else v
                for k, v in indicators.items()
                if k in ["rsi", "macd", "sma_20", "sma_50", "bollinger_upper", "bollinger_lower"]
            },
            "positions": sorted([
                (p["symbol"], p["side"], round(p["quantity"], 4))
                for p in positions
            ]) if positions else [],
        }

        # 生成哈希
        feature_str = json.dumps(features, sort_keys=True)
        return hashlib.md5(feature_str.encode()).hexdigest()

    async def get(self, cache_key: str) -> Optional[Dict]:
        """获取缓存"""
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT decision_json, signal, confidence
            FROM llm_cache
            WHERE cache_key = ?
        """, (cache_key,))

        row = cursor.fetchone()

        if row:
            # 更新访问统计
            cursor.execute("""
                UPDATE llm_cache
                SET access_count = access_count + 1,
                    last_accessed = ?
                WHERE cache_key = ?
            """, (int(datetime.now().timestamp()), cache_key))
            conn.commit()

            conn.close()
            return {
                "decision_json": row[0],
                "signal": row[1],
                "confidence": row[2],
            }

        conn.close()
        return None

    async def set(
        self,
        cache_key: str,
        symbol: str,
        interval: str,
        price: float,
        indicators_hash: str,
        decision_json: str,
        signal: str,
        confidence: float,
    ) -> None:
        """设置缓存"""
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        now = int(datetime.now().timestamp())

        cursor.execute("""
            INSERT OR REPLACE INTO llm_cache
            (cache_key, symbol, interval, price, indicators_hash,
             decision_json, signal, confidence, created_at,
             access_count, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            cache_key, symbol, interval, price, indicators_hash,
            decision_json, signal, confidence, now, now
        ))

        conn.commit()
        conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM llm_cache")
        total_entries = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(access_count) FROM llm_cache")
        total_accesses = cursor.fetchone()[0] or 0

        conn.close()

        return {
            "total_entries": total_entries,
            "total_accesses": total_accesses,
            "avg_accesses": total_accesses / total_entries if total_entries > 0 else 0,
        }


class LLMSimulator:
    """
    LLM决策模拟器

    基于历史决策的模式匹配模拟新决策，用于快速回测。
    """

    def __init__(self):
        """初始化模拟器"""
        self.decision_history: List[Dict] = []

    def add_decision(
        self,
        price: float,
        indicators: Dict[str, Any],
        signal: TradingSignal,
        confidence: float,
        market_condition: str,
    ) -> None:
        """添加历史决策"""
        self.decision_history.append({
            "price": price,
            "indicators": indicators,
            "signal": signal,
            "confidence": confidence,
            "market_condition": market_condition,
        })

    def find_similar_contexts(
        self,
        current_indicators: Dict[str, Any],
        top_k: int = 5,
    ) -> List[Dict]:
        """
        找到相似的历史决策

        Args:
            current_indicators: 当前技术指标
            top_k: 返回最相似的K个决策

        Returns:
            相似的历史决策列表
        """
        if not self.decision_history:
            return []

        similarities = []

        for hist_decision in self.decision_history:
            similarity = self._calculate_similarity(
                current_indicators,
                hist_decision["indicators"]
            )
            similarities.append((similarity, hist_decision))

        # 按相似度排序，取前K个
        similarities.sort(key=lambda x: x[0], reverse=True)
        return [decision for _, decision in similarities[:top_k]]

    def _calculate_similarity(
        self,
        indicators1: Dict[str, Any],
        indicators2: Dict[str, Any],
    ) -> float:
        """
        计算两个指标集的相似度

        使用简化的欧氏距离。
        """
        # 关键指标
        key_indicators = ["rsi", "macd", "sma_20", "sma_50", "bollinger_upper", "bollinger_lower"]

        distances = []
        for key in key_indicators:
            if key in indicators1 and key in indicators2:
                v1 = indicators1[key]
                v2 = indicators2[key]

                # 归一化距离
                if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                    max_val = max(abs(v1), abs(v2), 1e-8)
                    distance = abs(v1 - v2) / max_val
                    distances.append(distance)

        if not distances:
            return 0.0

        # 转换为相似度（0-1）
        avg_distance = sum(distances) / len(distances)
        similarity = 1.0 - min(avg_distance, 1.0)

        return similarity

    def simulate_decision(
        self,
        current_price: float,
        current_indicators: Dict[str, Any],
        current_positions: List[Dict],
    ) -> Tuple[TradingSignal, float]:
        """
        模拟决策

        Args:
            current_price: 当前价格
            current_indicators: 当前技术指标
            current_positions: 当前持仓

        Returns:
            (信号, 置信度)
        """
        # 1. 找到相似的历史决策
        similar_decisions = self.find_similar_contexts(current_indicators, top_k=5)

        if not similar_decisions:
            # 没有历史数据，返回HOLD
            return TradingSignal.HOLD, 0.5

        # 2. 投票决策
        votes = {TradingSignal.BUY: 0, TradingSignal.SELL: 0, TradingSignal.HOLD: 0}
        confidence_sum = {TradingSignal.BUY: 0.0, TradingSignal.SELL: 0.0, TradingSignal.HOLD: 0.0}

        for decision in similar_decisions:
            signal = decision["signal"]
            votes[signal] += 1
            confidence_sum[signal] += decision["confidence"]

        # 3. 找出得票最多的信号
        max_votes = max(votes.values())
        candidates = [s for s, v in votes.items() if v == max_votes]

        if len(candidates) == 1:
            selected_signal = candidates[0]
            avg_confidence = confidence_sum[selected_signal] / votes[selected_signal]
        else:
            # 票数相同，选择HOLD
            selected_signal = TradingSignal.HOLD
            avg_confidence = 0.5

        # 4. 考虑当前持仓（避免过度交易）
        if current_positions:
            # 如果有持仓，倾向于保持或平仓，不太可能开新仓
            if selected_signal != TradingSignal.HOLD:
                avg_confidence *= 0.8  # 降低置信度

        return selected_signal, avg_confidence


class LLMOptimizer:
    """
    LLM调用优化器

    根据模式选择最优的决策获取方式：
    - REAL: 真实LLM调用
    - CACHED: 使用缓存
    - SIMULATED: 模拟决策
    """

    def __init__(self, mode: LLMMode = LLMMode.CACHED):
        """
        初始化优化器

        Args:
            mode: LLM调用模式
        """
        self.mode = mode
        self.cache = LLMResponseCache()
        self.simulator = LLMSimulator()

        # 统计
        self.total_calls = 0
        self.cache_hits = 0
        self.real_calls = 0

    async def get_decision(
        self,
        coordinator,
        current_price: float,
        account_balance: float,
        current_positions: List[Dict],
        kline: Kline,
    ) -> BacktestDecision:
        """
        获取优化后的决策

        Args:
            coordinator: TradingCoordinator实例
            current_price: 当前价格
            account_balance: 账户余额
            current_positions: 当前持仓列表
            kline: K线数据

        Returns:
            BacktestDecision
        """
        self.total_calls += 1

        # 准备特征用于缓存/模拟
        indicators = self._extract_indicators(coordinator, current_price)
        cache_key = self.cache.generate_cache_key(
            kline.symbol, current_price, indicators, current_positions
        )

        if self.mode == LLMMode.REAL:
            # 真实LLM调用
            return await self._get_real_decision(
                coordinator, current_price, account_balance, current_positions
            )

        elif self.mode == LLMMode.CACHED:
            # 尝试从缓存获取
            cached = await self.cache.get(cache_key)

            if cached:
                self.cache_hits += 1
                return self._build_decision_from_cache(cached, kline)
            else:
                # 缓存未命中，调用真实LLM
                decision = await self._get_real_decision(
                    coordinator, current_price, account_balance, current_positions
                )

                # 存入缓存
                await self._store_decision_to_cache(
                    cache_key, kline, indicators, decision
                )

                return decision

        else:  # SIMULATED
            # 模拟决策
            signal, confidence = self.simulator.simulate_decision(
                current_price, indicators, current_positions
            )

            return self._build_simulated_decision(
                signal, confidence, kline, current_price, account_balance
            )

    async def _get_real_decision(
        self,
        coordinator,
        current_price: float,
        account_balance: float,
        current_positions: List[Dict],
    ) -> BacktestDecision:
        """获取真实LLM决策"""
        self.real_calls += 1

        trading_decision = await coordinator.analyze_and_decide(
            current_price=current_price,
            account_balance=account_balance,
            current_positions=current_positions,
        )

        return BacktestDecision(
            decision_id=trading_decision.timestamp,  # 使用时间戳作为ID
            timestamp=datetime.fromtimestamp(trading_decision.timestamp / 1000),
            current_price=current_price,
            trading_decision=trading_decision,
            processed_signal=getattr(coordinator, '_last_processed_signal', None),
            agent_contributions=getattr(coordinator, '_last_agent_contributions', {}),
            market_condition="unknown",
            signal=getattr(coordinator, '_last_processed_signal', None).signal if hasattr(coordinator, '_last_processed_signal') else TradingSignal.HOLD,
            confidence=getattr(coordinator, '_last_processed_signal', None).confidence if hasattr(coordinator, '_last_processed_signal') else 0.0,
            strength="unknown",
        )

    def _extract_indicators(self, coordinator, current_price: float) -> Dict[str, Any]:
        """提取技术指标"""
        # 尝试从coordinator获取指标
        # 这里简化处理，实际应该从context中获取
        return {
            "price": current_price,
            "rsi": 50.0,
            "macd": 0.0,
            "sma_20": current_price * 0.99,
            "sma_50": current_price * 0.98,
        }

    async def _store_decision_to_cache(
        self,
        cache_key: str,
        kline: Kline,
        indicators: Dict[str, Any],
        decision: BacktestDecision,
    ) -> None:
        """存储决策到缓存"""
        indicators_hash = hashlib.md5(
            json.dumps(indicators, sort_keys=True).encode()
        ).hexdigest()

        await self.cache.set(
            cache_key=cache_key,
            symbol=kline.symbol,
            interval=kline.interval,
            price=decision.current_price,
            indicators_hash=indicators_hash,
            decision_json="",
            signal=decision.signal.value,
            confidence=decision.confidence,
        )

    def _build_decision_from_cache(self, cached: Dict, kline: Kline) -> BacktestDecision:
        """从缓存构建决策"""
        # 简化处理，实际应该解析decision_json
        return BacktestDecision(
            decision_id=f"cached_{int(kline.open_time)}",
            timestamp=datetime.fromtimestamp(kline.open_time / 1000),
            current_price=kline.close,
            trading_decision=None,
            processed_signal=None,
            agent_contributions={},
            market_condition="cached",
            signal=TradingSignal(cached["signal"]),
            confidence=cached["confidence"],
            strength="moderate",
        )

    def _build_simulated_decision(
        self,
        signal: TradingSignal,
        confidence: float,
        kline: Kline,
        current_price: float,
        account_balance: float,
    ) -> BacktestDecision:
        """构建模拟决策"""
        return BacktestDecision(
            decision_id=f"sim_{int(kline.open_time)}",
            timestamp=datetime.fromtimestamp(kline.open_time / 1000),
            current_price=current_price,
            trading_decision=None,
            processed_signal=None,
            agent_contributions={},
            market_condition="simulated",
            signal=signal,
            confidence=confidence,
            strength="moderate",
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_calls": self.total_calls,
            "cache_hits": self.cache_hits,
            "real_calls": self.real_calls,
            "cache_hit_rate": self.cache_hits / self.total_calls if self.total_calls > 0 else 0,
        }
