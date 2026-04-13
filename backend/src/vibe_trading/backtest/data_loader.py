"""
回测数据加载器

支持从Binance API获取历史K线数据，并缓存到本地存储。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

from pi_logger import get_logger

from vibe_trading.data_sources.binance_client import BinanceClient, BinanceConfig, Kline
from vibe_trading.data_sources.kline_storage import KlineStorage, KlineQuery

logger = get_logger(__name__)


class DataSource(str, Enum):
    """数据源类型"""
    BINANCE_API = "binance_api"
    LOCAL_STORAGE = "local_storage"
    HYBRID = "hybrid"  # 优先本地，不足时从API补充


@dataclass
class DataLoadResult:
    """数据加载结果"""
    klines: List[Kline]
    source: DataSource
    cached_count: int  # 来自缓存的数量
    fetched_count: int  # 从API获取的数量
    total_count: int
    time_range: tuple[datetime, datetime]
    has_gaps: bool  # 是否有数据缺口

    # Lookback 相关字段
    lookback_start_time: Optional[datetime] = None  # 实际数据加载的开始时间（包含lookback）
    backtest_start_time: Optional[datetime] = None  # 回测开始的实际时间


class BacktestDataLoader:
    """
    回测数据加载器

    支持从多种数据源加载历史K线数据：
    1. 本地SQLite存储（快速）
    2. Binance API（完整历史数据）
    3. 混合模式（优先本地，不足时从API补充）
    """

    def __init__(
        self,
        default_source: DataSource = DataSource.HYBRID,
        storage: Optional[KlineStorage] = None,
        binance_client: Optional[BinanceClient] = None,
    ):
        """
        初始化数据加载器

        Args:
            default_source: 默认数据源
            storage: K线存储实例（如果为None则创建新实例）
            binance_client: Binance客户端（如果为None则创建新实例）
        """
        self.default_source = default_source

        # 确保storage已初始化
        if storage is None:
            from vibe_trading.data_sources.kline_storage import KlineStorage
            self.storage = KlineStorage()
        else:
            self.storage = storage

        self.binance_client = binance_client or self._create_binance_client()

    def _create_binance_client(self) -> BinanceClient:
        """创建Binance客户端"""
        config = BinanceConfig(
            api_key="",  # 历史数据下载不需要API key
            api_secret="",
            environment="spot",  # 使用现货数据（合约数据需要auth）
        )
        return BinanceClient(config)

    async def load_klines(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        interval: str = "30m",
        source: Optional[DataSource] = None,
        fill_gaps: bool = True,
    ) -> DataLoadResult:
        """
        加载K线数据

        Args:
            symbol: 交易品种
            start_time: 开始时间
            end_time: 结束时间
            interval: K线间隔
            source: 数据源（如果为None则使用default_source）
            fill_gaps: 是否填充数据缺口

        Returns:
            DataLoadResult: 加载结果
        """
        source = source or self.default_source
        logger.info(
            f"加载K线数据: {symbol} {interval} "
            f"{start_time.strftime('%Y-%m-%d')} ~ {end_time.strftime('%Y-%m-%d')}"
        )

        if source == DataSource.LOCAL_STORAGE:
            return await self._load_from_storage(symbol, start_time, end_time, interval)
        elif source == DataSource.BINANCE_API:
            return await self._load_from_binance(symbol, start_time, end_time, interval)
        else:  # HYBRID
            return await self._load_hybrid(symbol, start_time, end_time, interval, fill_gaps)

    async def _load_from_storage(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        interval: str,
    ) -> DataLoadResult:
        """从本地存储加载"""
        query = KlineQuery(
            symbol=symbol,
            interval=interval,
            start_time=int(start_time.timestamp() * 1000),
            end_time=int(end_time.timestamp() * 1000),
        )

        klines = await self.storage.query_klines(query)
        total_count = len(klines)

        logger.info(f"从本地存储加载了 {total_count} 条K线数据")

        # 检查是否有数据缺口
        has_gaps = self._check_data_gaps(klines, start_time, end_time, interval)

        return DataLoadResult(
            klines=klines,
            source=DataSource.LOCAL_STORAGE,
            cached_count=total_count,
            fetched_count=0,
            total_count=total_count,
            time_range=(start_time, end_time),
            has_gaps=has_gaps,
        )

    async def _load_from_binance(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        interval: str,
    ) -> DataLoadResult:
        """从Binance API加载"""
        try:
            from vibe_trading.data_sources.binance_client import KlineInterval

            # 将interval字符串转换为KlineInterval枚举
            interval_enum = KlineInterval(interval)

            klines = await self.binance_client.rest.get_klines(
                symbol=symbol,
                interval=interval_enum,
                limit=1000,
                start_time=int(start_time.timestamp() * 1000),
                end_time=int(end_time.timestamp() * 1000),
            )

            # 转换API响应为Kline对象
            kline_objects = []
            for kline_data in klines:
                # 使用 from_rest 方法正确转换类型
                kline = Kline.from_rest(kline_data)
                # from_rest 不设置 symbol 和 interval，需要手动设置
                kline.symbol = symbol
                kline.interval = interval
                kline_objects.append(kline)

            # 存储到本地
            if kline_objects:
                await self.storage.store_klines(kline_objects)
                logger.info(f"从Binance加载了 {len(kline_objects)} 条K线数据并已存储")

            return DataLoadResult(
                klines=kline_objects,
                source=DataSource.BINANCE_API,
                cached_count=0,
                fetched_count=len(kline_objects),
                total_count=len(kline_objects),
                time_range=(start_time, end_time),
                has_gaps=False,
            )

        except Exception as e:
            logger.error(f"从Binance加载数据失败: {e}")
            raise

    async def _load_hybrid(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        interval: str,
        fill_gaps: bool,
    ) -> DataLoadResult:
        """混合模式加载"""
        # 1. 先尝试从本地加载
        local_result = await self._load_from_storage(symbol, start_time, end_time, interval)

        # 2. 检查数据是否完整
        if not local_result.has_gaps and local_result.total_count > 0:
            logger.info("本地数据完整，无需从API补充")
            return local_result

        # 3. 找出数据缺口并补充
        if fill_gaps:
            gaps = self._identify_data_gaps(
                local_result.klines,
                start_time,
                end_time,
                interval
            )

            fetched_klines = []
            for gap_start, gap_end in gaps:
                logger.info(f"补充数据缺口: {gap_start} ~ {gap_end}")

                # 使用正确的API方法
                from vibe_trading.data_sources.binance_client import KlineInterval

                interval_enum = KlineInterval(interval)
                gap_klines_data = await self.binance_client.rest.get_klines(
                    symbol=symbol,
                    interval=interval_enum,
                    limit=1000,
                    start_time=int(gap_start.timestamp() * 1000),
                    end_time=int(gap_end.timestamp() * 1000),
                )

                # 转换为Kline对象
                for kline_data in gap_klines_data:
                    kline = Kline.from_rest(kline_data)
                    kline.symbol = symbol
                    kline.interval = interval
                    fetched_klines.append(kline)

            # 存储补充的数据
            if fetched_klines:
                await self.storage.store_klines(fetched_klines)

            # 合并本地和新增数据
            all_klines = local_result.klines + fetched_klines
            # 去重并排序
            all_klines = self._deduplicate_klines(all_klines)
            all_klines.sort(key=lambda k: k.open_time)

            return DataLoadResult(
                klines=all_klines,
                source=DataSource.HYBRID,
                cached_count=local_result.total_count,
                fetched_count=len(fetched_klines),
                total_count=len(all_klines),
                time_range=(start_time, end_time),
                has_gaps=False,
            )

        return local_result

    def _check_data_gaps(
        self,
        klines: List[Kline],
        start_time: datetime,
        end_time: datetime,
        interval: str,
    ) -> bool:
        """检查数据是否有缺口"""
        if not klines:
            return True

        # 解析interval
        interval_minutes = self._parse_interval_to_minutes(interval)

        # 期望的数据点数量
        expected_count = int((end_time - start_time).total_seconds() / 60 / interval_minutes) + 1

        # 实际数量
        actual_count = len(klines)

        # 允许5%的误差
        return actual_count < expected_count * 0.95

    def _identify_data_gaps(
        self,
        klines: List[Kline],
        start_time: datetime,
        end_time: datetime,
        interval: str,
    ) -> List[tuple[datetime, datetime]]:
        """识别数据缺口"""
        if not klines:
            return [(start_time, end_time)]

        interval_minutes = self._parse_interval_to_minutes(interval)
        gaps = []

        # 检查开始时间
        first_kline_time = datetime.fromtimestamp(klines[0].open_time / 1000)
        if first_kline_time > start_time:
            gaps.append((start_time, first_kline_time))

        # 检查中间缺口
        for i in range(len(klines) - 1):
            current_time = datetime.fromtimestamp(klines[i].open_time / 1000)
            next_time = datetime.fromtimestamp(klines[i + 1].open_time / 1000)
            expected_next_time = current_time + timedelta(minutes=interval_minutes)

            if next_time > expected_next_time:
                gaps.append((expected_next_time, next_time))

        # 检查结束时间
        last_kline_time = datetime.fromtimestamp(klines[-1].open_time / 1000)
        if last_kline_time < end_time:
            gaps.append((last_kline_time, end_time))

        return gaps

    def _deduplicate_klines(self, klines: List[Kline]) -> List[Kline]:
        """去重K线数据"""
        seen = set()
        unique_klines = []

        for kline in klines:
            key = (kline.symbol, kline.open_time)
            if key not in seen:
                seen.add(key)
                unique_klines.append(kline)

        return unique_klines

    def _parse_interval_to_minutes(self, interval: str) -> int:
        """解析interval字符串为分钟数"""
        interval = interval.lower()
        if interval.endswith('m'):
            return int(interval[:-1])
        elif interval.endswith('h'):
            return int(interval[:-1]) * 60
        elif interval.endswith('d'):
            return int(interval[:-1]) * 60 * 24
        else:
            # 默认30分钟
            return 30

    async def load_with_lookback(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        interval: str,
        lookback_periods: int,
        source: Optional[DataSource] = None,
        fill_gaps: bool = True,
    ) -> DataLoadResult:
        """
        加载包含lookback数据的K线

        Args:
            symbol: 交易品种
            start_time: 回测开始时间
            end_time: 回测结束时间
            interval: K线间隔
            lookback_periods: 需要额外加载的历史周期数
            source: 数据源（如果为None则使用default_source）
            fill_gaps: 是否填充数据缺口

        Returns:
            包含lookback数据的加载结果
        """
        # 计算需要额外加载的时间增量
        interval_minutes = self._parse_interval_to_minutes(interval)
        lookback_timedelta = timedelta(minutes=interval_minutes * lookback_periods)

        # 计算实际数据加载的开始时间
        extra_start_time = start_time - lookback_timedelta

        logger.info(
            f"加载K线数据（含lookback）: {symbol} {interval}\n"
            f"  回测期间: {start_time} ~ {end_time}\n"
            f"  数据加载: {extra_start_time} ~ {end_time}\n"
            f"  Lookback: {lookback_periods}周期 ({lookback_timedelta})"
        )

        # 加载完整数据
        result = await self.load_klines(
            symbol=symbol,
            start_time=extra_start_time,
            end_time=end_time,
            interval=interval,
            source=source,
            fill_gaps=fill_gaps,
        )

        # 标记lookback期间
        result.lookback_start_time = extra_start_time
        result.backtest_start_time = start_time

        return result


# ============================================================================
# 便捷函数
# ============================================================================

async def load_backtest_data(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    interval: str = "30m",
) -> List[Kline]:
    """
    便捷函数：加载回测数据

    Args:
        symbol: 交易品种
        start_time: 开始时间
        end_time: 结束时间
        interval: K线间隔

    Returns:
        K线数据列表
    """
    loader = BacktestDataLoader()
    result = await loader.load_klines(symbol, start_time, end_time, interval)
    return result.klines


# ============================================================================
# 导入修复
# ============================================================================

