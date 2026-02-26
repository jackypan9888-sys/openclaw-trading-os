"""Watchlist routes."""
from typing import Optional

from fastapi import APIRouter

from core.state import demo_user, feed, provider, store

router = APIRouter(prefix="/api")


@router.get("/watchlist")
async def get_watchlist():
    items = store.get_watchlist(demo_user.id)
    if not items:
        return []

    result = []
    for item in items:
        try:
            price_data = provider.get_price(item.symbol)
        except Exception:
            price_data = None
        if price_data:
            row = {**price_data}
        else:
            # Keep watchlist entries visible even when live quote fetch fails.
            row = {
                "symbol": item.symbol,
                "name": item.symbol,
                "price": None,
                "currency": "",
                "change": 0,
                "change_pct": 0,
                "market_state": "UNAVAILABLE",
                "timestamp": None,
            }

        result.append({
            **row,
            "target_price": item.target_price,
            "stop_price": item.stop_price,
        })
    return result


@router.post("/watchlist/{symbol}")
async def add_watchlist(symbol: str, target_price: Optional[float] = None, stop_price: Optional[float] = None):
    ok, msg = store.add_watchlist(demo_user.id, symbol.upper(), target_price, stop_price)
    if ok:
        try:
            data = provider.get_price(symbol.upper())
        except Exception:
            data = None
        if data:
            await feed.broadcast({"type": "price_tick", **data})
    return {"success": ok, "message": msg or "Added"}


@router.delete("/watchlist/{symbol}")
async def remove_watchlist(symbol: str):
    store.remove_watchlist(demo_user.id, symbol.upper())
    return {"success": True}
