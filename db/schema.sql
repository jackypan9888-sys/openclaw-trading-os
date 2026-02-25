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

CREATE INDEX IF NOT EXISTS idx_watchlist_user     ON user_watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_user_date   ON alerts_log(user_id, triggered_at);
CREATE INDEX IF NOT EXISTS idx_dedup_lookup       ON dedup_log(user_id, symbol, alert_type, triggered_at);
CREATE INDEX IF NOT EXISTS idx_cache_expires      ON analysis_cache(expires_at);
