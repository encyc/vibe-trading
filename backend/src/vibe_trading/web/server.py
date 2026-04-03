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
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Vibe Trading Monitor")

# 静态文件目录 - 从 server.py (backend/src/vibe_trading/web/) 往上 4 级到项目根
static_dir = Path(__file__).parent.parent.parent.parent.parent / "frontend"
static_dir.mkdir(exist_ok=True)


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


# =============================================================================
# WebSocket 端点
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 连接端点"""
    await websocket.accept()
    state.active_connections.append(websocket)

    # 发送初始状态
    await websocket.send_text(json.dumps({
        "type": "init",
        "timestamp": datetime.now().isoformat(),
        "data": {
            "klines": state.klines,
            "decisions": state.decisions,
            "logs": state.logs[-100:],  # 最近100条
            "phase_status": state.phase_status,
            "agent_reports": state.agent_reports,
        }
    }))

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.active_connections.remove(websocket)


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


@app.get("/")
async def get_html():
    """获取 HTML 页面"""
    html_file = static_dir / "index.html"
    if html_file.exists():
        return HTMLResponse(html_file.read_text())
    return HTMLResponse("<h1>Vibe Trading Monitor</h1><p>Frontend not found. Run: python build_frontend.py</p>")


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
