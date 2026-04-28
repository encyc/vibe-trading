.PHONY: help install start start-web analyze web test lint format typecheck clean all frontend frontend-dev frontend-build test-ws

# Default target
.DEFAULT_GOAL := help

# Variables
SYMBOL ?= BTCUSDT
INTERVAL ?= 30m
PYTHONPATH = backend/src
BACKEND_DIR = backend

help: ## Show this help message
	@echo "Vibe Trading - Multi-Agent Cryptocurrency Trading System"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	@echo "Installing dependencies..."
	cd $(BACKEND_DIR) && uv pip install -e .

start: ## Run trading system (multi-threaded)
	@echo "Starting trading system for $(SYMBOL) ($(INTERVAL))..."
	PYTHONPATH=$(PYTHONPATH) uv run -- vibe-trade start $(SYMBOL) --interval $(INTERVAL)

start-web: ## Run trading system with web monitoring (http://localhost:8000)
	@echo "Starting trading system with web monitoring for $(SYMBOL) ($(INTERVAL))..."
	PYTHONPATH=$(PYTHONPATH) uv run -- vibe-trade start $(SYMBOL) --interval $(INTERVAL) --web

analyze: ## Run single analysis
	@echo "Analyzing $(SYMBOL)..."
	PYTHONPATH=$(PYTHONPATH) uv run -- vibe-trade analyze --symbol $(SYMBOL)

web: ## Run React frontend (http://localhost:3000)
	@echo "Starting React frontend..."
	cd frontend/react-app && npm run dev

web-backend: ## Run backend web server (http://localhost:8000)
	@echo "Starting backend web server..."
	PYTHONPATH=$(PYTHONPATH) uv run backend/src/vibe_trading/web/server.py

test: ## Run all tests
	@echo "Running tests..."
	cd tests && uv run pytest -v

test-technical: ## Run technical analysis tests
	@echo "Running technical analysis tests..."
	cd tests && uv run pytest test_technical_analysis.py -v

test-sentiment: ## Run sentiment tools tests
	@echo "Running sentiment tools tests..."
	cd tests && uv run pytest test_sentiment_tools.py -v

test-researchers: ## Run researcher tests
	@echo "Running researcher tests..."
	cd tests && uv run pytest test_researchers.py -v

lint: ## Run linting (ruff check)
	@echo "Running linter..."
	uv run ruff check $(BACKEND_DIR)/src/

format: ## Format code (ruff format)
	@echo "Formatting code..."
	uv run ruff format $(BACKEND_DIR)/src/

typecheck: ## Run type checking (mypy)
	@echo "Running type checker..."
	uv run mypy $(BACKEND_DIR)/src/

check: lint typecheck ## Run all checks (lint + typecheck)
	@echo "All checks completed."

fix: ## Fix linting issues automatically
	@echo "Fixing linting issues..."
	uv run ruff check $(BACKEND_DIR)/src/ --fix

clean: ## Clean cache and temporary files
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleanup completed."

all: install lint typecheck test ## Run install, checks and tests
	@echo "Build completed successfully."

# Frontend commands
frontend: ## Install frontend dependencies
	@echo "Installing frontend dependencies..."
	cd frontend/react-app && npm install

frontend-dev: ## Run frontend development server (http://localhost:3000)
	@echo "Starting frontend development server..."
	cd frontend/react-app && npm run dev

frontend-build: ## Build frontend for production
	@echo "Building frontend..."
	cd frontend/react-app && npm run build

full-start: ## Start backend with React frontend (development)
	@echo "=========================================="
	@echo "Starting Full Vibe Trading System"
	@echo "=========================================="
	@echo ""
	@echo "Backend (WebSocket): http://localhost:8000"
	@echo "Frontend (React):    http://localhost:3000"
	@echo ""
	@echo "Press Ctrl+C to stop both services"
	@echo "=========================================="
	@echo ""
	@make -j2 start-web web

test-ws: ## Test WebSocket connection
	@echo "Testing WebSocket connection to ws://localhost:8000/ws"
	@python3 scripts/test_websocket.py
