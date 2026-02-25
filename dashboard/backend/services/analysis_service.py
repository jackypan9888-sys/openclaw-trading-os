"""Analysis and chat services."""
import asyncio
import json
import os
import re
import subprocess
import sys

from services.agent_profile_service import build_agent_contract, load_agent_profile
from services.formatters import format_market_cap, format_volume
from core.paths import SCRIPTS_DIR, WORKSPACE
from core.state import store


async def analyze_symbol(symbol: str) -> dict:
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
    try:
        loop = asyncio.get_event_loop()
        
        # 使用 sys.executable 确保使用正确的 Python
        python_exe = sys.executable
        
        market_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [python_exe, str(WORKSPACE / "skills" / "muquant" / "commands" / "market.py"), symbol, "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            ),
        )

        market_data = {}
        if market_result.returncode == 0:
            try:
                # 从输出中提取 JSON（过滤掉 🔍 正在查询... 等非JSON内容）
                stdout = market_result.stdout.strip()
                json_start = stdout.find('{')
                if json_start >= 0:
                    market_data = json.loads(stdout[json_start:])
            except Exception:
                pass

        # 直接使用 Python 运行分析脚本（避免 uv 依赖）
        analysis_script = str(WORKSPACE / "skills" / "stock-analysis" / "scripts" / "analyze_stock.py")
        analysis_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [python_exe, analysis_script, symbol, "--output", "json", "--fast"],
                capture_output=True,
                text=True,
                timeout=25,
                cwd=str(WORKSPACE / "skills" / "stock-analysis"),
            ),
        )

        analysis_data = {}
        if analysis_result.returncode == 0:
            try:
                # 同样处理 analyze_stock.py 的输出
                stdout = analysis_result.stdout.strip()
                json_start = stdout.find('{')
                if json_start >= 0:
                    analysis_data = json.loads(stdout[json_start:])
            except Exception:
                pass

        price = market_data.get("price", analysis_data.get("price", "N/A"))
        change_pct = market_data.get("change_pct", analysis_data.get("change_pct", 0))
        emoji = "🟢" if change_pct >= 0 else "🔴"

        score = analysis_data.get("total_score", "N/A")
        recommendation = analysis_data.get("recommendation", "--")
        summary = analysis_data.get("ai_summary", "")

        market_cap = market_data.get("market_cap") or analysis_data.get("market_cap")
        pe_ratio = market_data.get("pe_ratio") or analysis_data.get("pe_ratio")

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

    except Exception:
        return await chat_with_agent(f"分析股票 {symbol}：{original_message}", {})


async def analyze_crypto_with_skill(symbol: str, original_message: str) -> dict:
    try:
        loop = asyncio.get_event_loop()
        python_exe = sys.executable

        yf_symbol = f"{symbol}-USD" if not symbol.endswith("-USD") else symbol
        market_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [python_exe, str(WORKSPACE / "skills" / "muquant" / "commands" / "market.py"), yf_symbol, "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            ),
        )

        market_data = {}
        if market_result.returncode == 0:
            try:
                # 从输出中提取 JSON
                stdout = market_result.stdout.strip()
                json_start = stdout.find('{')
                if json_start >= 0:
                    market_data = json.loads(stdout[json_start:])
            except Exception:
                pass

        chart_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [python_exe, str(WORKSPACE / "skills" / "crypto-price" / "scripts" / "get_price_chart.py"), symbol, "1d"],
                capture_output=True,
                text=True,
                timeout=20,
                cwd=str(WORKSPACE / "skills" / "crypto-price"),
            ),
        )

        chart_data = {}
        if chart_result.returncode == 0:
            try:
                # 从输出中提取 JSON
                stdout = chart_result.stdout.strip()
                json_start = stdout.find('{')
                if json_start >= 0:
                    chart_data = json.loads(stdout[json_start:])
            except Exception:
                pass

        price = market_data.get("price", chart_data.get("price", "N/A"))
        change_pct = market_data.get("change_pct", chart_data.get("change_period_percent", 0))
        emoji = "🟢" if change_pct >= 0 else "🔴"
        chart_path = chart_data.get("chart_path", "")

        market_cap = market_data.get("market_cap")
        volume = market_data.get("volume")

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

        if chart_path and os.path.exists(chart_path):
            reply += f"\n\n📊 **K线图表已生成**: {chart_path}"

        return {"reply": reply}

    except Exception:
        return await chat_with_agent(f"分析加密货币 {symbol}：{original_message}", {})


async def chat_with_agent(message: str, context: dict) -> dict:
    profile = load_agent_profile()
    active_symbol = context.get("activeSymbol", "")
    if active_symbol:
        message = f"[当前查看: {active_symbol}] {message}"
    contract = build_agent_contract(profile, context=context)
    agent_message = (
        "[SYSTEM_CONTRACT]\n"
        f"{contract}\n\n"
        "[USER_MESSAGE]\n"
        f"{message}"
    )

    try:
        loop = asyncio.get_event_loop()
        import shutil

        openclaw_exe = shutil.which("openclaw") or "/opt/homebrew/bin/openclaw"
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    openclaw_exe,
                    "agent",
                    "--agent",
                    "trading-os",
                    "--session-id",
                    "trading-os-web",
                    "-m",
                    agent_message,
                    "--thinking",
                    "off",
                ],
                capture_output=True,
                text=True,
                timeout=12,
                env={**os.environ, "OPENCLAW_QUIET": "1"},
            ),
        )

        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()
            lines = output.split("\n")
            clean_lines = [l for l in lines if not l.startswith("Config warnings") and not l.startswith("-")]
            reply = "\n".join(clean_lines).strip()
            if reply:
                return {"reply": reply}

        return {
            "reply": "结论: 系统暂时无有效响应。\n行动: 稍后重试或改为明确问题。\n风险: 当前回复为空可能导致误判。\n置信度: 低。\n需确认: 请输入标的与目标（例如“分析 AAPL，给3条交易计划”）。"
        }

    except subprocess.TimeoutExpired:
        return {"reply": "结论: 响应超时。\n行动: 缩短问题范围并重试。\n风险: 超时状态下不应直接执行交易。\n置信度: 低。\n需确认: 请指定单一标的和时间周期。"}
    except Exception:
        return {"reply": "结论: 连接异常。\n行动: 检查 OpenClaw 服务后重试。\n风险: 外部依赖异常时禁止自动交易。\n置信度: 低。\n需确认: 是否继续仅做分析模式？"}
