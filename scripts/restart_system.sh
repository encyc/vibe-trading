#!/bin/bash
echo "=== Restarting Vibe Trading System ==="

# Kill all processes
echo "Stopping existing processes..."
pkill -f "vibe-trade start" 2>/dev/null || true
pkill -f "npm run dev" 2>/dev/null || true
lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true
lsof -ti:3000 | xargs -r kill -9 2>/dev/null || true
lsof -ti:3001 | xargs -r kill -9 2>/dev/null || true

sleep 2

echo "Starting fresh system..."
make full-start
