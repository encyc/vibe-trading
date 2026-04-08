# Web 监控

Vibe Trading 提供量子指挥塔风格的实时监控界面，让你能够实时查看 Agent 的决策过程和交易状态。

## 启动 Web 监控

### 方法1：使用 uvicorn

```bash
cd backend
PYTHONPATH=src uv run uvicorn vibe_trading.web.server:app --host 0.0.0.0 --port 8000 --reload
```

### 方法2：使用 FastAPI 开发服务器

```bash
cd backend
PYTHONPATH=src uv run --from vibe_trading.web.server python -m uvicorn vibe_trading.web.server:app --reload
```

### 访问界面

启动后，在浏览器中访问：

```
http://localhost:8000
```

## 界面概览

### 主要功能区域

```
┌─────────────────────────────────────────────────────────────┐
│  VIBE TRADING | QUANTUM COMMAND CENTER                     │
│  [重置布局]                                                 │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  市场概览                                                    │
│  [BTCUSDT] [价格] [涨跌] [成交量] [周期] [K线数]             │
└─────────────────────────────────────────────────────────────┘
┌──────────┬──────────┬──────────────────────────────────────┐
│  K线图表  │ Agent流程 │           决策中心                   │
│  [图表]   │ [Phase1-4]│      [当前决策] [决策统计]          │
└──────────┴──────────┴──────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  Agent报告切换  [分析师][研究员][风控][交易员][PM]            │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  实时日志                                                    │
│  [INFO] [DEBUG] [ERROR]                                    │
└─────────────────────────────────────────────────────────────┘
```

## 磁贴功能

### 拖拽排序

- 点击磁贴头部并拖动即可重新排列
- 拖动时磁贴会发光并浮起
- 其他磁贴会显示目标位置高亮
- 松开鼠标自动吸附到新位置

### 调整大小

**方式1：点击按钮循环切换**
- 点击磁贴头部的 ⊞ 按钮
- 循环切换5种预设尺寸（sm/md/lg/full/tall）

**方式2：自由调整**
- 拖动磁贴右下角的调整大小手柄
- 自由调整尺寸
- 自动吸附到最接近的预设尺寸

### 布局保存

- 所有磁贴位置和大小自动保存到浏览器本地存储
- 刷新页面后自动恢复之前的布局
- 点击顶部"重置布局"按钮可恢复默认布局

## 主要磁贴说明

### 1. 市场概览

显示实时市场数据：
- 交易对（如 BTCUSDT）
- 当前价格
- 24小时涨跌
- 24小时成交量
- K线周期
- K线数量

### 2. K线图表

实时K线图表，包含：
- 蜡烛图
- 决策标记点（↑↓○）
- 技术指标（RSI、MACD等）
- 自定义数据缩放控件

### 3. Agent协作流程

可视化展示4阶段协作流程：
- Phase 1-4 状态
- 当前运行阶段
- Agent标签系统
- 决策树可视化

### 4. 决策中心

显示当前决策和历史统计：
- 当前决策（类型、置信度、仓位）
- 决策统计（买入/卖出/观望/总数/胜率）
- 决策历史列表

### 5. Agent报告

切换查看不同团队的报告：
- 分析师报告
- 研究员报告
- 风控报告
- 交易员报告
- PM报告

### 6. 实时日志

实时显示系统日志：
- INFO：常规信息
- DEBUG：调试信息
- ERROR：错误信息
- 支持折叠/展开

## WebSocket 通信

### 连接地址

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
```

### 消息类型

#### 1. K线数据

```json
{
  "type": "kline",
  "data": {
    "symbol": "BTCUSDT",
    "open": 65000,
    "high": 65500,
    "low": 64800,
    "close": 65200,
    "volume": 1000
  }
}
```

#### 2. 决策数据

```json
{
  "type": "decision",
  "data": {
    "decision": "BUY",
    "quantity": 0.2,
    "price": 65000,
    "confidence": 0.75,
    "rationale": "综合评估后建议买入"
  }
}
```

#### 3. 阶段更新

```json
{
  "type": "phase",
  "data": {
    "phase": "analysts",
    "status": "running",
    "progress": 0.5
  }
}
```

#### 4. 日志消息

```json
{
  "type": "log",
  "data": {
    "level": "INFO",
    "tag": "TRADING",
    "message": "新K线到达，开始分析",
    "timestamp": "2024-01-01T12:00:00Z"
  }
}
```

#### 5. Agent报告

```json
{
  "type": "report",
  "data": {
    "agent": "TechnicalAnalyst",
    "phase": "analysts",
    "content": "上升趋势，RSI=65"
  }
}
```

## 自定义配置

### 修改磁贴默认布局

编辑 `backend/src/vibe_trading/web/visualizer.py` 中的 `default_tiles`：

```python
default_tiles = [
    {
        "id": "market-overview",
        "title": "市场概览",
        "size": "full",
        "position": {"x": 0, "y": 0, "w": 12, "h": 1}
    },
    # 添加更多磁贴...
]
```

### 自定义主题颜色

修改前端 CSS 变量：

```css
:root {
    --neon-cyan: #00f0ff;
    --neon-purple: #8b5cf6;
    --neon-green: #10b981;
    /* 修改这些颜色值 */
}
```

### 修改更新频率

编辑 `backend/src/vibe_trading/web/server.py`：

```python
# 修改推送频率
UPDATE_INTERVAL = 1.0  # 秒
```

## 性能优化

### 1. 节流更新

避免频繁更新导致性能问题：

```javascript
let lastUpdate = 0;
const UPDATE_INTERVAL = 1000; // 1秒

function updateUI(data) {
    const now = Date.now();
    if (now - lastUpdate < UPDATE_INTERVAL) {
        return;
    }
    lastUpdate = now;
    // 更新UI
}
```

### 2. 虚拟滚动

处理大量日志数据：

```javascript
// 只渲染可见区域的日志
const visibleLogs = logs.slice(
    scrollTop / itemHeight,
    (scrollTop + containerHeight) / itemHeight
);
```

### 3. 数据压缩

压缩WebSocket消息：

```python
import json
import gzip

def compress_message(data):
    json_str = json.dumps(data)
    return gzip.compress(json_str.encode())
```

## 故障排除

### 无法连接到 WebSocket

1. 检查后端服务是否启动
2. 检查防火墙设置
3. 查看浏览器控制台错误信息

### 图表不更新

1. 检查K线数据是否正常推送
2. 检查ECharts实例是否正确初始化
3. 查看浏览器控制台错误信息

### 布局异常

1. 清除浏览器缓存
2. 删除 localStorage 中的布局数据
3. 点击"重置布局"按钮

## 移动端支持

Web监控界面支持移动端访问：

- 响应式布局自动适配
- 触控手势支持
- 简化的移动端视图

## 下一步

- 了解 [回测系统](/guide/backtest) 验证策略
- 学习 [配置说明](/guide/configuration) 自定义系统
- 查看 [API文档](/guide/api) 集成外部应用