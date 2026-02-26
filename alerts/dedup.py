"""预警去重 / 冷却管理。

基于 SQLite app_settings 实现简单的冷却窗口去重，
无需额外依赖，进程重启后冷却状态仍保留。
"""
import json
import time
from db.store import DataStore  # type: ignore


def _key(user_id: int, symbol: str, alert_type: str) -> str:
    return f"alert_cooldown:{user_id}:{symbol}:{alert_type}"


def should_send(store: DataStore, user_id: int, symbol: str, alert_type: str, cooldown_hours: float) -> bool:
    """
    返回 True 表示可以发送（未在冷却期内）。
    同时记录本次发送时间。
    """
    key = _key(user_id, symbol, alert_type)
    setting = store.get_app_setting(key)
    raw = setting.value if setting else None
    if raw:
        try:
            last_ts = float(raw)
            elapsed_hours = (time.time() - last_ts) / 3600
            if elapsed_hours < cooldown_hours:
                return False
        except (ValueError, TypeError):
            pass
    # 记录发送时间
    store.set_app_setting(key, str(time.time()))
    return True
