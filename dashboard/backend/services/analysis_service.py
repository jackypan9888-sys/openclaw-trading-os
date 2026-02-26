"""Analysis and chat services - 带缓存优化和超时降级"""
import asyncio
import json
import os
import re
import subprocess
import sys
import time

from services.agent_profile_service import build_agent_contract, load_agent_profile
from services.formatters import format_market_cap, format_volume
from core.paths import SCRIPTS_DIR, WORKSPACE
from core.state import store, provider

# 超时阈值（秒）
TIMEOUT_PRICE_ONLY = 5.0    # >5s 只返回价格
TIMEOUT_USE_CACHE = 10.0    # >10s 使用缓存数据
TIMEOUT_TOTAL = 20.0        # 总超时限制


async def analyze_symbol(symbol: str) -> dict:
    """分析股票/加密货币（带缓存）"""
    symbol = symbol.upper()
    
    # 检查分析缓存
    cached = store.get_cached_analysis(symbol)
    if cached:
        return json.loads(cached)

    # 使用带超时的分析流程
    start_time = time.time()
    
    try:
        # 尝试快速获取（带超时保护）
        result = await _analyze_with_timeout(symbol, timeout=TIMEOUT_TOTAL)
        elapsed = time.time() - start_time
        print(f"[Analysis] {symbol} completed in {elapsed:.1f}s")
        return result
        
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"[Analysis] {symbol} timed out after {elapsed:.1f}s")
        
        # 超时降级：尝试返回缓存价格
        cached_price = store.get_cached_price(symbol)
        if cached_price:
            return {
                "symbol": symbol,
                "price": cached_price.get("price"),
                "change_pct": cached_price.get("change_pct"),
                "note": "分析超时，返回缓存价格",
                "cached": True,
                "fast_mode": True,
            }
        
        return {
            "error": f"分析超时 ({elapsed:.1f}s)",
            "symbol": symbol,
            "suggestion": "请稍后重试或联系管理员",
        }


async def _analyze_with_timeout(symbol: str, timeout: float) -> dict:
    """带超时限制的分析流程"""
    loop = asyncio.get_event_loop()
    python_exe = sys.executable
    
    # 并行启动市场数据获取和技术分析
    market_task = loop.run_in_executor(
        None,
        lambda: _get_market_data_with_degradation(symbol)
    )
    
    analysis_task = loop.run_in_executor(
        None,
        lambda: _get_analysis_data(symbol, python_exe)
    )
    
    # 等待结果，带超时
    try:
        market_data = await asyncio.wait_for(market_task, timeout=timeout/2)
    except asyncio.TimeoutError:
        market_data = {"error": "timeout"}
    
    try:
        analysis_data = await asyncio.wait_for(analysis_task, timeout=timeout/2)
    except asyncio.TimeoutError:
        analysis_data = {"error": "timeout"}
    
    # 组装结果
    return _build_analysis_result(symbol, market_data, analysis_data)


def _get_market_data_with_degradation(symbol: str) -> dict:
    """获取市场数据，带超时降级策略"""
    start = time.time()
    
    # 首先检查缓存
    cached = store.get_cached_price(symbol)
    
    try:
        # 尝试获取实时数据（带超时）
        # 使用 provider（CachedMarketDataProvider）
        data = provider.get_price(symbol, timeout=TIMEOUT_PRICE_ONLY)
        elapsed = time.time() - start
        
        if data and data.get("price") is not None:
            print(f"[Market] {symbol} fetched in {elapsed:.1f}s")
            return data
        
        # 获取失败，使用缓存
        if cached:
            print(f"[Market] {symbol} fetch failed after {elapsed:.1f}s, using cache")
            cached["from_cache"] = True
            return cached
            
    except Exception as e:
        elapsed = time.time() - start
        print(f"[Market] {symbol} error after {elapsed:.1f}s: {e}")
        
        # 出错时使用缓存
        if cached:
            cached["from_cache"] = True
            cached["error"] = str(e)
            return cached
    
    return {"error": "Failed to get market data"}


