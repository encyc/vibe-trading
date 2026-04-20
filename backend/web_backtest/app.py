"""
回测系统Web服务

提供回测任务管理、实时进度监控、结果展示等功能。
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# 添加backend/src到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pi_logger import get_logger

logger = get_logger(__name__)

# =============================================================================
# 数据模型
# =============================================================================


class BacktestTask(BaseModel):
    """回测任务"""
    task_id: str
    symbol: str
    interval: str
    start_time: str
    end_time: str
    llm_mode: str
    status: str  # pending, running, completed, failed
    current_kline: int = 0
    total_klines: int = 0
    current_equity: float = 0.0
    total_trades: int = 0
    llm_calls: int = 0
    llm_cache_hits: int = 0
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class BacktestCreateRequest(BaseModel):
    """创建回测请求"""
    symbol: str
    interval: str
    start_time: str  # YYYY-MM-DD
    end_time: str  # YYYY-MM-DD
    initial_balance: float = 10000.0
    llm_mode: str = "simulated"  # simulated, cached, real


class ProgressUpdate(BaseModel):
    """进度更新"""
    task_id: str
    status: str
    current_kline: int
    total_klines: int
    progress_percentage: float
    current_equity: float
    total_trades: int
    llm_calls: int
    llm_cache_hits: int
    cache_hit_rate: float
    estimated_remaining_seconds: Optional[float] = None


# =============================================================================
# 全局状态管理
# =============================================================================


class BacktestWebManager:
    """回测Web管理器"""

    def __init__(self):
        # 存储所有回测任务
        self.tasks: Dict[str, Dict] = {}

        # WebSocket连接
        self.active_connections: List[WebSocket] = []

        # 进度追踪器引用
        self.progress_trackers: Dict[str, object] = {}

    def add_task(self, task: BacktestTask) -> None:
        """添加任务"""
        self.tasks[task.task_id] = task.dict()
        logger.info(f"添加回测任务: {task.task_id}")

    def update_task(self, task_id: str, updates: Dict) -> None:
        """更新任务"""
        if task_id in self.tasks:
            self.tasks[task_id].update(updates)
            logger.info(f"更新任务: {task_id} - {updates}")

    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务"""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[Dict]:
        """获取所有任务"""
        return list(self.tasks.values())

    async def broadcast_progress(self, update: ProgressUpdate) -> None:
        """广播进度更新"""
        import json

        message = json.dumps(update.dict())
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                disconnected.append(connection)

        # �除断开的连接
        for connection in disconnected:
            self.active_connections.remove(connection)


# 全局管理器
manager = BacktestWebManager()

# =============================================================================
# FastAPI应用
# =============================================================================

app = FastAPI(
    title="Vibe Trading 回测系统",
    description="回测任务管理、实时进度监控、结果展示",
    version="1.0.0"
)


# =============================================================================
# WebSocket连接管理
# =============================================================================


