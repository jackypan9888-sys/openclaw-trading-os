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


# AI 配置文件路径
AI_CONFIG_PATH = Path.home() / ".openclaw" / "trading-os" / "ai_config.json"


def format_market_cap(cap):
    """格式化市值"""
    if not cap:
        return "N/A"
    if cap >= 1e12:
        return f"${cap/1e12:.2f}T"
    elif cap >= 1e9:
        return f"${cap/1e9:.2f}B"
    elif cap >= 1e6:
        return f"${cap/1e6:.2f}M"
    else:
        return f"${cap:,.0f}"


def format_volume(vol):
    """格式化成交量"""
    if not vol:
        return "N/A"
    if vol >= 1e9:
        return f"{vol/1e9:.2f}B"
    elif vol >= 1e6:
        return f"{vol/1e6:.2f}M"
    elif vol >= 1e3:
        return f"{vol/1e3:.2f}K"
    else:
        return f"{vol:,.0f}"

def load_ai_config():
    """加载 AI 配置"""
    if AI_CONFIG_PATH.exists():
        with open(AI_CONFIG_PATH) as f:
            return json.load(f)
    # 默认配置
    return {
        "provider": "anthropic",
        "api_key": "",  # 用户需要自己配置
        "model": "claude-sonnet-4-20250514",
        "persona": "木木的小奴"
    }

def save_ai_config(config: dict):
    """保存 AI 配置"""
    AI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AI_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


@app.get("/api/ai/config")
async def get_ai_config():
    """获取 AI 配置（隐藏完整 API key）"""
    config = load_ai_config()
    # 隐藏 API key，只显示前后几位
    if config.get("api_key"):
        key = config["api_key"]
        config["api_key_masked"] = f"{key[:10]}...{key[-4:]}" if len(key) > 14 else "***"
        config["api_key_set"] = True
    else:
        config["api_key_masked"] = ""
        config["api_key_set"] = False
    del config["api_key"]
    return config


@app.post("/api/ai/config")
async def set_ai_config(request: dict):
    """更新 AI 配置"""
    config = load_ai_config()
    if "api_key" in request and request["api_key"]:
        config["api_key"] = request["api_key"]
    if "model" in request:
        config["model"] = request["model"]
    if "persona" in request:
        config["persona"] = request["persona"]
    if "provider" in request:
        config["provider"] = request["provider"]
    save_ai_config(config)
    return {"success": True, "message": "配置已保存"}


@app.post("/api/chat")
async def chat(request: dict):
    """
    调用 OpenClaw trading-os agent 处理聊天消息
    使用 stock-analysis 和 crypto-price 技能进行专业分析
    """
    import re
    
    message = request.get("message", "").strip()
    context = request.get("context", {})
    
    if not message:
        return {"reply": "请输入消息"}
    
    # 检测分析意图和标的
    upper_msg = message.upper()
    
    # 匹配股票代码 (AAPL, 0700.HK, 港股腾讯等)
    stock_match = re.search(r'\b([A-Z]{1,5})\b|\b(\d{4,5})\.?HK\b|港股\s*(\d{4,5}|[\u4e00-\u9fa5]+)', message)
    
    # 匹配加密货币 (BTC, ETH, SOL 等)
    crypto_match = re.search(r'\b(BTC|ETH|SOL|BNB|XRP|ADA|DOGE|DOT|AVAX|MATIC|LINK|ATOM|UNI|LTC|BCH|XLM|ALGO|VET|FIL|NEAR|HYPE)\b', upper_msg)
    
    # 检测分析关键词
    is_analysis = re.search(r'分析|怎么看|如何|建议|点评|evaluate|analyze', message)
    is_price_query = re.search(r'价格|price|多少钱|查询', message)
    
    # ========== 股票分析 ==========
    if is_analysis and stock_match and not crypto_match:
        symbol = stock_match.group(1) or stock_match.group(2) or stock_match.group(3)
        if stock_match.group(2) or stock_match.group(3):  # 港股
            symbol = symbol + '.HK' if not symbol.endswith('.HK') else symbol
        
        return await analyze_stock_with_skill(symbol, message)
    
    # ========== 加密货币分析 ==========
    elif is_analysis and crypto_match:
        symbol = crypto_match.group(1)
        return await analyze_crypto_with_skill(symbol, message)
    
    # ========== 普通对话 ==========
    return await chat_with_agent(message, context)