def _get_analysis_data(symbol: str, python_exe: str) -> dict:
    """获取技术分析数据"""
    try:
        analysis_script = str(WORKSPACE / "skills" / "stock-analysis" / "scripts" / "analyze_stock.py")
        result = subprocess.run(
            [python_exe, analysis_script, symbol, "--output", "json", "--fast"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(WORKSPACE / "skills" / "stock-analysis"),
        )
        
        if result.returncode == 0:
            stdout = result.stdout.strip()
            json_start = stdout.find('{')
            if json_start >= 0:
                data = json.loads(stdout[json_start:])
                # 缓存分析结果
                store.set_cached_analysis(symbol, json.dumps(data), ttl_minutes=30)
                return data
                
    except subprocess.TimeoutExpired:
        print(f"[Analysis] {symbol} analysis script timeout")
        return {"error": "timeout"}
    except Exception as e:
        print(f"[Analysis] {symbol} analysis error: {e}")
        
    return {}


def _build_analysis_result(symbol: str, market_data: dict, analysis_data: dict) -> dict:
    """组装分析结果"""
    result = {
        "symbol": symbol,
        "price": market_data.get("price"),
        "change_pct": market_data.get("change_pct", 0),
        "currency": market_data.get("currency", "USD"),
        "market_cap": market_data.get("market_cap"),
        "pe_ratio": market_data.get("pe_ratio"),
        "volume": market_data.get("volume"),
    }
    
    if analysis_data and not analysis_data.get("error"):
        result.update({
            "total_score": analysis_data.get("total_score"),
            "recommendation": analysis_data.get("recommendation"),
            "ai_summary": analysis_data.get("ai_summary"),
            "technical": analysis_data.get("technical", {}),
        })
    
    if market_data.get("from_cache"):
        result["from_cache"] = True
        
    return result


async def chat_dispatch(request: dict) -> dict:
    message = request.get("message", "").strip()
    context = request.get("context", {})

    if not message:
        return {"reply": "请输入消息"}

    upper_msg = message.upper()
    stock_match = re.search(r"\b([A-Z]{1,5})\b|\b(\d{4,5})\.?HK\b|港股\s*(\d{4,5}|[\u4e00-\u9fa5]+)", message)
    crypto_match = re.search(r"\b(BTC|ETH|SOL|BNB|XRP|ADA|DOGE|DOT|AVAX|MATIC|LINK|ATOM|UNI|LTC|BCH|XLM|ALGO|VET|FIL|NEAR|HYPE)\b", upper_msg)
    is_analysis = re.search(r"分析|怎么看|如何|建议|点评|evaluate|analyze", message)

    if is_analysis and stock_match and not crypto_match:
        symbol = stock_match.group(1) or stock_match.group(2) or stock_match.group(3)
        if stock_match.group(2) or stock_match.group(3):
            symbol = symbol + ".HK" if not symbol.endswith(".HK") else symbol
        return await analyze_stock_with_skill(symbol, message)

    if is_analysis and crypto_match:
        symbol = crypto_match.group(1)
        return await analyze_crypto_with_skill(symbol, message)

    return await chat_with_agent(message, context)


async def analyze_stock_with_skill(symbol: str, original_message: str) -> dict:
    """分析股票（带缓存优化和超时降级）"""
    start_time = time.time()
    
    try:
        # 使用并行获取优化
        market_data, analysis_data = await _fetch_stock_data_parallel(symbol)
        
        elapsed = time.time() - start_time
        
        # 超时降级检测
        if elapsed > TIMEOUT_USE_CACHE:
            # 超过10秒，尝试使用缓存
            cached = store.get_cached_analysis(symbol)
            if cached:
                data = json.loads(cached)
                return _format_quick_response(symbol, data, elapsed, from_cache=True)
        
        # 组装回复
        return _format_stock_response(symbol, market_data, analysis_data, elapsed)
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[StockAnalysis] {symbol} error after {elapsed:.1f}s: {e}")
        
        # 错误时返回缓存或快速模式
        cached_analysis = store.get_cached_analysis(symbol)
        cached_price = store.get_cached_price(symbol)
        
        if cached_analysis:
            return _format_quick_response(symbol, json.loads(cached_analysis), elapsed, from_cache=True)
        elif cached_price:
            return _format_price_only_response(symbol, cached_price, elapsed)
        
        return {"reply": f"❌ 分析 {symbol} 时出错，请稍后重试"}


async def _fetch_stock_data_parallel(symbol: str) -> tuple:
    """并行获取股票数据"""
    loop = asyncio.get_event_loop()
    python_exe = sys.executable
    
    # 任务1：从缓存/实时获取价格
    async def get_market():
        # 使用 CachedMarketDataProvider
        return provider.get_price(symbol, timeout=TIMEOUT_PRICE_ONLY)
    
    # 任务2：获取技术分析
    async def get_analysis():
        try:
            return await loop.run_in_executor(
                None,
                lambda: _get_analysis_data(symbol, python_exe)
            )
        except Exception as e:
            print(f"[Parallel] Analysis fetch error: {e}")
            return {}
    
    # 并行执行
    market_task = asyncio.create_task(get_market())
    analysis_task = asyncio.create_task(get_analysis())
    
    market_data = await market_task
    
    # 如果价格获取很快，等待分析完成
    if market_data and market_data.get("price"):
        try:
            analysis_data = await asyncio.wait_for(analysis_task, timeout=TIMEOUT_PRICE_ONLY)
        except asyncio.TimeoutError:
            analysis_data = {"error": "timeout"}
    else:
        analysis_data = await analysis_task
    
    return market_data, analysis_data


def _format_stock_response(symbol: str, market_data: dict, analysis_data: dict, elapsed: float) -> dict:
    """格式化股票分析回复"""
    price = market_data.get("price", "N/A") if market_data else "N/A"
    change_pct = market_data.get("change_pct", 0) if market_data else 0
    emoji = "🟢" if change_pct >= 0 else "🔴"
    
    score = analysis_data.get("total_score", "N/A") if analysis_data else "N/A"
    recommendation = analysis_data.get("recommendation", "--") if analysis_data else "--"
    summary = analysis_data.get("ai_summary", "") if analysis_data else ""
    
    market_cap = market_data.get("market_cap") if market_data else None
    pe_ratio = market_data.get("pe_ratio") if market_data else None
    cached_tag = " [缓存]" if market_data and market_data.get("cached") else ""
    
    reply = f"""🦞 **{symbol}** 实时分析报告 ⚔️{cached_tag}

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
*响应时间: {elapsed:.1f}s | 数据来源: Yahoo Finance via CachedProvider*
*⚠️ 仅供参考，不构成投资建议*"""

    return {"reply": reply}


def _format_quick_response(symbol: str, data: dict, elapsed: float, from_cache: bool = False) -> dict:
    """格式化快速响应（降级模式）"""
    cache_tag = " [缓存数据]" if from_cache else ""
    
    reply = f"""⚡ **{symbol}** 快速响应{cache_tag}

💰 价格: ${data.get('price', 'N/A')}
📈 涨跌: {data.get('change_pct', 0):+.2f}%
📊 AI评分: {data.get('total_score', 'N/A')}/100
🎯 建议: {data.get('recommendation', '--')}

*⚠️ 响应时间 {elapsed:.1f}s 超过阈值，已切换到快速模式*
*完整分析可能稍后提供*"""

    return {"reply": reply}


def _format_price_only_response(symbol: str, price_data: dict, elapsed: float) -> dict:
    """格式化仅价格响应（严重降级）"""
    emoji = "🟢" if price_data.get("change_pct", 0) >= 0 else "🔴"
    
    reply = f"""⚡ **{symbol}** 价格速报 [缓存]

{emoji} 价格: ${price_data.get('price', 'N/A')}
📊 涨跌: {price_data.get('change_pct', 0):+.2f}%

*⚠️ 数据源暂时不可用，显示缓存数据*
*响应时间: {elapsed:.1f}s*"""

    return {"reply": reply}


async def analyze_crypto_with_skill(symbol: str, original_message: str) -> dict:
    """分析加密货币（带缓存优化）"""
    start_time = time.time()
    
    try:
        loop = asyncio.get_event_loop()
        python_exe = sys.executable
        yf_symbol = f"{symbol}-USD" if not symbol.endswith("-USD") else symbol
        
        # 并行获取价格和图表
        async def get_price():
            return provider.get_price(yf_symbol, timeout=TIMEOUT_PRICE_ONLY)
        
        async def get_chart():
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [python_exe, str(WORKSPACE / "skills" / "crypto-price" / "scripts" / "get_price_chart.py"), symbol, "1d"],
                        capture_output=True,
                        text=True,
                        timeout=15,
                        cwd=str(WORKSPACE / "skills" / "crypto-price"),
                    )
                )
                if result.returncode == 0:
                    stdout = result.stdout.strip()
                    json_start = stdout.find('{')
                    if json_start >= 0:
                        return json.loads(stdout[json_start:])
            except Exception as e:
                print(f"[Crypto] Chart error: {e}")
            return {}
        
        price_task = asyncio.create_task(get_price())
        chart_task = asyncio.create_task(get_chart())
        
        market_data = await price_task
        
        # 如果价格获取很快，继续等待图表
        elapsed_so_far = time.time() - start_time
        remaining = TIMEOUT_PRICE_ONLY - elapsed_so_far
        
        if remaining > 0 and market_data and market_data.get("price"):
            try:
                chart_data = await asyncio.wait_for(chart_task, timeout=remaining)
            except asyncio.TimeoutError:
                chart_data = {}
        else:
            chart_data = await chart_task
        
        elapsed = time.time() - start_time
        
        price = market_data.get("price", chart_data.get("price", "N/A")) if market_data else chart_data.get("price", "N/A")
        change_pct = market_data.get("change_pct", chart_data.get("change_period_percent", 0)) if market_data else chart_data.get("change_period_percent", 0)
        emoji = "🟢" if change_pct >= 0 else "🔴"
        chart_path = chart_data.get("chart_path", "")
        market_cap = market_data.get("market_cap") if market_data else None
        volume = market_data.get("volume") if market_data else None
        cached_tag = " [缓存]" if market_data and market_data.get("cached") else ""

        reply = f"""🦞 **{symbol}** 加密货币实时分析 🪙{cached_tag}

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
*响应时间: {elapsed:.1f}s | 数据来源: Yahoo Finance / CoinGecko*
*⚠️ 加密市场波动剧烈，请注意风险*"""

        if chart_path and os.path.exists(chart_path):
            reply += f"\n\n📊 **K线图表已生成**: {chart_path}"

        return {"reply": reply}

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[Crypto] {symbol} error after {elapsed:.1f}s: {e}")
        return {"reply": f"❌ 分析加密货币 {symbol} 时出错"}


