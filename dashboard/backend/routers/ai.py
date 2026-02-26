"""AI-related routes."""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from services.agent_profile_service import load_agent_profile, update_agent_profile
from services.ai_config_service import get_masked_ai_config, update_ai_config
from services.analysis_service import analyze_symbol, chat_dispatch, stream_chat_with_agent

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


@router.post("/chat/stream")
async def chat_stream(request: dict):
    """
    流式聊天 SSE 端点。
    分析类请求（股票/加密）走本地分析后模拟流式；
    一般对话走 OpenClaw WebSocket 真实流式。
    前端用 fetch + ReadableStream 消费。
    """
    message = request.get("message", "").strip()
    context = request.get("context", {})

    if not message:
        async def _empty():
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    async def generate():
        try:
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
            async for chunk in stream_chat_with_agent(message, context):
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