async def analyze_stock_with_skill(symbol: str, original_message: str) -> dict:
    """使用 muquant market.py 获取实时价格 + stock-analysis 深度分析"""
    try:
        loop = asyncio.get_event_loop()
        
        # 第1步: 用 market.py 获取最准确的实时价格
        market_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["python3", str(WORKSPACE / "skills" / "muquant" / "commands" / "market.py"), 
                 symbol, "--json"],
                capture_output=True,
                text=True,
                timeout=15
            ),
        )
        
        market_data = {}
        if market_result.returncode == 0:
            try:
                market_data = json.loads(market_result.stdout)
            except:
                pass
        
        # 第2步: 用 stock-analysis 获取深度分析
        analysis_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["uv", "run", str(WORKSPACE / "skills" / "stock-analysis" / "scripts" / "analyze_stock.py"), 
                 symbol, "--output", "json", "--fast"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(WORKSPACE / "skills" / "stock-analysis")
            ),
        )
        
        analysis_data = {}
        if analysis_result.returncode == 0:
            try:
                analysis_data = json.loads(analysis_result.stdout)
            except:
                pass
        
        # 合并数据构建回复
        price = market_data.get('price', analysis_data.get('price', 'N/A'))
        change_pct = market_data.get('change_pct', analysis_data.get('change_pct', 0))
        emoji = "🟢" if change_pct >= 0 else "🔴"
        
        score = analysis_data.get("total_score", "N/A")
        recommendation = analysis_data.get("recommendation", "--")
        summary = analysis_data.get("ai_summary", "")
        
        # 市值和PE优先用 market.py 的数据（更实时）
        market_cap = market_data.get('market_cap') or analysis_data.get('market_cap')
        pe_ratio = market_data.get('pe_ratio') or analysis_data.get('pe_ratio')
        
        reply = f"""🦞 **{symbol}** 实时分析报告 ⚔️

### 💰 实时行情 (Yahoo Finance)
| 指标 | 数据 | 信号 |
|------|------|------|
| **现价** | **${price}** | {emoji} |
| **涨跌** | **{change_pct:+.2f}%** | {"🚀" if change_pct > 2 else "📉" if change_pct < -2 else "➡️"} |
| **市值** | {format_market_cap(market_cap)} | 💎 |
| **PE** | {f"{pe_ratio:.2f}" if pe_ratio else "N/A"} | {"⚠️ 偏高" if pe_ratio and pe_ratio > 30 else "✅ 合理" if pe_ratio else "--"} |

### 📊 AI评分: {score}/100 | 建议: {recommendation}

{summary}

---
*数据来源: Yahoo Finance via market.py | 分析模型: stock-analysis v6.2*
*⚠️ 仅供参考，不构成投资建议*"""
        
        return {"reply": reply}
        
    except Exception as e:
        # 出错时回退到 agent
        return await chat_with_agent(f"分析股票 {symbol}：{original_message}", {})


