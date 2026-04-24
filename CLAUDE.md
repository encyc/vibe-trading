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

**Prime Agent Mode:**
- Monitoring mode for observing market without trading
- Uses `PrimeAgent` with `PrimeConfig` for configuration
- Command: `vibe-trade prime BTCUSDT`
- Tests located in `tests/prime/`

**Threading Architecture:**
- **Macro Thread**: Runs every hour, analyzes macro environment (trend, sentiment, events)
- **On Bar Thread**: K-line triggered, reads macro state and runs simplified 3-phase flow
- **Event Thread**: Real-time trigger monitoring with priority queue for emergency responses

## Development Commands

**Recommended: Use Makefile (from project root)**
```bash
make install          # Install dependencies
make start            # Run trading system (SYMBOL=BTCUSDT)
make start-web        # Run with web monitoring (localhost:8000)
make analyze          # Single analysis
make test             # Run all tests
make check            # Lint + typecheck
make fix              # Auto-fix linting issues
make clean            # Clean cache files

# Run specific tests
make test-technical   # Technical analysis tests
make test-sentiment   # Sentiment tools tests
make test-researchers # Researcher tests
```

**Backend (Python) - from backend directory**
```bash
cd backend && uv pip install -e .

# Run trading system
PYTHONPATH=src uv run -- vibe-trade start BTCUSDT

# Prime Agent monitoring mode
PYTHONPATH=src uv run -- vibe-trade prime BTCUSDT

# Run tests (pytest-asyncio auto mode enabled)
cd tests && uv run pytest -v
```

**Frontend (React/Vite) - from frontend/react-app**
```bash
npm install           # Install dependencies
npm run dev           # Development server (localhost:3000)
npm run build         # Production build (tsc + vite)
npm run lint          # ESLint check
```

**Web Services**
```bash
make web              # React frontend (localhost:3000)
make web-backend      # Backend web server (localhost:8000)
make full-start       # Backend + frontend together
make test-ws          # Test WebSocket connection
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

### Web Modules
- `vibe_trading.web`: Main web server with WebSocket support
- `backend.web_live`: Live trading web interface module

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
- Test files are in `tests/` directory (pytest.ini configured)
- pytest-asyncio auto mode: async test functions are automatically detected
- Tests use real market data from Binance
- Some tests require API keys in `.env`
- Prime Agent tests in `tests/prime/`
- Run specific test file: `cd tests && uv run pytest test_name.py -v`

### Database
- Uses SQLite with aiosqlite for async operations
- Migrations in `data_sources/migrations/`
- Tables: klines, macro_states, trigger_configs, trigger_events, decisions

### Multi-threading
- Three independent threads communicate via shared state and message passing
- Emergency mode pauses main thread for critical events
- Use `ThreadManager` to manage thread lifecycle

### Frontend (React)
- Located in `frontend/react-app/` (Vite + TypeScript)
- WebSocket connection to backend for real-time updates
- Uses lightweight-charts for K-line visualization
- Components: `src/components/` (Panel, Chart, AgentFlow, etc.)
- Services: `src/services/` (WebSocket client)
- Hooks: `src/hooks/` (useWebSocket, usePanel, etc.)

### Documentation Site
- VitePress docs in `docs/` directory
- Deployed to GitHub Pages via `.github/workflows/deploy.yml`
- Build: `cd docs && npm run build`
- Preview: `cd docs && npm run preview`

## Behavioral Guidelines

These guidelines reduce common LLM coding mistakes and bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
