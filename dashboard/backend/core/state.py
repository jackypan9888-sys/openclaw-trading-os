"""Shared application state (provider, datastore, feed)."""
import asyncio
import sys
from fastapi import WebSocket

from core.paths import ROOT, MARKET_DIR

sys.path.insert(0, str(MARKET_DIR))
sys.path.insert(0, str(ROOT))

from db.store import DataStore  # type: ignore

try:
    from market_data import MarketDataProvider  # type: ignore
except Exception:
    class MarketDataProvider:  # type: ignore
        """Fallback provider to keep app bootable without external market deps."""

        def get_price(self, symbol: str):
            return None

        def get_chart_data(self, symbol: str, period: str):
            return None


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
        """后台任务：每 60s 推送所有自选股价格"""
        self.running = True
        while self.running:
            if self.clients:
                symbols = list(store.get_all_watched_symbols().keys())
                for symbol in symbols:
                    try:
                        loop = asyncio.get_event_loop()
                        data = await loop.run_in_executor(None, provider.get_price, symbol)
                        if data:
                            await self.broadcast({"type": "price_tick", **data})
                    except Exception:
                        pass
                await self.broadcast({"type": "heartbeat"})
            await asyncio.sleep(60)


provider = MarketDataProvider()
store = DataStore()
store.init_db()

demo_user = store.get_or_create_user("demo", "demo")
feed = PriceFeed()
