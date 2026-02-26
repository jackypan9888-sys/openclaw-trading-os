-- OpenClaw Trading OS — SQLite Schema
-- trading_os.db
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id  TEXT UNIQUE NOT NULL,
    username     TEXT,
    tier         TEXT NOT NULL DEFAULT 'free',   -- 'free' | 'pro'
    quiet_from   TEXT,                            -- "22:00" local time
    quiet_to     TEXT,                            -- "07:00" local time
    timezone     TEXT NOT NULL DEFAULT 'UTC',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    alerts_today INTEGER NOT NULL DEFAULT 0,
    alerts_reset TEXT NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS user_watchlist (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    target_price    REAL,
    stop_price      REAL,
    alert_on_signal INTEGER NOT NULL DEFAULT 1,  -- 信号变化预警（Pro）
    alert_on_rumor  INTEGER NOT NULL DEFAULT 0,  -- 传言预警（Pro）
    last_signal     TEXT,                        -- 上次信号: BUY/HOLD/SELL
    added_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, symbol)
);

CREATE TABLE IF NOT EXISTS alerts_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    symbol       TEXT NOT NULL,
    alert_type   TEXT NOT NULL,   -- stop_hit|target_hit|signal_change|rumor|hot
    triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
    price        REAL,
    ai_summary   TEXT,
    delivered    INTEGER NOT NULL DEFAULT 0,
    message_id   INTEGER           -- Telegram message_id，用于后续 edit
);

CREATE TABLE IF NOT EXISTS dedup_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    symbol       TEXT NOT NULL,
    alert_type   TEXT NOT NULL,
    triggered_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analysis_cache (
    symbol       TEXT PRIMARY KEY,
    cached_at    TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    result_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_cache (
    symbol       TEXT PRIMARY KEY,
    price        REAL NOT NULL,
    change       REAL NOT NULL DEFAULT 0,
    change_pct   REAL NOT NULL DEFAULT 0,
    currency     TEXT NOT NULL DEFAULT 'USD',
    market_cap   REAL,
    pe_ratio     REAL,
    volume       REAL,
    cached_at    TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_price_cache_expires ON price_cache(expires_at);

CREATE TABLE IF NOT EXISTS strategies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    market       TEXT NOT NULL,             -- US/HK/Crypto
    symbol       TEXT NOT NULL,
    timeframe    TEXT NOT NULL DEFAULT '1d',
    config_json  TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE/PAUSED/ARCHIVED
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id     INTEGER REFERENCES strategies(id) ON DELETE SET NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,      -- BUY/SELL
    order_type      TEXT NOT NULL,      -- MARKET/LIMIT/STOP
    quantity        REAL NOT NULL,
    limit_price     REAL,
    stop_price      REAL,
    tif             TEXT NOT NULL DEFAULT 'DAY',    -- DAY/GTC/IOC
    status          TEXT NOT NULL DEFAULT 'NEW',    -- NEW/SUBMITTED/FILLED/CANCELED/REJECTED
    broker_order_id TEXT,
    reject_reason   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS positions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol         TEXT NOT NULL,
    quantity       REAL NOT NULL DEFAULT 0,
    avg_cost       REAL NOT NULL DEFAULT 0,
    last_price     REAL,
    market_value   REAL,
    unrealized_pnl REAL,
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, symbol)
);

CREATE TABLE IF NOT EXISTS risk_rules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    rule_type    TEXT NOT NULL,      -- max_position_pct/max_daily_loss/max_orders_per_day/...
    value_json   TEXT NOT NULL DEFAULT '{}',
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id  INTEGER REFERENCES strategies(id) ON DELETE SET NULL,
    run_type     TEXT NOT NULL,          -- analyze/plan/execute/reconcile
    input_json   TEXT NOT NULL DEFAULT '{}',
    output_json  TEXT,
    status       TEXT NOT NULL DEFAULT 'RUNNING',   -- RUNNING/SUCCESS/FAILED/SKIPPED
    error        TEXT,
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT
);

CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_watchlist_user     ON user_watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_user_date   ON alerts_log(user_id, triggered_at);
CREATE INDEX IF NOT EXISTS idx_dedup_lookup       ON dedup_log(user_id, symbol, alert_type, triggered_at);
CREATE INDEX IF NOT EXISTS idx_cache_expires      ON analysis_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_strategies_user_status ON strategies(user_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_user_status     ON orders(user_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_positions_user_symbol  ON positions(user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_risk_rules_user        ON risk_rules(user_id, enabled);
CREATE INDEX IF NOT EXISTS idx_agent_runs_user_type   ON agent_runs(user_id, run_type, started_at);
