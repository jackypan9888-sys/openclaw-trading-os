"""AI-related routes."""
from fastapi import APIRouter

from services.agent_profile_service import load_agent_profile, update_agent_profile
from services.ai_config_service import get_masked_ai_config, update_ai_config
from services.analysis_service import analyze_symbol, chat_dispatch

router = APIRouter(prefix="/api")


@router.get("/analyze/{symbol}")
async def analyze(symbol: str):
    return await analyze_symbol(symbol)


@router.get("/ai/config")
async def get_ai_config():
    return get_masked_ai_config()


@router.post("/ai/config")
async def set_ai_config(request: dict):
    return update_ai_config(request)


@router.get("/agent/config")
async def get_agent_config():
    return load_agent_profile()


@router.post("/agent/config")
async def set_agent_config(request: dict):
    return update_agent_profile(request)


@router.post("/chat")
async def chat(request: dict):
    return await chat_dispatch(request)
