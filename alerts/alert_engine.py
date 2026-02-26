"""预警引擎。

接收价格数据，对照每个用户的自选股止损/目标价设置，触发预警并写入 DB。
设计原则：先写 DB，再异步通知（Telegram / AI 分析）。
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from db.models import ALERT_COOLDOWN, TIER_LIMITS  # type: ignore
from db.store import DataStore  # type: ignore
from alerts.dedup import should_send  # type: ignore

logger = logging.getLogger(__name__)


def check_alerts(store: DataStore, symbol: str, price_data: dict, user_ids: list[int]):
    """
    对一个 symbol 的最新价格，逐用户检查触发条件。

    触发顺序（优先级由高到低）：
      1. stop_hit   — 跌破止损价（无冷却，最高优先）
      2. target_hit — 达到目标价（24h 冷却）
    """
    price = float(price_data.get("price") or 0)
    if price <= 0:
        return

    for user_id in user_ids:
        try:
            item = store.get_watchlist_item(user_id, symbol)
            if not item:
                continue

            # 权限检查
            allowed_types = TIER_LIMITS.get("free", {}).get("alert_types", [])
            try:
                user = store._get_user_by_id(user_id)
                allowed_types = TIER_LIMITS.get(user.tier, TIER_LIMITS["free"])["alert_types"]
            except Exception:
                pass

            # 1. 止损触发（无冷却）
            if (
                "stop_hit" in allowed_types
                and item.stop_price
                and price <= float(item.stop_price)
            ):
                cooldown = ALERT_COOLDOWN.get("stop_hit", 0)
                if cooldown == 0 or should_send(store, user_id, symbol, "stop_hit", cooldown or 0.5):
                    _fire(store, user_id, symbol, "stop_hit", price, item.stop_price)

            # 2. 目标价触发
            elif (
                "target_hit" in allowed_types
                and item.target_price
                and price >= float(item.target_price)
            ):
                if should_send(store, user_id, symbol, "target_hit", ALERT_COOLDOWN.get("target_hit", 24)):
                    _fire(store, user_id, symbol, "target_hit", price, item.target_price)

        except Exception as e:
            logger.warning(f"[AlertEngine] user={user_id} {symbol}: {e}")


def _fire(store: DataStore, user_id: int, symbol: str, alert_type: str, price: float, trigger_price: float):
    """记录预警到 DB，并打印日志（Telegram 推送在后续模块实现）。"""
    if not store.can_send_alert(user_id):
        logger.debug(f"[AlertEngine] daily limit reached for user {user_id}")
        return

    try:
        alert_id = store.log_alert(
            user_id=user_id,
            symbol=symbol,
            alert_type=alert_type,
            price=price,
        )
        store.mark_delivered(alert_id)

        emoji = "🛑" if alert_type == "stop_hit" else "🎯"
        direction = "跌破止损" if alert_type == "stop_hit" else "达到目标"
        logger.info(
            f"{emoji} [{alert_type.upper()}] {symbol} "
            f"当前价 ${price:.2f} {direction} ${trigger_price:.2f} "
            f"(user={user_id}, alert_id={alert_id})"
        )
    except Exception as e:
        logger.error(f"[AlertEngine] _fire failed: {e}")
