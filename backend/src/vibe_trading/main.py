"""
Vibe Trading - 多Agent协作量化交易系统

主入口文件，负责启动交易系统。
"""
import asyncio
import logging
import signal
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from vibe_trading.config.settings import get_settings
from vibe_trading.config.binance_config import BinanceConfig
from vibe_trading.config.agent_config import AgentTeamConfig
from vibe_trading.data_sources.binance_client import (
    BinanceClient,
    KlineInterval,
)
from vibe_trading.data_sources.kline_storage import KlineStorage
from vibe_trading.memory.memory import BM25Memory
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
console = Console()


class VibeTradingApp:
    """Vibe Trading 应用主类"""

    def __init__(self):
        self.settings = get_settings()
        self.binance_config: BinanceConfig | None = None
        self.binance_client: BinanceClient | None = None
        self.storage: KlineStorage | None = None
        self.memory: BM25Memory | None = None
        self.coordinator: TradingCoordinator | None = None
        self._running = False
        self._kline_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """初始化所有组件"""
        console.print(Panel("[bold cyan]初始化 Vibe Trading 系统[/bold cyan]"))

        # 1. 初始化 Binance 配置
        self.binance_config = BinanceConfig.from_env()
        console.print(f"  ✓ Binance 环境: {self.binance_config.environment.value}")

        # 2. 初始化 Binance 客户端
        self.binance_client = BinanceClient(self.binance_config)
        console.print(f"  ✓ Binance 客户端已创建")

        # 3. 初始化数据库
        self.storage = KlineStorage()
        await self.storage.init()
        console.print(f"  ✓ 数据库已初始化")

        # 4. 初始化记忆系统
        if self.settings.enable_memory:
            self.memory = BM25Memory()
            console.print(f"  ✓ 记忆系统已启用")

        # 5. 初始化 Agent 团队配置
        agent_config = AgentTeamConfig()
        enabled_count = sum(
            1 for cfg in agent_config.get_all_configs().values() if cfg.enabled
        )
        console.print(f"  ✓ Agent 团队: {enabled_count} 个角色已启用")

        # 6. 为每个交易对创建协调器
        self.coordinators: list[TradingCoordinator] = []
        for symbol in self.settings.symbols:
            coord = TradingCoordinator(
                symbol=symbol,
                interval=self.settings.interval,
                memory=self.memory,
                agent_config=agent_config,
            )
            await coord.initialize()
            self.coordinators.append(coord)
            console.print(f"  ✓ 协调器已初始化: {symbol}")

        console.print()
        console.print("[green]✅ 系统初始化完成！[/green]")
        console.print()

    async def _on_kline(self, kline) -> None:
        """处理新 K线数据"""
        try:
            # 存储到数据库
            await self.storage.store_kline(kline)

            # 触发对应交易对的协调器
            for coord in self.coordinators:
                if coord.symbol == kline.symbol:
                    await coord.on_new_kline(kline)
                    break

        except Exception as e:
            logger.error(f"处理 K线数据失败: {e}", exc_info=True)

    async def run(self) -> None:
        """运行主循环"""
        self._running = True

        # 设置信号处理
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        console.print(Panel("[bold yellow]开始交易循环[/bold yellow]"))
        console.print(f"  交易模式: {self.settings.trading_mode.value}")
        console.print(f"  交易品种: {', '.join(self.settings.symbols)}")
        console.print(f"  K线周期: {self.settings.interval}")
        console.print()
        console.print("[dim]按 Ctrl+C 停止运行[/dim]")
        console.print()

        # 订阅 K线数据
        for symbol in self.settings.symbols:
            self.binance_client.ws.subscribe_kline(
                symbol=symbol,
                interval=KlineInterval(self.settings.interval),
                callback=self._on_kline,
            )
            logger.info(f"已订阅 {symbol} {self.settings.interval} K线")

        # 启动 WebSocket 监听
        try:
            await self.binance_client.ws.start()
        except Exception as e:
            logger.error(f"WebSocket 错误: {e}")
            await self.stop()

    async def stop(self) -> None:
        """停止系统"""
        if not self._running:
            return

        console.print()
        console.print("[yellow]正在停止系统...[/yellow]")

        self._running = False

        # 断开 WebSocket
        if self.binance_client:
            await self.binance_client.close()

        # 关闭数据库
        if self.storage:
            await self.storage.close()

        console.print("[green]✅ 系统已停止[/green]")

    async def fetch_historical_klines(self) -> None:
        """获取历史 K线数据用于初始化"""
        console.print(Panel("[bold cyan]获取历史 K线 数据[/bold cyan]"))

        for symbol in self.settings.symbols:
            try:
                klines = await self.binance_client.rest.get_klines(
                    symbol=symbol,
                    interval=KlineInterval(self.settings.interval),
                    limit=200,
                )

                # 转换并存储
                from vibe_trading.data_sources.binance_client import Kline
                kline_objects = []
                for k in klines:
                    kline = Kline.from_rest(k)
                    kline.symbol = symbol
                    kline.interval = self.settings.interval
                    kline_objects.append(kline)

                await self.storage.store_klines(kline_objects)
                console.print(f"  ✓ {symbol}: 已加载 {len(kline_objects)} 条历史数据")

            except Exception as e:
                logger.error(f"获取 {symbol} 历史数据失败: {e}")

        console.print()


async def main() -> None:
    """主函数"""
    app = VibeTradingApp()

    try:
        await app.initialize()
        await app.fetch_historical_klines()
        await app.run()
    except KeyboardInterrupt:
        await app.stop()
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        logger.exception("主程序异常")
        await app.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
