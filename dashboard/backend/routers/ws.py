"""WebSocket routes."""
import asyncio
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.state import demo_user, feed, provider, store

router = APIRouter()


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    fixed_mode = _env_flag("TRADING_OS_FIXED_MODE", True)
    disable_ws = _env_flag("TRADING_OS_DISABLE_WS", fixed_mode)
    if disable_ws:
        await ws.accept()
        await ws.send_json({"type": "system", "message": "ws_disabled_by_fixed_mode"})
        await ws.close()
        return

    await feed.connect(ws)

    items = store.get_watchlist(demo_user.id)
    loop = asyncio.get_event_loop()
    for item in items:
        try:
            data = await loop.run_in_executor(None, provider.get_price, item.symbol)
            if data:
                await ws.send_json({"type": "price_tick", **data})
        except Exception:
            pass

    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        feed.disconnect(ws)
