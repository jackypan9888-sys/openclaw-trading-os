"""OpenClaw Trading OS dashboard application factory."""
import asyncio
import os
import sys
from pathlib import Path

# 确保可以导入本地模块
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.paths import STATIC_DIR
from core.state import feed
from routers.ai import router as ai_router
from routers.market import api_router as market_api_router
from routers.market import router as market_router
from routers.trading import router as trading_router
from routers.watchlist import router as watchlist_router
from routers.ws import router as ws_router

app = FastAPI(title="OpenClaw Trading OS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(market_router)
app.include_router(market_api_router)
app.include_router(watchlist_router)
app.include_router(ai_router)
app.include_router(trading_router)
app.include_router(ws_router)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


@app.on_event("startup")
async def startup():
    fixed_mode = _env_flag("TRADING_OS_FIXED_MODE", True)
    disable_polling = _env_flag("TRADING_OS_DISABLE_POLLING", fixed_mode)
    if not disable_polling:
        asyncio.create_task(feed.start_polling())