async def analyze_crypto_with_skill(symbol: str, original_message: str) -> dict:
    """使用 muquant market.py 获取实时价格 + crypto-price K线图表"""
    try:
        loop = asyncio.get_event_loop()
        
        # 第1步: 用 market.py 获取最准确的实时价格 (BTC-USD 格式)
        yf_symbol = f"{symbol}-USD" if not symbol.endswith('-USD') else symbol
        market_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["python3", str(WORKSPACE / "skills" / "muquant" / "commands" / "market.py"), 
                 yf_symbol, "--json"],
                capture_output=True,
                text=True,
                timeout=15
            ),
        )
        
        market_data = {}
        if market_result.returncode == 0:
            try:
                market_data = json.loads(market_result.stdout)
            except:
                pass
        
        # 第2步: 用 crypto-price 获取K线图表
        chart_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["python3", str(WORKSPACE / "skills" / "crypto-price" / "scripts" / "get_price_chart.py"), 
                 symbol, "1d"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(WORKSPACE / "skills" / "crypto-price")
            ),
        )
        
        chart_data = {}
        if chart_result.returncode == 0:
            try:
                chart_data = json.loads(chart_result.stdout)
            except:
                pass
        
        # 合并数据
        price = market_data.get('price', chart_data.get('price', 'N/A'))
        change_pct = market_data.get('change_pct', chart_data.get('change_period_percent', 0))
        emoji = "🟢" if change_pct >= 0 else "🔴"
        chart_path = chart_data.get('chart_path', '')
        
        # 市值和成交量
        market_cap = market_data.get('market_cap')
        volume = market_data.get('volume')
        
        reply = f"""🦞 **{symbol}** 加密货币实时分析 🪙

### 💰 实时行情 (Yahoo Finance)
| 指标 | 数据 | 信号 |
|------|------|------|
| **现价** | **${price}** | {emoji} |
| **24h涨跌** | **{change_pct:+.2f}%** | {"🚀" if change_pct > 5 else "📉" if change_pct < -5 else "➡️"} |
| **市值** | {format_market_cap(market_cap)} | 💎 |
| **24h成交量** | {format_volume(volume)} | 📊 |

### 📈 技术分析
{chart_data.get('text_plain', '技术面分析数据获取中...')}

---
*数据来源: Yahoo Finance via market.py | K线: CoinGecko*
*⚠️ 加密市场波动剧烈，请注意风险*"""
        
        # 如果有图表路径，添加
        if chart_path and os.path.exists(chart_path):
            reply += f"\n\n📊 **K线图表已生成**: {chart_path}"
        
        return {"reply": reply}
        
    except Exception as e:
        # 出错时回退到 agent
        return await chat_with_agent(f"分析加密货币 {symbol}：{original_message}", {})


async def chat_with_agent(message: str, context: dict) -> dict:
    """与 OpenClaw agent 对话 - 带超时和降级机制"""
    # 添加上下文信息
    active_symbol = context.get("activeSymbol", "")
    if active_symbol:
        message = f"[当前查看: {active_symbol}] {message}"
    
    # 首先尝试用 web_search 快速回答（3秒内）
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    "openclaw", "agent",
                    "--agent", "trading-os",
                    "--session-id", "trading-os-web",
                    "-m", message,
                    "--thinking", "off"  # 关闭思考，加速响应
                ],
                capture_output=True,
                text=True,
                timeout=15,  # 15秒超时
                env={**os.environ, "OPENCLAW_QUIET": "1"}
            ),
        )
        
        if result.returncode == 0 and result.stdout.strip():
            # 清理输出
            output = result.stdout.strip()
            lines = output.split('\n')
            clean_lines = [l for l in lines if not l.startswith('Config warnings') and not l.startswith('-')]
            reply = '\n'.join(clean_lines).strip()
            if reply:
                return {"reply": reply}
        
        # Agent 没返回有效内容，降级到快速模式
        return {"reply": "🦞 龙虾交易助手收到！\n\n当前系统繁忙，请稍后再试，或直接查询股票代码（如：分析 AAPL）"}
        
    except subprocess.TimeoutExpired:
        # 超时，返回友好提示
        return {"reply": "⏳ 龙虾交易助手思考超时了...\n\n💡 试试这些快捷命令：\n• 分析 AAPL\n• 查询 BTC价格\n• 扫描热点"}
    except Exception as e:
        # 出错也返回友好提示
        return {"reply": "⚠️ 连接暂时不稳定\n\n💡 您可以：\n• 刷新页面重试\n• 使用左侧快捷操作（AI分析/热点扫描）"}


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
