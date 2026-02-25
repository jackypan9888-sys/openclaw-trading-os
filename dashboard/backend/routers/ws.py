"""WebSocket routes."""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.state import demo_user, feed, provider, store

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
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
