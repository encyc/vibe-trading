.PHONY: help install start start-web analyze web test lint format typecheck clean all

# Default target
.DEFAULT_GOAL := help

# Variables
SYMBOL ?= BTCUSDT
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
	@echo "Starting trading system for $(SYMBOL)..."
	PYTHONPATH=$(PYTHONPATH) uv run -- vibe-trade start $(SYMBOL)

start-web: ## Run trading system with web monitoring (http://localhost:8000)
	@echo "Starting trading system with web monitoring for $(SYMBOL)..."
	PYTHONPATH=$(PYTHONPATH) uv run -- vibe-trade start $(SYMBOL) --web

analyze: ## Run single analysis
	@echo "Analyzing $(SYMBOL)..."
	PYTHONPATH=$(PYTHONPATH) uv run -- vibe-trade analyze --symbol $(SYMBOL)

web: ## Run web monitoring interface (http://localhost:8000)
	@echo "Starting web interface..."
	PYTHONPATH=$(PYTHONPATH) uv run backend/src/vibe_trading/web/server.py

test: ## Run all tests
	@echo "Running tests..."
	cd tests && uv run pytest test_backtest_system.py -v

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
