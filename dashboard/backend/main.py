"""
OpenClaw Trading OS — Dashboard Backend
FastAPI server: REST API + WebSocket real-time price feed
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# ── 路径设置 ────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent          # skills/trading-os/
WORKSPACE = Path.home() / ".openclaw" / "workspace"
STATIC_DIR = ROOT / "dashboard" / "static"
SCRIPTS_DIR = WORKSPACE / "skills" / "stock-analysis" / "scripts"
MARKET_DIR = WORKSPACE / "muquant" / "market-query"

sys.path.insert(0, str(MARKET_DIR))
sys.path.insert(0, str(ROOT))

from market_data import MarketDataProvider          # type: ignore
from db.store import DataStore                      # type: ignore

# ── 应用初始化 ──────────────────────────────────────────────────
app = FastAPI(title="OpenClaw Trading OS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

provider = MarketDataProvider()
store = DataStore()
store.init_db()

# 确保 demo 用户存在
_demo_user = store.get_or_create_user("demo", "demo")

# ── WebSocket 管理器 ────────────────────────────────────────────
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
                        data = await loop.run_in_executor(
                            None, provider.get_price, symbol
                        )
                        if data:
                            await self.broadcast({"type": "price_tick", **data})
                    except Exception:
                        pass
                await self.broadcast({"type": "heartbeat"})
            await asyncio.sleep(60)


feed = PriceFeed()


@app.on_event("startup")
async def startup():
    asyncio.create_task(feed.start_polling())


# ── REST API ────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/price/{symbol}")
async def get_price(symbol: str):
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, provider.get_price, symbol.upper())
    return data or {"error": f"No data for {symbol}"}


@app.get("/api/chart/{symbol}")
async def get_chart(symbol: str, period: str = "5d"):
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, provider.get_chart_data, symbol.upper(), period
    )
    return data or {"error": f"No chart data for {symbol}"}


@app.get("/api/watchlist")
async def get_watchlist():
    items = store.get_watchlist(_demo_user.id)
    if not items:
        # 默认展示几个示范标的
        return []
    loop = asyncio.get_event_loop()
    result = []
    for item in items:
        price_data = await loop.run_in_executor(
            None, provider.get_price, item.symbol
        )
        if price_data:
            result.append({
                **price_data,
                "target_price": item.target_price,
                "stop_price": item.stop_price,
            })
    return result


@app.post("/api/watchlist/{symbol}")
async def add_watchlist(
    symbol: str,
    target_price: Optional[float] = None,
    stop_price: Optional[float] = None,
):
    ok, msg = store.add_watchlist(
        _demo_user.id, symbol.upper(), target_price, stop_price
    )
    if ok:
        # 立即推送新标的价格
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, provider.get_price, symbol.upper())
        if data:
            await feed.broadcast({"type": "price_tick", **data})
    return {"success": ok, "message": msg or "Added"}


@app.delete("/api/watchlist/{symbol}")
async def remove_watchlist(symbol: str):
    store.remove_watchlist(_demo_user.id, symbol.upper())
    return {"success": True}


@app.get("/api/analyze/{symbol}")
async def analyze(symbol: str):
    cached = store.get_cached_analysis(symbol.upper())
    if cached:
        return json.loads(cached)

    script = str(SCRIPTS_DIR / "analyze_stock.py")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["uv", "run", script, symbol.upper(), "--output", "json", "--fast"],
                capture_output=True,
                text=True,
                timeout=45,
            ),
        )
        if result.returncode == 0 and result.stdout.strip():
            store.set_cached_analysis(symbol.upper(), result.stdout, ttl_minutes=30)
            return json.loads(result.stdout)
        return {"error": result.stderr or "Analysis failed", "symbol": symbol}
    except subprocess.TimeoutExpired:
        return {"error": "Analysis timed out (45s)", "symbol": symbol}
    except Exception as e:
        return {"error": str(e), "symbol": symbol}


@app.get("/api/hot")
async def get_hot():
    script = str(SCRIPTS_DIR / "hot_scanner.py")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["python3", script, "--json"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(SCRIPTS_DIR),
            ),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return {"error": result.stderr or "Hot scan failed"}
    except Exception as e:
        return {"error": str(e)}


# ── WebSocket ───────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await feed.connect(ws)
    # 连接后立即推送当前自选股价格
    items = store.get_watchlist(_demo_user.id)
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
            # 保持连接，等待客户端消息（心跳 ping）
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        feed.disconnect(ws)
