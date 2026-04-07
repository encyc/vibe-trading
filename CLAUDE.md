# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vibe Trading is a multi-agent cryptocurrency trading system powered by Large Language Models (LLMs). The system uses a collaborative agent architecture with 12 specialized agents working across 4 phases to make trading decisions.

**Core Architecture:**
- **pi_agent_core**: Agent framework with dual-loop message processing engine
- **pi_ai**: LLM abstraction layer supporting multiple providers (OpenAI, Anthropic, Google, custom endpoints)
- **pi_logger**: Structured logging system with colorized console output and file logging
- **vibe_trading**: Main trading application with agents, coordinators, data sources, and execution

**Decision Flow (4 Phases):**
1. **Phase 1 - Analysts**: Technical, Fundamental, News, Sentiment analysts (parallel execution)
2. **Phase 2 - Researchers**: Bull/Bear researchers debate → Research manager makes investment recommendation
3. **Phase 3 - Risk Team**: Aggressive, Neutral, Conservative risk assessments
4. **Phase 4 - Decision Layer**: Trader creates execution plan → Portfolio manager makes final decision

**Threading Architecture:**
- **Macro Thread**: Runs every hour, analyzes macro environment (trend, sentiment, events)
- **On Bar Thread**: K-line triggered, reads macro state and runs simplified 3-phase flow
- **Event Thread**: Real-time trigger monitoring with priority queue for emergency responses

## Development Commands

```bash
# Install dependencies
cd backend && uv pip install -e .

# Run trading system (multi-threaded)
PYTHONPATH=src uv run -- vibe-trade start BTCUSDT

# Run single analysis
PYTHONPATH=src uv run -- vibe-trade analyze --symbol BTCUSDT

# Run with web monitoring
uv run test_historical.py  # Web UI at http://localhost:8000

# Run specific tests
uv run test_technical_analysis.py
uv run test_sentiment_tools.py
uv run test_researchers.py

# Linting (use ruff, not black)
uv run ruff check backend/src/
uv run ruff format backend/src/

# Type checking
uv run mypy backend/src/
```

## Configuration

**Environment Variables (.env):**
- `LLM_MODEL`: Model name from `llm.yaml` (default: `glm_4_7`)
- `TRADING_MODE`: `paper` or `live`
- `BINANCE_TESTNET_API_KEY`/`BINANCE_TESTNET_API_SECRET`: For paper trading
- `BINANCE_API_KEY`/`BINANCE_API_SECRET`: For live trading
- `DATABASE_URL`: SQLite database path
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR

**LLM Configuration (backend/src/pi_ai/llm.yaml):**
- Contains multiple model configurations (glm_4_7, iflow, longcat, etc.)
- `use_llm`: Default model to use
- `model_router`: Automatic model selection based on task type

**Agent Configuration (backend/src/vibe_trading/config/agent_config.py):**
- `AgentRole`: Enum of all 12 agent roles
- `AgentConfig`: Per-agent configuration (temperature, model override, enabled status)
- `AgentTeamConfig`: Default configurations for all agents

## Key Architecture Patterns

### Agent System
- All agents inherit from `pi_agent_core.Agent` and use `agent_loop()` for execution
- Agents are created via `agent_factory.create_trading_agent()` with tool assignment
- Use `get_logger()` from `pi_logger` for logging (NOT standard `logging.getLogger()`)
- The logger supports `tag` parameter: `logger.info("message", tag="AgentName")`

### Tool System
- 23 tools defined across 4 categories: technical, fundamental, sentiment, market data
- Tools are Pydantic models with `@tool` decorator
- Assigned to agents based on role in `agent_factory.py`
- Tools can be called by LLM via function calling

### State Management
- `SharedStateManager`: Thread-safe shared state storage
- `StateMachine`: Decision flow state tracking (ANALYZING → DEBATING → ASSESSING_RISK → PLANNING → COMPLETED)
- `EventQueue`: Priority queue for trigger events (CRITICAL > HIGH > MEDIUM > LOW)

### Trigger System
- Extensible trigger system via `trigger_registry.register()`
- Triggers check conditions and return `TriggerEvent` when triggered
- Priority levels determine handling: CRITICAL (auto-execute), HIGH (suggest), MEDIUM/LOW (log only)

### LLM Integration
- Use `stream_simple()` for basic streaming responses
- Model router automatically selects models based on whether tools are needed
- Concurrent LLM calls are limited via Semaphore (default: 3 concurrent) to avoid rate limiting
- Credit tracking available for billing (optional)

### Data Sources
- `BinanceClient`: WebSocket and REST API client for market data
- `KlineStorage`: SQLite-based K-line data persistence
- `MacroStorage`: SQLite-based macro state storage
- `RateLimiter`: Token bucket rate limiter (2400 requests/minute)

## Important Notes

### Logging
- **Always use `pi_logger`**: `from pi_logger import get_logger; logger = get_logger(__name__)`
- **Never use standard logging**: `logging.getLogger(__name__)` does NOT support the `tag` parameter
- Standard logging causes `TypeError: info() got an unexpected keyword argument 'tag'` errors

### Agent Development
- Agents should be async and use `agent.prompt()` for user messages
- Use `ToolContext` to pass shared resources (symbol, interval, storage, etc.)
- Agent prompts are in `config/prompts.py`
- Use `setup_streaming()` for streaming event callbacks

### Testing
- Test files are in root directory (not backend/src)
- Tests use real market data from Binance
- Some tests require API keys in `.env`

### Database
- Uses SQLite with aiosqlite for async operations
- Migrations in `data_sources/migrations/`
- Tables: klines, macro_states, trigger_configs, trigger_events, decisions

### Multi-threading
- Three independent threads communicate via shared state and message passing
- Emergency mode pauses main thread for critical events
- Use `ThreadManager` to manage thread lifecycle