async def chat_with_agent(message: str, context: dict) -> dict:
    """优先调用 OpenClaw trading-os agent，失败时回退到本地引导回复。"""
    active_symbol = context.get("activeSymbol", "")

    profile = load_agent_profile()
    contract = build_agent_contract(profile, context)
    prompt = (
        f"{contract}\n\n"
        f"当前界面标的: {active_symbol or '未指定'}\n"
        "请直接给出中文回复，结构为：结论 / 行动 / 风险 / 需确认。\n"
        f"用户消息：{message}"
    )

    loop = asyncio.get_event_loop()
    result = None
    run_error = ""
    try:
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["openclaw", "agent", "--agent", "trading-os", "--message", prompt, "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            ),
        )
    except subprocess.TimeoutExpired:
        run_error = "交易员 agent 响应超时（30s）"
    except FileNotFoundError:
        run_error = "未找到 openclaw 命令，请检查 PATH"
    except Exception as e:
        run_error = f"交易员 agent 调用异常: {e}"

    if result and result.returncode == 0 and result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            payloads = data.get("result", {}).get("payloads", [])
            if payloads and payloads[0].get("text"):
                return {"reply": payloads[0]["text"]}
        except Exception:
            pass

    fallback = (
        "🦞 **龙虾交易助手在线！** ⚔️\n\n"
        "你好！我是你的 Trading OS 专属交易助手。\n\n"
        "### 💬 我可以帮你：\n"
        "1. **📊 股票分析** - 输入 \"分析 AAPL\" 或 \"分析 0700.HK\"\n"
        "2. **🪙 加密货币** - 输入 \"分析 BTC\" 或 \"分析 ETH\"\n"
        "3. **🔍 热点扫描** - 询问 \"今天有什么热点\"\n"
        "4. **💰 实时行情** - 查看左侧面板的自选股\n\n"
        "---\n"
        "*💡 提示: 直接在下方输入框发送消息与我对话！*\n"
        "*⚠️ 风险提示: 所有分析仅供参考，不构成投资建议*"
    )
    if run_error:
        fallback += f"\n错误摘要: {run_error}"
    elif result and result.stderr.strip():
        fallback += f"\n错误摘要: {result.stderr.strip()[:180]}"
    return {"reply": fallback}
