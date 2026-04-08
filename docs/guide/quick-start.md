# 快速开始

本指南将帮助你快速搭建和运行 Vibe Trading 系统。

## 环境要求

- Python 3.13+
- Node.js 18+ (用于Web界面开发)
- Git

## 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/encyc/vibe-trading.git
cd vibe-trading
```

### 2. 安装后端依赖

我们使用 `uv` 作为包管理器，它比传统的 pip 更快。

```bash
cd backend
uv pip install -e .
```

如果没有安装 `uv`，可以先安装：

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. 配置环境变量

复制示例配置文件：

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env` 文件，配置以下内容：

```env
# Binance API 配置
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# LLM 配置
LLM_PROVIDER=openai  # 或 anthropic, azure, 本地模型
LLM_API_KEY=your_llm_api_key_here
LLM_MODEL=gpt-4

# 数据库配置
DATABASE_URL=sqlite:///vibe_trading.db

# 日志配置
LOG_LEVEL=INFO
```

::: tip 提示
如果不配置 Binance API，系统将使用 Paper Trading 模式，不会进行真实交易。
:::

### 4. 初始化数据库

```bash
cd backend
PYTHONPATH=src uv run --from vibe_trading.cli vibe-trade init-db
```

## 运行系统

### Paper Trading 模式（推荐新手）

```bash
# 返回项目根目录
cd ..

# 启动 Paper Trading
PYTHONPATH=backend/src uv run -- vibe-trade start BTCUSDT --interval 5m --mode paper
```

### 实盘交易模式

::: warning 警告
实盘交易模式会使用真实资金，请谨慎使用！建议先在 Paper Trading 模式下充分测试。
:::

```bash
# 仅打印订单，不执行
PYTHONPATH=backend/src uv run -- vibe-trade start BTCUSDT --interval 5m --mode live

# 真实执行交易
PYTHONPATH=backend/src uv run -- vibe-trade start BTCUSDT --interval 5m --mode live --execute
```

## 启动 Web 监控界面

在另一个终端窗口中：

```bash
cd backend
PYTHONPATH=src uv run uvicorn vibe_trading.web.server:app --host 0.0.0.0 --port 8000 --reload
```

然后在浏览器中访问 `http://localhost:8000` 即可查看实时监控界面。

## 使用 Prime Agent 模式

Prime Agent 模式是推荐的生产模式，它包含更完善的三线程架构和监控：

```bash
PYTHONPATH=backend/src uv run -- vibe-trade prime BTCUSDT --interval 5m
```

## 运行回测

```bash
# 基础回测
PYTHONPATH=backend/src uv run -- vibe-trade backtest BTCUSDT --start "2024-01-01" --end "2024-01-31"

# 使用缓存模式（更快）
PYTHONPATH=backend/src uv run -- vibe-trade backtest BTCUSDT --start "2024-01-01" --end "2024-01-31" --llm-mode cached

# 生成HTML报告
PYTHONPATH=backend/src uv run -- vibe-trade backtest BTCUSDT --start "2024-01-01" --end "2024-01-31" --report-format html
```

## 下一步

- 阅读 [项目简介](/guide/intro) 了解系统架构
- 查看 [Agent团队](/guide/agents) 了解各个Agent的职责
- 阅读 [系统架构](/guide/architecture) 深入了解技术实现
- 配置 [Web监控](/guide/monitoring) 自定义监控界面

## 常见问题

### Q: 如何获取 Binance API 密钥？

A: 访问 [Binance API 管理](https://www.binance.com/en/my/settings/api-management) 创建API密钥。建议只启用"读取"权限以测试系统。

### Q: 系统支持哪些交易对？

A: 目前支持 Binance 的所有现货和永续合约交易对，如 BTCUSDT、ETHUSDT 等。

### Q: 如何自定义Agent？

A: 参考 [自定义Agent](/guide/custom-agent) 文档。

### Q: 如何查看日志？

A: 日志保存在 `logs/` 目录下，同时在控制台实时输出。可以通过 `.env` 文件中的 `LOG_LEVEL` 调整日志详细程度。

## 获取帮助

- 查看 [GitHub Issues](https://github.com/encyc/vibe-trading/issues)
- 阅读 [完整文档](/)
- 加入社区讨论（待开放）