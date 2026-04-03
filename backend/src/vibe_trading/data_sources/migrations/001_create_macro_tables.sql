-- ============================================================================
-- Vibe Trading Database Migration: Macro Tables
-- Version: 001
-- Description: Create tables for macro analysis, trigger management, and thread state
-- ============================================================================

-- ============================================================================
-- 1. Macro States Table
-- Stores macro analysis results from the macro analysis thread
-- ============================================================================
CREATE TABLE IF NOT EXISTS macro_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    timestamp INTEGER NOT NULL,  -- Unix timestamp (milliseconds)
    
    -- Trend Analysis
    trend_direction VARCHAR(20),  -- UPTREND/DOWNTREND/SIDEWAYS
    trend_strength VARCHAR(20),   -- STRONG/MODERATE/WEAK
    market_regime VARCHAR(20),    -- BULL/BEAR/NEUTRAL
    
    -- Sentiment Analysis
    overall_sentiment VARCHAR(20), -- POSITIVE/NEGATIVE/NEUTRAL
    sentiment_score REAL,         -- -100 to 100
    
    -- Major Events
    major_events TEXT,            -- JSON array of events
    
    -- Agent Recommendation
    agent_recommendation TEXT,    -- JSON
    
    -- Metadata
    confidence REAL,              -- 0 to 1
    analysis_duration REAL,       -- seconds
    
    -- Timestamps
    created_at INTEGER NOT NULL,
    
    -- Constraints
    UNIQUE(symbol, timestamp)
);

-- Indexes for macro_states
CREATE INDEX IF NOT EXISTS idx_macro_states_symbol_timestamp 
    ON macro_states(symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_macro_states_timestamp 
    ON macro_states(timestamp);
CREATE INDEX IF NOT EXISTS idx_macro_states_trend_direction 
    ON macro_states(trend_direction);
CREATE INDEX IF NOT EXISTS idx_macro_states_market_regime 
    ON macro_states(market_regime);

-- ============================================================================
-- 2. Trigger Configs Table
-- Stores trigger configurations
-- ============================================================================
CREATE TABLE IF NOT EXISTS trigger_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_name VARCHAR(50) UNIQUE NOT NULL,
    trigger_type VARCHAR(20) NOT NULL,  -- PRICE/RISK/SYSTEM
    
    -- Configuration
    config_json TEXT NOT NULL,
    
    -- Runtime Parameters
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 50,  -- 0-100, higher = more urgent
    cooldown_seconds INTEGER DEFAULT 300,
    
    -- Statistics
    trigger_count INTEGER DEFAULT 0,
    last_triggered_at INTEGER,
    
    -- Timestamps
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- Indexes for trigger_configs
CREATE INDEX IF NOT EXISTS idx_trigger_configs_enabled 
    ON trigger_configs(enabled);
CREATE INDEX IF NOT EXISTS idx_trigger_configs_priority 
    ON trigger_configs(priority);
CREATE INDEX IF NOT EXISTS idx_trigger_configs_type 
    ON trigger_configs(trigger_type);

-- ============================================================================
-- 3. Trigger Events Table
-- Stores triggered events and their processing status
-- ============================================================================
CREATE TABLE IF NOT EXISTS trigger_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id VARCHAR(50) UNIQUE NOT NULL,
    trigger_name VARCHAR(50) NOT NULL,
    symbol VARCHAR(20),
    
    -- Event Data
    severity VARCHAR(20) NOT NULL,  -- LOW/MEDIUM/HIGH/CRITICAL
    data_json TEXT NOT NULL,
    
    -- Processing Status
    status VARCHAR(20) NOT NULL,   -- PENDING/CONFIRMED/EXECUTED/IGNORED
    action_taken TEXT,             -- JSON
    
    -- Timestamps
    detected_at INTEGER NOT NULL,
    confirmed_at INTEGER,
    executed_at INTEGER,
    
    -- Correlation
    correlation_id VARCHAR(50),
    
    -- Metadata
    created_at INTEGER NOT NULL
);

-- Indexes for trigger_events
CREATE INDEX IF NOT EXISTS idx_trigger_events_status 
    ON trigger_events(status);
CREATE INDEX IF NOT EXISTS idx_trigger_events_severity 
    ON trigger_events(severity);
CREATE INDEX IF NOT EXISTS idx_trigger_events_detected_at 
    ON trigger_events(detected_at);
CREATE INDEX IF NOT EXISTS idx_trigger_events_trigger_name 
    ON trigger_events(trigger_name);
CREATE INDEX IF NOT EXISTS idx_trigger_events_correlation_id 
    ON trigger_events(correlation_id);

-- ============================================================================
-- 4. Thread States Table
-- Stores thread status and performance metrics
-- ============================================================================
CREATE TABLE IF NOT EXISTS thread_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_name VARCHAR(50) UNIQUE NOT NULL,
    
    -- Status
    status VARCHAR(20) NOT NULL,   -- RUNNING/STOPPED/PAUSED/ERROR
    current_task TEXT,
    last_activity_at INTEGER,
    
    -- Performance Metrics
    total_runs INTEGER DEFAULT 0,
    avg_duration REAL,
    error_count INTEGER DEFAULT 0,
    
    -- Configuration
    config_json TEXT,
    
    -- Timestamps
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- Indexes for thread_states
CREATE INDEX IF NOT EXISTS idx_thread_states_status 
    ON thread_states(status);
CREATE INDEX IF NOT EXISTS idx_thread_states_thread_name 
    ON thread_states(thread_name);

-- ============================================================================
-- Sample Data (Optional - for testing)
-- ============================================================================

-- Insert sample trigger configs
INSERT OR IGNORE INTO trigger_configs (
    trigger_name, trigger_type, config_json, enabled, priority, cooldown_seconds,
    created_at, updated_at
) VALUES 
(
    'price_drop',
    'PRICE',
    '{"threshold": 0.03, "symbol": "BTCUSDT"}',
    1,
    90,
    300,
    strftime('%s', 'now') * 1000,
    strftime('%s', 'now') * 1000
),
(
    'var_warning',
    'RISK',
    '{"threshold": 0.05, "confidence": 0.95}',
    1,
    80,
    600,
    strftime('%s', 'now') * 1000,
    strftime('%s', 'now') * 1000
);

-- ============================================================================
-- End of Migration
-- ============================================================================