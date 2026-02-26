"""Shared application state (provider, datastore, feed)."""
import asyncio
import os
import sys
from fastapi import WebSocket

from core.paths import ROOT, MARKET_DIR

sys.path.insert(0, str(MARKET_DIR))
sys.path.insert(0, str(ROOT))

from db.store import DataStore  # type: ignore

def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


FIXED_MODE = _env_flag("TRADING_OS_FIXED_MODE", True)
USE_CACHED_PROVIDER = _env_flag("TRADING_OS_USE_CACHED_PROVIDER", not FIXED_MODE)


class NullMarketDataProvider:
    """Fallback provider to keep app bootable without external market deps."""

    def get_price(self, symbol: str, timeout: float = 8.0):
        return None

    def get_chart_data(self, symbol: str, period: str):
        return None


class SimpleProviderAdapter:
    """Wrapper around lightweight provider to normalize call signatures."""

    def __init__(self, raw_provider):
        self._provider = raw_provider

    def get_price(self, symbol: str, timeout: float = 8.0):
        return self._provider.get_price(symbol)

    def get_chart_data(self, symbol: str, period: str):
        return self._provider.get_chart_data(symbol, period)


class CachedProviderAdapter:
    """Wrapper around cached provider with controlled warmup behavior."""

    def __init__(self, raw_provider):
        self._provider = raw_provider
        if _env_flag("TRADING_OS_PRELOAD_POPULAR", False):
            try:
                self._provider.preload_popular_stocks()
            except Exception as e:
                print(f"[State] preload failed: {e}")

    def get_price(self, symbol: str, timeout: float = 8.0):
        return self._provider.get_price(symbol, timeout=timeout)

    def get_chart_data(self, symbol: str, period: str):
        return self._provider.get_chart_data(symbol, period)

    async def get_prices_parallel(self, symbols, timeout: float = 10.0):
        return await self._provider.get_prices_parallel(symbols, timeout=timeout)

    def clear_expired_cache(self):
        return self._provider.clear_expired_cache()


def build_market_provider():
    try:
        from market_data import CachedMarketDataProvider, MarketDataProvider as RawMarketProvider  # type: ignore
        if USE_CACHED_PROVIDER:
            print("[State] provider=cached")
            return CachedProviderAdapter(CachedMarketDataProvider())
        print("[State] provider=simple")
        return SimpleProviderAdapter(RawMarketProvider())
    except Exception as e:
        print(f"[State] Failed to load market provider: {e}")
        return NullMarketDataProvider()


class PriceFeed:
    def __init__(self):
        self.clients: list[WebSocket] = []
        self.running = False

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.clients:
            self.clients.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def start_polling(self):
        """后台任务：定时推送所有自选股价格。"""
        self.running = True
        interval_sec = int(os.getenv("TRADING_OS_POLL_INTERVAL_SEC", "60"))

        await asyncio.sleep(1)

        while self.running:
            if self.clients:
                symbols = list(store.get_all_watched_symbols().keys())

                if symbols and hasattr(provider, "get_prices_parallel"):
                    try:
                        results = await provider.get_prices_parallel(symbols, timeout=15.0)
                        for _, data in results.items():
                            if data:
                                await self.broadcast({"type": "price_tick", **data})
                    except Exception as e:
                        print(f"[PriceFeed] Parallel fetch error: {e}")
                        for symbol in symbols:
                            try:
                                data = provider.get_price(symbol, timeout=5.0)
                                if data:
                                    await self.broadcast({"type": "price_tick", **data})
                            except Exception:
                                pass
                else:
                    for symbol in symbols:
                        try:
                            data = provider.get_price(symbol, timeout=5.0)
                            if data:
                                await self.broadcast({"type": "price_tick", **data})
                        except Exception:
                            pass
                
                await self.broadcast({"type": "heartbeat"})
            
            if hasattr(provider, "clear_expired_cache"):
                try:
                    cleared = provider.clear_expired_cache()
                    if cleared > 0:
                        print(f"[PriceFeed] Cleared {cleared} expired cache entries")
                except Exception:
                    pass

            await asyncio.sleep(max(15, interval_sec))


# 初始化全局对象
provider = build_market_provider()
store = DataStore()
store.init_db()

demo_user = store.get_or_create_user("demo", "demo")
feed = PriceFeed()
