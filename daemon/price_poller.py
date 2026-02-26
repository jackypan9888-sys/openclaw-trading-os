"""价格轮询器。

定时拉取所有自选股价格 → 更新 price_cache → 触发预警引擎。
设计为独立进程友好：只依赖 db.store + market_data，不依赖 FastAPI。
"""
import sys
import os
import time
import logging
from pathlib import Path

# 添加路径以复用 dashboard 的 db 和 market 模块
ROOT = Path(__file__).parent.parent
WORKSPACE = Path.home() / ".openclaw" / "workspace"
MARKET_DIR = WORKSPACE / "muquant" / "market-query"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(MARKET_DIR))

from db.store import DataStore  # type: ignore

logger = logging.getLogger(__name__)


def _build_provider():
    try:
        from market_data import MarketDataProvider  # type: ignore
        return MarketDataProvider()
    except Exception as e:
        logger.warning(f"[PricePoller] market_data unavailable: {e}")
        return None


_store = DataStore()
_store.init_db()
_provider = _build_provider()


def poll_once(user_id: int | None = None):
    """
    执行一次完整轮询：
    1. 从 DB 获取所有被关注的 symbol
    2. 批量拉取价格
    3. 更新 price_cache
    4. 触发预警引擎
    返回 dict {symbol: price_data}
    """
    if _provider is None:
        logger.debug("[PricePoller] no provider, skip")
        return {}

    # 获取所有用户的自选股
    symbol_map = _store.get_all_watched_symbols()  # {symbol: [user_ids]}
    if not symbol_map:
        return {}

    prices: dict = {}
    for symbol in symbol_map:
        try:
            data = _provider.get_price(symbol)
            if data:
                prices[symbol] = data
        except Exception as e:
            logger.warning(f"[PricePoller] {symbol}: {e}")

    # 触发预警引擎（延迟导入，避免循环依赖）
    if prices:
        try:
            from alerts.alert_engine import check_alerts  # type: ignore
            for symbol, price_data in prices.items():
                user_ids = symbol_map.get(symbol, [])
                if user_ids:
                    check_alerts(_store, symbol, price_data, user_ids)
        except Exception as e:
            logger.warning(f"[PricePoller] alert check error: {e}")

    logger.info(f"[PricePoller] polled {len(prices)}/{len(symbol_map)} symbols")
    return prices
