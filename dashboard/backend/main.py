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


# 热门股票列表（用于搜索提示）
POPULAR_SYMBOLS = [
    # 美股科技
    {"symbol": "AAPL", "name": "Apple Inc.", "market": "US"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "market": "US"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "market": "US"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "market": "US"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "market": "US"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "market": "US"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "market": "US"},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "market": "US"},
    {"symbol": "NFLX", "name": "Netflix Inc.", "market": "US"},
    {"symbol": "CRM", "name": "Salesforce Inc.", "market": "US"},
    {"symbol": "INTC", "name": "Intel Corporation", "market": "US"},
    {"symbol": "ORCL", "name": "Oracle Corporation", "market": "US"},
    {"symbol": "ADBE", "name": "Adobe Inc.", "market": "US"},
    {"symbol": "CSCO", "name": "Cisco Systems", "market": "US"},
    {"symbol": "QCOM", "name": "Qualcomm Inc.", "market": "US"},
    # 美股金融
    {"symbol": "JPM", "name": "JPMorgan Chase", "market": "US"},
    {"symbol": "V", "name": "Visa Inc.", "market": "US"},
    {"symbol": "MA", "name": "Mastercard Inc.", "market": "US"},
    {"symbol": "BAC", "name": "Bank of America", "market": "US"},
    {"symbol": "GS", "name": "Goldman Sachs", "market": "US"},
    # 美股消费
    {"symbol": "WMT", "name": "Walmart Inc.", "market": "US"},
    {"symbol": "KO", "name": "Coca-Cola Company", "market": "US"},
    {"symbol": "PEP", "name": "PepsiCo Inc.", "market": "US"},
    {"symbol": "MCD", "name": "McDonald's Corp.", "market": "US"},
    {"symbol": "NKE", "name": "Nike Inc.", "market": "US"},
    {"symbol": "SBUX", "name": "Starbucks Corp.", "market": "US"},
    # 美股其他
    {"symbol": "DIS", "name": "Walt Disney Company", "market": "US"},
    {"symbol": "BA", "name": "Boeing Company", "market": "US"},
    {"symbol": "XOM", "name": "Exxon Mobil", "market": "US"},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "market": "US"},
    {"symbol": "PFE", "name": "Pfizer Inc.", "market": "US"},
    {"symbol": "UNH", "name": "UnitedHealth Group", "market": "US"},
    # 港股
    {"symbol": "0700.HK", "name": "腾讯控股", "market": "HK"},
    {"symbol": "9988.HK", "name": "阿里巴巴", "market": "HK"},
    {"symbol": "9618.HK", "name": "京东集团", "market": "HK"},
    {"symbol": "3690.HK", "name": "美团", "market": "HK"},
    {"symbol": "1810.HK", "name": "小米集团", "market": "HK"},
    {"symbol": "9888.HK", "name": "百度集团", "market": "HK"},
    {"symbol": "2318.HK", "name": "中国平安", "market": "HK"},
    {"symbol": "0941.HK", "name": "中国移动", "market": "HK"},
    {"symbol": "1299.HK", "name": "友邦保险", "market": "HK"},
    {"symbol": "0005.HK", "name": "汇丰控股", "market": "HK"},
    {"symbol": "2020.HK", "name": "安踏体育", "market": "HK"},
    {"symbol": "9999.HK", "name": "网易", "market": "HK"},
    {"symbol": "0388.HK", "name": "香港交易所", "market": "HK"},
    {"symbol": "2382.HK", "name": "舜宇光学", "market": "HK"},
    {"symbol": "1211.HK", "name": "比亚迪股份", "market": "HK"},
    # 加密货币
    {"symbol": "BTC-USD", "name": "Bitcoin 比特币", "market": "Crypto"},
    {"symbol": "ETH-USD", "name": "Ethereum 以太坊", "market": "Crypto"},
    {"symbol": "BNB-USD", "name": "BNB 币安币", "market": "Crypto"},
    {"symbol": "SOL-USD", "name": "Solana", "market": "Crypto"},
    {"symbol": "XRP-USD", "name": "Ripple 瑞波币", "market": "Crypto"},
    {"symbol": "ADA-USD", "name": "Cardano 艾达币", "market": "Crypto"},
    {"symbol": "DOGE-USD", "name": "Dogecoin 狗狗币", "market": "Crypto"},
    {"symbol": "DOT-USD", "name": "Polkadot 波卡", "market": "Crypto"},
    {"symbol": "MATIC-USD", "name": "Polygon", "market": "Crypto"},
    {"symbol": "LINK-USD", "name": "Chainlink", "market": "Crypto"},
    {"symbol": "AVAX-USD", "name": "Avalanche", "market": "Crypto"},
    {"symbol": "UNI-USD", "name": "Uniswap", "market": "Crypto"},
]


@app.get("/api/search")
async def search_symbols(q: str = ""):
    """搜索股票代码/名称"""
    if not q or len(q) < 1:
        return []
    
    q_upper = q.upper()
    q_lower = q.lower()
    
    results = []
    for item in POPULAR_SYMBOLS:
        # 匹配代码或名称
        if (q_upper in item["symbol"].upper() or 
            q_lower in item["name"].lower() or
            q_upper in item["name"].upper()):
            results.append(item)
        if len(results) >= 10:  # 最多返回 10 个
            break
    
    return results


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


@app.post("/api/chat")
async def chat(request: dict):
    """
    调用 OpenClaw agent 处理聊天消息
    前端发送: {"message": "分析 AAPL"}
    返回: {"reply": "...AI 回复..."}
    """
    message = request.get("message", "").strip()
    if not message:
        return {"reply": "请输入消息"}
    
    # 构建上下文提示
    context = f"""你是 Trading OS 的 AI 助手，帮助用户分析股票和加密货币。
用户问题: {message}

请简洁回答（不超过 200 字），如果涉及股票分析，给出具体建议。
如果用户问的是特定股票代码，告诉他们当前价格和你的看法。"""
    
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["openclaw", "agent", "--message", context, "--json"],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "OPENCLAW_QUIET": "1"}
            ),
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                reply = data.get("reply") or data.get("response") or data.get("message") or result.stdout
            except json.JSONDecodeError:
                reply = result.stdout.strip()
            return {"reply": reply}
        else:
            # 回退到简单响应
            return {"reply": f"收到你的问题：{message}\n\n请使用左侧搜索框添加股票，然后点击「AI 分析」获取详细分析。"}
    except subprocess.TimeoutExpired:
        return {"reply": "分析超时，请稍后重试。"}
    except Exception as e:
        return {"reply": f"抱歉，暂时无法处理。请直接使用「AI 分析」按钮。"}


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
