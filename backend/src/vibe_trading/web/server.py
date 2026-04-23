"""
Vibe Trading Web Server

提供实时监控和可视化界面。
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from pi_logger import get_logger
from vibe_trading.data_sources.kline_storage import KlineStorage, KlineQuery
from vibe_trading.data_sources.technical_indicators import TechnicalIndicators

app = FastAPI(title="Vibe Trading Monitor")

# Add CORS middleware - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局存储和指标计算器
kline_storage = KlineStorage()
technical_indicators = TechnicalIndicators()


class ConnectionState:
    """WebSocket 连接状态管理"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.current_kline: Optional[dict] = None
        self.klines: List[dict] = []
        self.decisions: List[dict] = []
        self.logs: List[dict] = []
        self.phase_status: dict = {}
        self.agent_reports: dict = {}
        self.indicators: dict = {}  # 技术指标数据

    async def broadcast(self, message: dict):
        """广播消息给所有连接"""
        if self.active_connections:
            await asyncio.gather(
                *[conn.send_text(json.dumps(message)) for conn in self.active_connections],
                return_exceptions=True
            )

    async def send_update(self, event_type: str, data: dict):
        """发送更新"""
        await self.broadcast({
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        })


state = ConnectionState()


async def load_historical_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 100):
    """加载历史K线数据"""
    logger = get_logger("webserver")
    try:
        # 初始化存储
        await kline_storage.init()

        # 查询历史K线
        query = KlineQuery(symbol=symbol, interval=interval, limit=limit)
        klines = await kline_storage.query_klines(query)

        if not klines:
            logger.warning(f"No historical klines found for {symbol}")
            return

        # 转换为字典格式并添加到状态
        for kline in klines:
            kline_dict = {
                "time": datetime.fromtimestamp(kline.open_time / 1000).isoformat(),
                "open": kline.open,
                "high": kline.high,
                "low": kline.low,
                "close": kline.close,
                "volume": kline.volume,
            }
            state.klines.append(kline_dict)

        logger.info(f"Loaded {len(klines)} historical klines")

        # 计算技术指标
        await calculate_indicators()

    except Exception as e:
        logger.error(f"Failed to load historical klines: {e}", exc_info=True)
    finally:
        await kline_storage.close()


async def calculate_indicators():
    """计算技术指标"""
    if len(state.klines) < 50:
        return

    logger = get_logger("webserver")

    try:
        # 准备数据
        opens = [k["open"] for k in state.klines]
        highs = [k["high"] for k in state.klines]
        lows = [k["low"] for k in state.klines]
        closes = [k["close"] for k in state.klines]
        volumes = [k["volume"] for k in state.klines]

        # 加载到技术指标计算器
        technical_indicators.load_data(opens, highs, lows, closes, volumes)

        # 计算所有指标
        df = technical_indicators.calculate_all()

        # 辅助函数：安全转换值为JSON可序列化的格式
        def safe_to_list(series):
            result = []
            for val in series:
                # 使用pd.isna来检测NaN
                import pandas as pd
                if pd.isna(val):
                    result.append(None)
                else:
                    result.append(float(val) if val is not None else None)
            return result

        # 提取指标数据
        state.indicators = {
            "rsi": safe_to_list(df["rsi"]),
            "macd": safe_to_list(df["macd"]),
            "macd_signal": safe_to_list(df["macd_signal"]),
            "macd_hist": safe_to_list(df["macd_hist"]),
            "sma_20": safe_to_list(df["sma_20"]),
            "sma_50": safe_to_list(df["sma_50"]),
            "ema_12": safe_to_list(df["ema_12"]),
            "ema_26": safe_to_list(df["ema_26"]),
            "bb_upper": safe_to_list(df["bb_upper"]),
            "bb_middle": safe_to_list(df["bb_middle"]),
            "bb_lower": safe_to_list(df["bb_lower"]),
            "atr": safe_to_list(df["atr"]),
        }

        logger.info(f"Calculated technical indicators for {len(state.klines)} klines")

    except Exception as e:
        logger.error(f"Failed to calculate indicators: {e}", exc_info=True)