@app.websocket("/ws/progress/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket进度推送端点"""
    await websocket.accept()
    manager.active_connections.append(websocket)
    logger.info(f"WebSocket连接建立: {task_id}")

    try:
        # 保持连接并发送进度更新
        while True:
            # 这里可以等待新的进度更新
            # 实际使用中，由回测任务调用broadcast_progress
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.active_connections.remove(websocket)
        logger.info(f"WebSocket连接断开: {task_id}")


# =============================================================================
# API端点
# =============================================================================


@app.get("/")
async def root():
    """首页"""
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Vibe Trading 回测系统</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .header {
            text-align: center;
            padding: 40px 0;
            border-bottom: 1px solid #333;
        }
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .header p {
            color: #888;
            font-size: 1.1em;
        }
        .section {
            background: #1e1e2e;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        .section h2 {
            font-size: 1.8em;
            margin-bottom: 20px;
            color: #667eea;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: #252535;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        .stat-card h3 {
            font-size: 0.9em;
            color: #888;
            margin-bottom: 10px;
        }
        .stat-card .value {
            font-size: 2em;
            font-weight: bold;
            color: #fff;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #bbb;
            font-size: 0.9em;
        }
        .form-control {
            width: 100%;
            padding: 12px;
            background: #2a2a3a;
            border: 1px solid #444;
            border-radius: 8px;
            color: #fff;
            font-size: 1em;
        }
        .form-control:focus {
            outline: none;
            border-color: #667eea;
        }
        select.form-control {
            cursor: pointer;
        }
        .btn {
            padding: 14px 28px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 8px;
            color: #fff;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }
        .btn:active {
            transform: translateY(0);
        }
        .btn-secondary {
            background: #444;
        }
        .task-list {
            margin-top: 20px;
        }
        .task-item {
            background: #252535;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 15px;
            border-left: 4px solid #444;
            transition: all 0.3s;
        }
        .task-item.running {
            border-left-color: #667eea;
        }
        .task-item.completed {
            border-left-color: #10b981;
        }
        .task-item.failed {
            border-left-color: #ef4444;
        }
        .task-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .task-title {
            font-size: 1.1em;
            font-weight: 600;
        }
        .task-status {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }
        .task-status.pending {
            background: #444;
            color: #bbb;
        }
        .task-status.running {
            background: rgba(102, 126, 234, 0.2);
            color: #667eea;
        }
        .task-status.completed {
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
        }
        .task-status.failed {
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
        }
        .task-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-top: 10px;
        }
        .task-info-item {
            font-size: 0.9em;
            color: #888;
        }
        .task-info-item .value {
            color: #fff;
            font-weight: 600;
        }
        .progress-bar {
            width: 100%;
            height: 6px;
            background: #333;
            border-radius: 3px;
            overflow: hidden;
            margin-top: 10px;
        }
        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            transition: width 0.3s;
            border-radius: 3px;
        }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #888;
        }
        .empty-state svg {
            width: 80px;
            height: 80px;
            margin-bottom: 20px;
            opacity: 0.5;
        }
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255, 255, 255, 0.1);
            border-top-color: #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 Vibe Trading 回测系统</h1>
            <p>实时监控、结果展示、性能分析</p>
        </div>

        <!-- 创建回测任务 -->
        <div class="section">
            <h2>🚀 创建回测任务</h2>
            <form id="backtestForm">
                <div class="stats-grid">
                    <div class="form-group">
                        <label>交易品种</label>
                        <input type="text" class="form-control" id="symbol" value="BTCUSDT" placeholder="BTCUSDT">
                    </div>
                    <div class="form-group">
                        <label>K线间隔</label>
                        <select class="form-control" id="interval">
                            <option value="1m">1分钟</option>
                            <option value="5m">5分钟</option>
                            <option value="15m">15分钟</option>
                            <option value="1h" selected>1小时</option>
                            <option value="4h">4小时</option>
                            <option value="1d">1天</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>开始日期</label>
                        <input type="date" class="form-control" id="startDate" value="2026-03-01">
                    </div>
                    <div class="form-group">
                        <label>结束日期</label>
                        <input type="date" class="form-control" id="endDate" value="2026-03-10">
                    </div>
                    <div class="form-group">
                        <label>初始资金 ($)</label>
                        <input type="number" class="form-control" id="initialBalance" value="10000">
                    </div>
                    <div class="form-group">
                        <label>LLM模式</label>
                        <select class="form-control" id="llmMode">
                            <option value="simulated" selected>模拟模式 (最快)</option>
                            <option value="cached">缓存模式 (推荐)</option>
                            <option value="real">真实模式 (最准)</option>
                        </select>
                    </div>
                </div>
                <button type="submit" class="btn" id="submitBtn">
                    <span id="btnText">开始回测</span>
                </button>
            </form>
        </div>

        <!-- 任务列表 -->
        <div class="section">
            <h2>📋 回测任务</h2>
            <div id="taskList" class="task-list">
                <div class="empty-state">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2H9a2 2 0 00-2 2V5z"/>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5a2 2 0 012 2h2a2 2 0 012 2v2a2 2 0 01-2 2H9a2 2 0 01-2-2V9a2 2 0 012-2V5z"/>
                    </svg>
                    <p>暂无回测任务</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        // WebSocket连接
        let ws = null;
        let currentTaskId = null;

        // 初始化
        document.addEventListener('DOMContentLoaded', () => {
            loadTasks();

            // 定期刷新任务列表
            setInterval(loadTasks, 2000);
        });

        // 表单提交
        document.getElementById('backtestForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            await createBacktest();
        });

        // 创建回测
        async function createBacktest() {
            const btn = document.getElementById('submitBtn');
            const btnText = document.getElementById('btnText');

            const data = {
                symbol: document.getElementById('symbol').value,
                interval: document.getElementById('interval').value,
                start_time: document.getElementById('startDate').value,
                end_time: document.getElementById('endDate').value,
                initial_balance: parseFloat(document.getElementById('initialBalance').value),
                llm_mode: document.getElementById('llmMode').value
            };

            // 验证
            if (!data.symbol || !data.interval || !data.start_time || !data.end_time) {
                alert('请填写完整信息');
                return;
            }

            // 禁用按钮
            btn.disabled = true;
            btnText.textContent = '提交中...';

            try {
                const response = await fetch('/api/backtest', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    const result = await response.json();
                    currentTaskId = result.task_id;
                    connectWebSocket(result.task_id);
                    loadTasks();
                    alert('回测任务已创建！');
                } else {
                    const error = await response.json();
                    alert('创建失败: ' + error.detail);
                }
            } catch (error) {
                alert('请求失败: ' + error);
            } finally {
                btn.disabled = false;
                btnText.textContent = '开始回测';
            }
        }

        // 加载任务列表
        async function loadTasks() {
            try {
                const response = await fetch('/api/backtest/tasks');
                if (response.ok) {
                    const tasks = await response.json();
                    renderTaskList(tasks);
                }
            } catch (error) {
                console.error('加载任务失败:', error);
            }
        }

        // 渲染任务列表
        function renderTaskList(tasks) {
            const container = document.getElementById('taskList');

            if (tasks.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <svg xmlns="http://www.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2H9a2 2 0 00-2-2V5z"/>
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5a2 2 0 012 2h2a2 2 0 012 2v2a2 2 0 01-2 2H9a2 2 0 01-2-2V9a2 2 0 012-2V5z"/>
                        </svg>
                        <p>暂无回测任务</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = tasks.map(task => {
                const statusClass = task.status.toLowerCase();
                const statusText = {
                    'pending': '等待中',
                    'running': '运行中',
                    'completed': '已完成',
                    'failed': '失败'
                }[task.status] || task.status;

                const progressPercent = task.total_klines > 0
                    ? (task.current_kline / task.total_klines * 100).toFixed(1)
                    : 0;

                return `
                    <div class="task-item ${statusClass}">
                        <div class="task-header">
                            <div class="task-title">${task.symbol} - ${task.interval}</div>
                            <div class="task-status ${statusClass}">${statusText}</div>
                        </div>
                        <div class="task-info">
                            <div class="task-info-item">
                                <div>进度</div>
                                <div class="value">${progressPercent}%</div>
                            </div>
                            <div class="task-info-item">
                                <div>权益</div>
                                <div class="value">$${task.current_equity.toFixed(2)}</div>
                            </div>
                            <div class="task-info-item">
                                <div>交易</div>
                                <div class="value">${task.total_trades}</div>
                            </div>
                            <div class="task-info-item">
                                <div>LLM调用</div>
                                <div class="value">${task.llm_calls}</div>
                            </div>
                            <div class="task-info-item">
                                <div>缓存命中率</div>
                                <div class="value">${(task.llm_cache_hits / task.llm_calls * 100).toFixed(0)}%</div>
                            </div>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-bar-fill" style="width: ${progressPercent}%"></div>
                        </div>
                        <div style="margin-top: 15px; text-align: right;">
                            <button class="btn btn-secondary" onclick="viewResults('${task.task_id}')" ${task.status !== 'completed' ? 'disabled' : ''}>
                                查看详情
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // WebSocket连接
        function connectWebSocket(taskId) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.close();
            }

            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws/progress/${taskId}`);

            ws.onmessage = (event) => {
                const update = JSON.parse(event.data);
                updateTaskInList(update);
            };

            ws.onclose = () => {
                console.log('WebSocket连接关闭');
                // 5秒后重连
                setTimeout(() => {
                    if (currentTaskId === taskId) {
                        connectWebSocket(taskId);
                    }
                }, 5000);
            };

            ws.onerror = (error) => {
                console.error('WebSocket错误:', error);
            };
        }

        // 更新任务显示
        function updateTaskInList(update) {
            // 这里可以更新单个任务的显示
            loadTasks();
        }

        // 查看结果
        function viewResults(taskId) {
            window.open(`/results/${taskId}`, '_blank');
        }
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@app.get("/api/backtest/tasks")
async def get_tasks():
    """获取所有回测任务"""
    tasks = manager.get_all_tasks()
    return JSONResponse(tasks)


@app.post("/api/backtest")
async def create_backtest(request: BacktestCreateRequest):
    """创建新的回测任务"""
    import asyncio
    import uuid

    # 生成任务ID
    task_id = f"backtest_{uuid.uuid4().hex[:8]}"

    # 创建任务
    task = BacktestTask(
        task_id=task_id,
        symbol=request.symbol,
        interval=request.interval,
        start_time=request.start_time,
        end_time=request.end_time,
        llm_mode=request.llm_mode,
        status="pending",
        created_at=datetime.now().isoformat(),
    )

    manager.add_task(task)

    # 异步执行回测（不阻塞响应）
    asyncio.create_task(run_backtest_task(task_id, request))

    return {"task_id": task_id, "status": "pending"}


@app.get("/api/backtest/{task_id}")
async def get_task(task_id: str):
    """获取单个任务详情"""
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JSONResponse(task)


@app.get("/results/{task_id}")
async def view_results(task_id: str):
    """查看回测结果页面"""
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 这里可以返回详细的结果页面
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>回测结果 - {task['symbol']}</title>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background: #f5f5f5;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>回测结果 - {task['symbol']}</h1>
            <p>任务ID: {task_id}</p>
            <p>状态: {task['status']}</p>
            <p>权益: ${task['current_equity']:.2f}</p>
            <p>交易数: {task['total_trades']}</p>
            <p><a href="/">← 返回任务列表</a></p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# =============================================================================
# 回测执行逻辑
# =============================================================================


async def run_backtest_task(task_id: str, request: BacktestCreateRequest):
    """在后台运行回测任务"""
    try:
        # 更新状态为运行中
        manager.update_task(task_id, {
            "status": "running",
            "started_at": datetime.now().isoformat()
        })

        # 发送初始进度
        await manager.broadcast_progress(ProgressUpdate(
            task_id=task_id,
            status="running",
            current_kline=0,
            total_klines=100,
            progress_percentage=0.0,
            current_equity=request.initial_balance,
            total_trades=0,
            llm_calls=0,
            llm_cache_hits=0,
            cache_hit_rate=0.0,
        ))

        # 导入回测模块
        from vibe_trading.backtest.engine import BacktestEngine
        from vibe_trading.backtest.models import BacktestConfig, LLMMode
        from vibe_trading.backtest.progress import ProgressTracker

        # 创建配置
        config = BacktestConfig(
            symbol=request.symbol,
            interval=request.interval,
            start_time=datetime.fromisoformat(request.start_time),
            end_time=datetime.fromisoformat(request.end_time),
            initial_balance=request.initial_balance,
            llm_mode=LLMMode(request.llm_mode.lower()),
            enable_progress_bar=False,
        )

        # 创建进度追踪器
        tracker = ProgressTracker(task_id=task_id)

        # 添加进度回调
        async def progress_callback(update):
            # 广播进度更新
            await manager.broadcast_progress(update)

            # 更新任务状态
            manager.update_task(task_id, {
                "status": update.status.value,
                "current_kline": update.current_kline,
                "current_equity": update.current_equity,
                "total_trades": update.total_trades,
                "llm_calls": update.llm_calls,
                "llm_cache_hits": update.llm_cache_hits,
            })

        tracker.add_callback(progress_callback)

        # 创建引擎
        engine = BacktestEngine(config)

        # 运行回测
        result = await engine.run_backtest()

        # 完成
        tracker.complete()

        # 更新最终状态
        manager.update_task(task_id, {
            "status": "completed",
            "current_kline": result.total_klines,
            "current_equity": result.metrics.total_return if result.metrics else request.initial_balance,
            "total_trades": len(result.trades),
            "llm_calls": result.llm_calls,
            "llm_cache_hits": result.llm_cache_hits,
            "completed_at": datetime.now().isoformat(),
        })

        logger.info(f"回测任务完成: {task_id}")

    except Exception as e:
        logger.error(f"回测任务失败: {task_id} - {e}", exc_info=True)

        # 更新状态为失败
        manager.update_task(task_id, {
            "status": "failed",
            "error_message": str(e),
            "completed_at": datetime.now().isoformat(),
        })


# =============================================================================
# 启动服务器
# =============================================================================

if __name__ == "__main__":
    print("🚀 启动回测Web服务...")
    print("📍 访问 http://localhost:8000")
    print("   文档: http://localhost:8000/docs")
    print("   回测管理: http://localhost:8000/")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
