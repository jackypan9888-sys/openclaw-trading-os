"""Market data and misc routes."""
import asyncio
import json
import subprocess

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.paths import STATIC_DIR, SCRIPTS_DIR
from core.state import provider

router = APIRouter()
api_router = APIRouter(prefix="/api")


@router.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@api_router.get("/health")
async def health():
    return {"ok": True, "service": "trading-os-dashboard"}


POPULAR_SYMBOLS = [
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
    {"symbol": "JPM", "name": "JPMorgan Chase", "market": "US"},
    {"symbol": "V", "name": "Visa Inc.", "market": "US"},
    {"symbol": "MA", "name": "Mastercard Inc.", "market": "US"},
    {"symbol": "BAC", "name": "Bank of America", "market": "US"},
    {"symbol": "GS", "name": "Goldman Sachs", "market": "US"},
    {"symbol": "WMT", "name": "Walmart Inc.", "market": "US"},
    {"symbol": "KO", "name": "Coca-Cola Company", "market": "US"},
    {"symbol": "PEP", "name": "PepsiCo Inc.", "market": "US"},
    {"symbol": "MCD", "name": "McDonald's Corp.", "market": "US"},
    {"symbol": "NKE", "name": "Nike Inc.", "market": "US"},
    {"symbol": "SBUX", "name": "Starbucks Corp.", "market": "US"},
    {"symbol": "DIS", "name": "Walt Disney Company", "market": "US"},
    {"symbol": "BA", "name": "Boeing Company", "market": "US"},
    {"symbol": "XOM", "name": "Exxon Mobil", "market": "US"},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "market": "US"},
    {"symbol": "PFE", "name": "Pfizer Inc.", "market": "US"},
    {"symbol": "UNH", "name": "UnitedHealth Group", "market": "US"},
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


@api_router.get("/search")
async def search_symbols(q: str = ""):
    if not q or len(q) < 1:
        return []

    q_upper = q.upper()
    q_lower = q.lower()
    results = []
    for item in POPULAR_SYMBOLS:
        if (
            q_upper in item["symbol"].upper()
            or q_lower in item["name"].lower()
            or q_upper in item["name"].upper()
        ):
            results.append(item)
        if len(results) >= 10:
            break
    return results


@api_router.get("/price/{symbol}")
async def get_price(symbol: str):
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, provider.get_price, symbol.upper())
    return data or {"error": f"No data for {symbol}"}


@api_router.get("/chart/{symbol}")
async def get_chart(symbol: str, period: str = "5d"):
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, provider.get_chart_data, symbol.upper(), period)
    return data or {"error": f"No chart data for {symbol}"}


@api_router.get("/hot")
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
