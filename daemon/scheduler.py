"""市场时段感知调度器。

根据 US / HK / Crypto 市场开盘状态动态调整轮询频率：
- 盘中（任一市场开盘）: 60s
- 全部收盘:             300s
- Crypto 永远视为开盘
"""
from datetime import datetime, time as dtime
import pytz

MARKET_SCHEDULES = {
    "US": {
        "tz": "America/New_York",
        "open": dtime(9, 30),
        "close": dtime(16, 0),
    },
    "HK": {
        "tz": "Asia/Hong_Kong",
        "open": dtime(9, 30),
        "close": dtime(16, 0),
    },
}

# 判断标的属于哪个市场
def classify_symbol(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith(".HK"):
        return "HK"
    if s.endswith("-USD") or s.endswith("-USDT"):
        return "CRYPTO"
    return "US"


def is_market_open(market: str) -> bool:
    """检查指定市场当前是否处于交易时段。"""
    if market == "CRYPTO":
        return True
    cfg = MARKET_SCHEDULES.get(market)
    if not cfg:
        return False
    tz = pytz.timezone(cfg["tz"])
    now = datetime.now(tz)
    if now.weekday() >= 5:      # 周六/周日休市
        return False
    t = now.time().replace(second=0, microsecond=0)
    return cfg["open"] <= t < cfg["close"]


def get_poll_interval(symbols: list[str]) -> int:
    """根据当前自选股中是否有开盘市场决定轮询频率（秒）。"""
    markets = {classify_symbol(s) for s in symbols}
    for m in markets:
        if is_market_open(m):
            return 60
    return 300


def market_status_summary(symbols: list[str]) -> dict:
    """返回各市场开盘状态摘要，供日志/API 使用。"""
    markets = {classify_symbol(s) for s in symbols}
    return {m: is_market_open(m) for m in sorted(markets)}
