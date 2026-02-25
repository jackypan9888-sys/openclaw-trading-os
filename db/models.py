from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    id: int
    telegram_id: str
    username: Optional[str]
    tier: str               # 'free' | 'pro'
    quiet_from: Optional[str]   # "22:00"
    quiet_to: Optional[str]     # "07:00"
    timezone: str
    created_at: str
    alerts_today: int
    alerts_reset: str

@dataclass
class WatchlistItem:
    id: int
    user_id: int
    symbol: str
    target_price: Optional[float]
    stop_price: Optional[float]
    alert_on_signal: bool
    alert_on_rumor: bool
    last_signal: Optional[str]
    added_at: str

@dataclass
class AlertLog:
    id: int
    user_id: Optional[int]
    symbol: str
    alert_type: str
    triggered_at: str
    price: Optional[float]
    ai_summary: Optional[str]
    delivered: bool
    message_id: Optional[int]

# 预警冷却时间（小时）
ALERT_COOLDOWN = {
    'stop_hit':      0,   # 无冷却，始终触发
    'target_hit':    24,
    'signal_change': 4,
    'rumor':         12,
    'hot':           24,
}

# 层级权限配置
TIER_LIMITS = {
    'free': {
        'max_symbols':       5,
        'alert_types':       ['stop_hit', 'target_hit'],
        'ai_summary':        False,
        'max_alerts_per_day': 10,
    },
    'pro': {
        'max_symbols':       999,
        'alert_types':       ['stop_hit', 'target_hit', 'signal_change', 'rumor', 'hot'],
        'ai_summary':        True,
        'max_alerts_per_day': 100,
    },
}