# =============================================================================
# WebSocket 端点
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 连接端点"""
    logger = get_logger("webserver")
    await websocket.accept()
    state.active_connections.append(websocket)
    logger.info(f"WebSocket connected. Total clients: {len(state.active_connections)}")

    try:
        # 小延迟确保客户端准备好接收数据
        await asyncio.sleep(0.1)

        # 如果没有K线数据，加载历史数据
        if not state.klines:
            await load_historical_klines()

        # 发送初始状态
        await websocket.send_text(json.dumps({
            "type": "init",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "klines": state.klines,
                "indicators": state.indicators,  # 发送技术指标数据
                "decisions": state.decisions,
                "logs": state.logs[-100:],  # 最近100条
                "phase_status": state.phase_status,
                "agent_reports": state.agent_reports,
            }
        }))

        # 保持连接活跃，等待客户端消息
        while True:
            try:
                # 接收客户端消息
                data = await websocket.receive_text()
                
                # 处理心跳
                if data == "ping":
                    await websocket.send_text("pong")
                    logger.debug("Received ping, sent pong")
                elif data == "pong":
                    logger.debug("Received pong")
                    
            except asyncio.TimeoutError:
                # 超时错误 - 忽略，让连接保持
                logger.warning(f"Message timeout, keeping connection alive")
                continue
                    
            except Exception as e:
                logger.error(f"Message receive error: {e}")
                break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        if websocket in state.active_connections:
            state.active_connections.remove(websocket)
            logger.info(f"WebSocket removed. Total clients: {len(state.active_connections)}")


# =============================================================================
# REST API 端点
# =============================================================================

class KlineData(BaseModel):
    """K线数据"""
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class DecisionData(BaseModel):
    """决策数据"""
    index: int
    time: str
    close: float
    decision: str
    rationale: str


@app.get("/api/status")
async def get_status():
    """获取当前状态"""
    return {
        "connected_clients": len(state.active_connections),
        "total_klines": len(state.klines),
        "total_decisions": len(state.decisions),
        "current_phase": state.phase_status.get("current"),
    }


@app.get("/api/klines")
async def get_klines():
    """获取所有 K线数据"""
    return {"klines": state.klines}


@app.get("/api/decisions")
async def get_decisions():
    """获取所有决策"""
    return {"decisions": state.decisions}


@app.get("/api/logs")
async def get_logs():
    """获取日志"""
    return {"logs": state.logs[-200:]}


@app.post("/api/kline")
async def add_kline(kline: KlineData):
    """添加 K线数据"""
    kline_dict = kline.model_dump()
    state.klines.append(kline_dict)
    state.current_kline = kline_dict

    # 重新计算技术指标
    await calculate_indicators()

    await state.send_update("kline", kline_dict)
    return {"success": True}


@app.post("/api/decision")
async def add_decision(decision: DecisionData):
    """添加决策"""
    decision_dict = decision.model_dump()
    state.decisions.append(decision_dict)
    await state.send_update("decision", decision_dict)
    return {"success": True}


@app.post("/api/log")
async def add_log(log_data: dict):
    """添加日志"""
    log_entry = {
        "timestamp": log_data.get("timestamp", datetime.now().isoformat()),
        "level": log_data.get("level", "info"),
        "tag": log_data.get("tag", ""),
        "message": log_data.get("message", ""),
    }
    state.logs.append(log_entry)
    # 限制日志数量
    if len(state.logs) > 500:
        state.logs = state.logs[-500:]
    await state.send_update("log", log_entry)
    return {"success": True}


@app.post("/api/phase")
async def update_phase(phase_data: dict):
    """更新阶段状态"""
    phase = phase_data.get("phase", "")
    status = phase_data.get("status", "running")  # running, completed, error
    duration = phase_data.get("duration", None)

    state.phase_status["current"] = phase
    state.phase_status[phase] = {"status": status, "duration": duration}

    await state.send_update("phase", {
        "phase": phase,
        "status": status,
        "duration": duration
    })
    return {"success": True}


@app.post("/api/report")
async def add_report(report_data: dict):
    """添加 Agent 报告"""
    agent = report_data.get("agent", "")
    content = report_data.get("content", "")
    phase = report_data.get("phase", "")

    if phase not in state.agent_reports:
        state.agent_reports[phase] = {}

    state.agent_reports[phase][agent] = content

    await state.send_update("report", {
        "agent": agent,
        "phase": phase,
        "content": content
    })
    return {"success": True}


@app.post("/api/reset")
async def reset_data():
    """重置所有数据"""
    state.klines = []
    state.decisions = []
    state.logs = []
    state.phase_status = {}
    state.agent_reports = {}
    state.current_kline = None

    await state.send_update("reset", {})
    return {"success": True}


@app.post("/api/decision_tree")
async def update_decision_tree(tree_data: dict):
    """更新决策树"""
    await state.send_update("decision_tree", tree_data)
    return {"success": True}


# =============================================================================
# 辅助函数 - 用于 test_historical.py 调用
# =============================================================================

_api_base_url = "http://localhost:8000"


async def send_kline(kline: dict) -> None:
    """发送 K线数据"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(f"{_api_base_url}/api/kline", json=kline)
    except Exception:
        pass  # 服务器未启动时忽略错误


async def send_decision(decision: dict) -> None:
    """发送决策数据"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(f"{_api_base_url}/api/decision", json=decision)
    except Exception:
        pass


async def send_log(level: str, tag: str, message: str) -> None:
    """发送日志"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(f"{_api_base_url}/api/log", json={
                "level": level,
                "tag": tag,
                "message": message
            })
    except Exception:
        pass


async def send_phase(phase: str, status: str = "running", duration: float = None) -> None:
    """更新阶段状态"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(f"{_api_base_url}/api/phase", json={
                "phase": phase,
                "status": status,
                "duration": duration
            })
    except Exception:
        pass


async def send_report(agent: str, content: str, phase: str = "") -> None:
    """发送 Agent 报告"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(f"{_api_base_url}/api/report", json={
                "agent": agent,
                "content": content,
                "phase": phase
            })
    except Exception:
        pass


async def send_decision_tree(tree_data: dict) -> None:
    """发送决策树数据"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(f"{_api_base_url}/api/decision_tree", json=tree_data)
    except Exception:
        pass


def run_server(port: int = 8000):
    """运行服务器"""
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_server()
