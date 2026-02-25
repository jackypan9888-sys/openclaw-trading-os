import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional

from .models import (
    User,
    WatchlistItem,
    AlertLog,
    Strategy,
    Order,
    Position,
    RiskRule,
    AgentRun,
    AppSetting,
    TIER_LIMITS,
)

DB_PATH = os.path.expanduser("~/.openclaw/trading-os/trading_os.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


class DataStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_db(self):
        with open(SCHEMA_PATH) as f:
            schema = f.read()
        with self._conn() as conn:
            conn.executescript(schema)

    # ── 用户 ──────────────────────────────────────────────────

    def get_or_create_user(self, telegram_id: str, username: str = None) -> User:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_id=?", (str(telegram_id),)
            ).fetchone()
            if row:
                return User(**dict(row))
            conn.execute(
                "INSERT INTO users(telegram_id, username) VALUES(?,?)",
                (str(telegram_id), username),
            )
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_id=?", (str(telegram_id),)
            ).fetchone()
            return User(**dict(row))

    def get_user_by_telegram(self, telegram_id: str) -> Optional[User]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_id=?", (str(telegram_id),)
            ).fetchone()
            return User(**dict(row)) if row else None

    def set_user_tier(self, telegram_id: str, tier: str):
        """手动升级用户层级（收款后调用）"""
        with self._conn() as conn:
            conn.execute(
                "UPDATE users SET tier=? WHERE telegram_id=?",
                (tier, str(telegram_id)),
            )

    def set_quiet_hours(self, user_id: int, quiet_from: str, quiet_to: str, timezone: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE users SET quiet_from=?, quiet_to=?, timezone=? WHERE id=?",
                (quiet_from, quiet_to, timezone, user_id),
            )

    # ── 自选股 ────────────────────────────────────────────────

    def add_watchlist(
        self,
        user_id: int,
        symbol: str,
        target_price: float = None,
        stop_price: float = None,
    ) -> tuple[bool, str]:
        """
        Returns (True, "") on success.
        Returns (False, reason) if limit exceeded or duplicate.
        """
        user = self._get_user_by_id(user_id)
        limit = TIER_LIMITS[user.tier]
        current = self.get_watchlist(user_id)
        if len(current) >= limit["max_symbols"]:
            return False, f"已达上限 {limit['max_symbols']} 只（{user.tier} 套餐）"
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO user_watchlist(user_id,symbol,target_price,stop_price) VALUES(?,?,?,?)",
                    (user_id, symbol.upper(), target_price, stop_price),
                )
            return True, ""
        except sqlite3.IntegrityError:
            return False, f"{symbol.upper()} 已在自选股列表中"

    def remove_watchlist(self, user_id: int, symbol: str):
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM user_watchlist WHERE user_id=? AND symbol=?",
                (user_id, symbol.upper()),
            )

    def get_watchlist(self, user_id: int) -> list[WatchlistItem]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM user_watchlist WHERE user_id=? ORDER BY added_at",
                (user_id,),
            ).fetchall()
            return [WatchlistItem(**dict(r)) for r in rows]

    def get_watchlist_item(self, user_id: int, symbol: str) -> Optional[WatchlistItem]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM user_watchlist WHERE user_id=? AND symbol=?",
                (user_id, symbol.upper()),
            ).fetchone()
            return WatchlistItem(**dict(row)) if row else None

    def get_all_watched_symbols(self) -> dict[str, list[int]]:
        """返回 {symbol: [user_id, ...]}，跨所有用户去重汇总，供 Daemon 批量查价用"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT symbol, user_id FROM user_watchlist"
            ).fetchall()
        result: dict[str, list[int]] = {}
        for row in rows:
            result.setdefault(row["symbol"], []).append(row["user_id"])
        return result

    def update_last_signal(self, user_id: int, symbol: str, signal: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE user_watchlist SET last_signal=? WHERE user_id=? AND symbol=?",
                (signal, user_id, symbol.upper()),
            )

    # ── 预警日志 ──────────────────────────────────────────────

    def log_alert(
        self,
        user_id: int,
        symbol: str,
        alert_type: str,
        price: float = None,
        ai_summary: str = None,
    ) -> int:
        """插入预警记录并更新今日计数，返回 alert_id"""
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO alerts_log(user_id,symbol,alert_type,price,ai_summary) VALUES(?,?,?,?,?)",
                (user_id, symbol, alert_type, price, ai_summary),
            )
            conn.execute(
                """UPDATE users SET
                   alerts_today = CASE WHEN alerts_reset = date('now')
                                       THEN alerts_today + 1 ELSE 1 END,
                   alerts_reset = date('now')
                   WHERE id=?""",
                (user_id,),
            )
            return cur.lastrowid

    def mark_delivered(self, alert_id: int, message_id: int = None):
        with self._conn() as conn:
            conn.execute(
                "UPDATE alerts_log SET delivered=1, message_id=? WHERE id=?",
                (message_id, alert_id),
            )

    def update_ai_summary(self, alert_id: int, ai_summary: str):
        """AI 分析完成后更新同一条记录"""
        with self._conn() as conn:
            conn.execute(
                "UPDATE alerts_log SET ai_summary=? WHERE id=?",
                (ai_summary, alert_id),
            )

    def get_today_alerts(self, user_id: int) -> list[AlertLog]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts_log "
                "WHERE user_id=? AND date(triggered_at)=date('now') "
                "ORDER BY triggered_at DESC",
                (user_id,),
            ).fetchall()
            return [AlertLog(**dict(r)) for r in rows]

    def can_send_alert(self, user_id: int) -> bool:
        user = self._get_user_by_id(user_id)
        # 如果日期已过，计数视为 0
        if user.alerts_reset != datetime.utcnow().strftime("%Y-%m-%d"):
            return True
        return user.alerts_today < TIER_LIMITS[user.tier]["max_alerts_per_day"]

    def can_use_alert_type(self, user_id: int, alert_type: str) -> bool:
        user = self._get_user_by_id(user_id)
        return alert_type in TIER_LIMITS[user.tier]["alert_types"]

    def has_ai_summary(self, user_id: int) -> bool:
        user = self._get_user_by_id(user_id)
        return TIER_LIMITS[user.tier]["ai_summary"]

    # ── 去重冷却 ──────────────────────────────────────────────

    def check_dedup(
        self, user_id: int, symbol: str, alert_type: str, cooldown_hours: int
    ) -> bool:
        """True = 冷却已过，可以发；False = 冷却中，跳过"""
        if cooldown_hours == 0:
            return True  # stop_hit 无冷却
        cutoff = (datetime.utcnow() - timedelta(hours=cooldown_hours)).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                """SELECT id FROM dedup_log
                   WHERE user_id=? AND symbol=? AND alert_type=?
                   AND triggered_at > ?
                   ORDER BY triggered_at DESC LIMIT 1""",
                (user_id, symbol, alert_type, cutoff),
            ).fetchone()
            return row is None

    def record_dedup(self, user_id: int, symbol: str, alert_type: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO dedup_log(user_id,symbol,alert_type) VALUES(?,?,?)",
                (user_id, symbol, alert_type),
            )

    # ── 分析缓存 ──────────────────────────────────────────────

    def get_cached_analysis(self, symbol: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT result_json FROM analysis_cache "
                "WHERE symbol=? AND expires_at > datetime('now')",
                (symbol.upper(),),
            ).fetchone()
            return row["result_json"] if row else None

    def set_cached_analysis(self, symbol: str, result_json: str, ttl_minutes: int = 30):
        expires = (datetime.utcnow() + timedelta(minutes=ttl_minutes)).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO analysis_cache"
                "(symbol,cached_at,expires_at,result_json) VALUES(?,datetime('now'),?,?)",
                (symbol.upper(), expires, result_json),
            )

    def clear_expired_cache(self):
        with self._conn() as conn:
            conn.execute("DELETE FROM analysis_cache WHERE expires_at <= datetime('now')")

    # ── 交易域模型（Phase 2） ───────────────────────────────────

    def create_strategy(
        self,
        user_id: int,
        name: str,
        market: str,
        symbol: str,
        config_json: str = "{}",
        timeframe: str = "1d",
        status: str = "ACTIVE",
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO strategies(user_id,name,market,symbol,timeframe,config_json,status)"
                " VALUES(?,?,?,?,?,?,?)",
                (user_id, name, market, symbol.upper(), timeframe, config_json, status),
            )
            return cur.lastrowid

    def list_strategies(self, user_id: int, status: Optional[str] = None) -> list[Strategy]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM strategies WHERE user_id=? AND status=? ORDER BY updated_at DESC",
                    (user_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM strategies WHERE user_id=? ORDER BY updated_at DESC",
                    (user_id,),
                ).fetchall()
            return [Strategy(**dict(r)) for r in rows]

    def create_order(
        self,
        user_id: int,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        strategy_id: int = None,
        limit_price: float = None,
        stop_price: float = None,
        tif: str = "DAY",
        status: str = "NEW",
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO orders(user_id,strategy_id,symbol,side,order_type,quantity,limit_price,stop_price,tif,status)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    user_id,
                    strategy_id,
                    symbol.upper(),
                    side.upper(),
                    order_type.upper(),
                    quantity,
                    limit_price,
                    stop_price,
                    tif.upper(),
                    status.upper(),
                ),
            )
            return cur.lastrowid

    def update_order_status(
        self,
        order_id: int,
        status: str,
        broker_order_id: str = None,
        reject_reason: str = None,
    ):
        with self._conn() as conn:
            conn.execute(
                "UPDATE orders SET status=?, broker_order_id=COALESCE(?, broker_order_id), "
                "reject_reason=COALESCE(?, reject_reason), updated_at=datetime('now') WHERE id=?",
                (status.upper(), broker_order_id, reject_reason, order_id),
            )

    def list_orders(self, user_id: int, status: Optional[str] = None, limit: int = 100) -> list[Order]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE user_id=? AND status=? ORDER BY created_at DESC LIMIT ?",
                    (user_id, status.upper(), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_order_by_id(self, order_id: int) -> Optional[Order]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            return Order(**dict(row)) if row else None

    def count_orders_today(self, user_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(1) AS cnt FROM orders "
                "WHERE user_id=? AND date(created_at)=date('now') AND status != 'REJECTED'",
                (user_id,),
            ).fetchone()
            return int(row["cnt"] if row else 0)

    def upsert_position(
        self,
        user_id: int,
        symbol: str,
        quantity: float,
        avg_cost: float,
        last_price: float = None,
    ):
        market_value = (quantity * last_price) if last_price is not None else None
        unrealized_pnl = (
            (last_price - avg_cost) * quantity if last_price is not None else None
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO positions(user_id,symbol,quantity,avg_cost,last_price,market_value,unrealized_pnl)"
                " VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(user_id,symbol) DO UPDATE SET "
                "quantity=excluded.quantity, avg_cost=excluded.avg_cost, "
                "last_price=excluded.last_price, market_value=excluded.market_value, "
                "unrealized_pnl=excluded.unrealized_pnl, updated_at=datetime('now')",
                (
                    user_id,
                    symbol.upper(),
                    quantity,
                    avg_cost,
                    last_price,
                    market_value,
                    unrealized_pnl,
                ),
            )

    def get_open_positions(self, user_id: int) -> list[Position]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE user_id=? AND quantity != 0 ORDER BY symbol",
                (user_id,),
            ).fetchall()
            return [Position(**dict(r)) for r in rows]

    def get_position(self, user_id: int, symbol: str) -> Optional[Position]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE user_id=? AND symbol=?",
                (user_id, symbol.upper()),
            ).fetchone()
            return Position(**dict(row)) if row else None

    def create_risk_rule(
        self,
        user_id: int,
        name: str,
        rule_type: str,
        value_json: str = "{}",
        enabled: bool = True,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO risk_rules(user_id,name,rule_type,value_json,enabled) VALUES(?,?,?,?,?)",
                (user_id, name, rule_type, value_json, int(enabled)),
            )
            return cur.lastrowid

    def list_risk_rules(self, user_id: int, enabled_only: bool = True) -> list[RiskRule]:
        with self._conn() as conn:
            if enabled_only:
                rows = conn.execute(
                    "SELECT * FROM risk_rules WHERE user_id=? AND enabled=1 ORDER BY updated_at DESC",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM risk_rules WHERE user_id=? ORDER BY updated_at DESC",
                    (user_id,),
                ).fetchall()
            return [RiskRule(**dict(r)) for r in rows]

    def record_agent_run(
        self,
        user_id: int,
        run_type: str,
        input_json: str = "{}",
        strategy_id: int = None,
        status: str = "RUNNING",
        output_json: str = None,
        error: str = None,
        finished: bool = False,
    ) -> int:
        finished_at = datetime.utcnow().isoformat() if finished else None
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO agent_runs(user_id,strategy_id,run_type,input_json,output_json,status,error,finished_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    user_id,
                    strategy_id,
                    run_type,
                    input_json,
                    output_json,
                    status,
                    error,
                    finished_at,
                ),
            )
            return cur.lastrowid

    def update_agent_run(
        self,
        run_id: int,
        status: str,
        output_json: str = None,
        error: str = None,
    ):
        with self._conn() as conn:
            conn.execute(
                "UPDATE agent_runs SET status=?, output_json=COALESCE(?,output_json), "
                "error=COALESCE(?,error), finished_at=datetime('now') WHERE id=?",
                (status, output_json, error, run_id),
            )

    def list_recent_agent_runs(self, user_id: int, limit: int = 50) -> list[AgentRun]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_runs WHERE user_id=? ORDER BY started_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [AgentRun(**dict(r)) for r in rows]

    # ── 系统配置 ──────────────────────────────────────────────

    def get_app_setting(self, key: str) -> Optional[AppSetting]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM app_settings WHERE key=?",
                (key,),
            ).fetchone()
            return AppSetting(**dict(row)) if row else None

    def set_app_setting(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
                (key, value),
            )

    def get_execution_mode(self) -> str:
        row = self.get_app_setting("execution_mode")
        return (row.value if row else "PAPER").upper()

    def set_execution_mode(self, mode: str):
        self.set_app_setting("execution_mode", mode.upper())

    def is_kill_switch_on(self) -> bool:
        row = self.get_app_setting("kill_switch")
        if not row:
            return False
        return row.value.lower() in {"1", "true", "on", "yes"}

    def set_kill_switch(self, enabled: bool):
        self.set_app_setting("kill_switch", "1" if enabled else "0")

    # ── 内部工具 ──────────────────────────────────────────────

    def _get_user_by_id(self, user_id: int) -> User:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"User id={user_id} not found")
            return User(**dict(row))
