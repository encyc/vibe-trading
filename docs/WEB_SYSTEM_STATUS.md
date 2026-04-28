# Vibe Trading Web System Status

## 当前状态

Web 监控系统当前采用：

- Backend: FastAPI + WebSocket，默认端口 `8000`
- Frontend: React + Vite + TypeScript，默认端口 `3000`
- Chart: `lightweight-charts`
- Persistence: SQLite `klines` + `bar_decision_journal`

## 快速启动

```bash
# 启动交易系统 + WebSocket 后端
make start-web SYMBOL=BTCUSDT INTERVAL=30m

# 启动 React 前端
make web

# 或并行启动
make full-start
```

访问地址：

```text
Frontend:  http://localhost:3000
Backend:   http://localhost:8000
WebSocket: ws://localhost:8000/ws
```

## 当前能力

- 实时 K线展示
- BUY/SELL 决策标记
- Agent Monitor 分阶段展示报告
- Agent 报告点击展开/收起
- Agent 报告 Markdown 渲染
- Runtime Log 同步 terminal 输出
- 右侧模块拖拽排序和调整高度
- 主图与右侧区域横向调整
- 点击历史 K线查询该 K线的 Agent 报告、日志和最终决策

## 关键文件

- `backend/src/vibe_trading/web/server.py`：FastAPI/WebSocket 服务和 Web 状态 API
- `backend/src/vibe_trading/web/journal_storage.py`：K线级决策追溯持久化
- `backend/src/vibe_trading/threads/onbar_thread.py`：K线处理与 Web 推送
- `frontend/react-app/src/App.tsx`：主布局和模块拖拽/调整大小
- `frontend/react-app/src/hooks/useTradingFeed.ts`：WebSocket 连接与自动重连
- `frontend/react-app/src/components/ChartPanel.tsx`：K线图表
- `frontend/react-app/src/components/AgentActivityPanel.tsx`：Agent 报告展示

## 验证命令

```bash
# 后端状态
curl http://localhost:8000/api/status

# 前端构建
cd frontend/react-app && npm run build

# WebSocket 测试
make test-ws
```

## 注意事项

- `make start-web` 会把交易系统和 Web 后端运行在同一个 Python 进程中，因此 Runtime Log 可以镜像 terminal 输出。
- 如果单独运行 `make web-backend`，再从另一个进程启动交易系统，Runtime Log 只能显示通过 API 主动发送的日志。
- 点击历史 K线时，只有被系统处理并写入 `bar_decision_journal` 的 K线才会显示完整 Agent 报告。普通历史 OHLCV 不会自动生成报告。
