"""Watchlist routes."""
import asyncio
from typing import Optional

from fastapi import APIRouter

from core.state import demo_user, feed, provider, store

router = APIRouter(prefix="/api")


@router.get("/watchlist")
async def get_watchlist():
    items = store.get_watchlist(demo_user.id)
    if not items:
        return []

    loop = asyncio.get_event_loop()
    result = []
    for item in items:
        price_data = await loop.run_in_executor(None, provider.get_price, item.symbol)
        if price_data:
            result.append({
                **price_data,
                "target_price": item.target_price,
                "stop_price": item.stop_price,
            })
    return result


@router.post("/watchlist/{symbol}")
async def add_watchlist(symbol: str, target_price: Optional[float] = None, stop_price: Optional[float] = None):
    ok, msg = store.add_watchlist(demo_user.id, symbol.upper(), target_price, stop_price)
    if ok:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, provider.get_price, symbol.upper())
        if data:
            await feed.broadcast({"type": "price_tick", **data})
    return {"success": ok, "message": msg or "Added"}


@router.delete("/watchlist/{symbol}")
async def remove_watchlist(symbol: str):
    store.remove_watchlist(demo_user.id, symbol.upper())
    return {"success": True}
