import time
from pathlib import Path

import pytest

from vibe_trading.config import settings as settings_module
from vibe_trading.config.binance_config import BinanceEnvironment
from vibe_trading.agents.agent_factory import ToolContext
from vibe_trading.agents.agent_tools import SubmitTradeOrderParams, get_execution_tools, get_tools_for_agent
from vibe_trading.data_sources.binance_client import (
    BinanceConfig,
    BinanceRestClient,
    OrderSide,
    OrderType,
    Position,
    PositionSide,
)
from vibe_trading.execution.order_executor import PaperOrderExecutor
from vibe_trading.execution.order_executor import TradingMode, create_executor
from vibe_trading.execution.position_manager import PositionManager
from vibe_trading.web.journal_storage import DecisionJournalStorage


@pytest.mark.asyncio
async def test_paper_executor_opens_and_closes_long_position():
    executor = PaperOrderExecutor(initial_balance=10_000)
    executor.update_price("BTCUSDT", 50_000)

    opened = await executor.place_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.01,
        position_side=PositionSide.LONG,
    )
    assert opened.status == "FILLED"
    assert opened.filled_price == 50_000

    positions = await executor.get_positions()
    assert len(positions) == 1
    assert positions[0].position_amount == pytest.approx(0.01)
    assert positions[0].notional == pytest.approx(500)

    await executor.place_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=0.01,
        position_side=PositionSide.LONG,
    )
    assert await executor.get_positions() == []


@pytest.mark.asyncio
async def test_position_manager_closes_with_order_type_enum():
    class RecordingExecutor(PaperOrderExecutor):
        def __init__(self):
            super().__init__()
            self.last_order_type = None

        async def place_order(self, *args, **kwargs):
            self.last_order_type = kwargs["order_type"]
            return await super().place_order(*args, **kwargs)

    executor = RecordingExecutor()
    manager = PositionManager(executor)
    manager._positions["BTCUSDT_LONG"] = Position(
        symbol="BTCUSDT",
        position_amount=0.01,
        entry_price=50_000,
        mark_price=50_000,
        unrealized_profit=0,
        liquidation_price=0,
        leverage=5,
        position_side=PositionSide.LONG,
        notional=500,
    )

    assert await manager.close_position("BTCUSDT", PositionSide.LONG)
    assert executor.last_order_type == OrderType.MARKET


def test_signed_request_uses_epoch_milliseconds_and_encoded_signature(monkeypatch):
    config = BinanceConfig(
        environment=BinanceEnvironment.TESTNET,
        api_key="key",
        api_secret="secret",
    )
    client = BinanceRestClient(config)

    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.123)
    params = client._sign({"symbol": "BTCUSDT", "timestamp": int(time.time() * 1000)})

    assert params["timestamp"] == 1_700_000_000_123
    assert len(params["signature"]) == 64
    assert params["signature"].isalnum()


@pytest.mark.asyncio
async def test_limit_order_payload_includes_time_in_force(monkeypatch):
    config = BinanceConfig(
        environment=BinanceEnvironment.TESTNET,
        api_key="key",
        api_secret="secret",
    )
    client = BinanceRestClient(config)
    captured = {}

    async def fake_request(method, endpoint, signed=False, **kwargs):
        captured.update({"method": method, "endpoint": endpoint, "signed": signed, **kwargs})
        return {
            "symbol": "BTCUSDT",
            "orderId": 123,
            "clientOrderId": "abc",
            "side": "BUY",
            "type": "LIMIT",
            "positionSide": "LONG",
            "origQty": "0.01",
            "price": "50000",
            "stopPrice": "0",
            "status": "NEW",
            "executedQty": "0",
            "cumQty": "0",
        }

    monkeypatch.setattr(client, "_request", fake_request)
    order = await client.place_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.01,
        price=50_000,
        position_side=PositionSide.LONG,
    )

    assert order.order_id == 123
    assert captured["method"] == "POST"
    assert captured["endpoint"] == "/fapi/v1/order"
    assert captured["signed"] is True
    assert captured["params"]["timeInForce"] == "GTC"


def test_settings_expose_binance_credentials(monkeypatch):
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    monkeypatch.setenv("BINANCE_API_KEY", "live-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "live-secret")
    settings_module.set_settings(None)

    settings = settings_module.get_settings()

    assert settings.binance_testnet_api_key == "test-key"
    assert settings.binance_testnet_api_secret == "test-secret"
    assert settings.binance_api_key == "live-key"
    assert settings.binance_api_secret == "live-secret"


def test_live_executor_requires_mainnet_credentials(monkeypatch):
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    settings_module.set_settings(None)

    with pytest.raises(ValueError, match="BINANCE_API_KEY"):
        create_executor(TradingMode.LIVE, dry_run=True)


def test_testnet_executor_uses_testnet_credentials(monkeypatch):
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    settings_module.set_settings(None)

    executor = create_executor(TradingMode.TESTNET)

    assert executor._client.config.is_testnet
    assert executor._client.config.api_key == "test-key"


def test_execution_tool_is_not_in_general_portfolio_toolset():
    tool_names = {tool.name for tool in get_tools_for_agent("portfolio_manager")}
    assert "submit_trade_order" not in tool_names


@pytest.mark.asyncio
async def test_submit_trade_order_tool_uses_bound_executor():
    executor = PaperOrderExecutor(initial_balance=10_000)
    executor.update_price("BTCUSDT", 50_000)
    context = ToolContext(symbol="BTCUSDT", interval="30m", executor=executor)
    tools = get_execution_tools(context)

    submit_tool = tools[0]
    result = await submit_tool.execute(
        "test-call",
        SubmitTradeOrderParams(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.01,
            position_side="LONG",
            rationale="test approved by portfolio manager",
        ),
        None,
        None,
    )

    assert result.details["status"] == "FILLED"
    assert result.details["symbol"] == "BTCUSDT"
    assert result.details["side"] == "BUY"
    positions = await executor.get_positions()
    assert len(positions) == 1
    assert positions[0].position_amount == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_journal_persists_execution_records(tmp_path: Path):
    db_path = tmp_path / "journal.db"
    storage = DecisionJournalStorage(f"sqlite+aiosqlite:///{db_path}")
    await storage.init()

    await storage.upsert_bar(
        symbol="BTCUSDT",
        interval="30m",
        open_time_ms=1_700_000_000_000,
        bar_time="2026-04-28T10:00:00",
        update={"kline": {"close": 50_000}},
    )
    await storage.upsert_bar(
        symbol="BTCUSDT",
        interval="30m",
        open_time_ms=1_700_000_000_000,
        bar_time="2026-04-28T10:00:00",
        update={
            "execution": {
                "agent": "Portfolio Manager",
                "tool_name": "submit_trade_order",
                "result": {"status": "FILLED", "symbol": "BTCUSDT"},
            }
        },
    )

    bar = await storage.get_bar(symbol="BTCUSDT", interval="30m", open_time_ms=1_700_000_000_000)
    assert bar is not None
    assert len(bar.executions) == 1
    assert bar.executions[0]["tool_name"] == "submit_trade_order"
    assert bar.executions[0]["result"]["status"] == "FILLED"
