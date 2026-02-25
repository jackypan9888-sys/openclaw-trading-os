"""OpenClaw trading agent profile and response contract management."""

import json
from pathlib import Path

AGENT_PROFILE_PATH = Path.home() / ".openclaw" / "trading-os" / "agent_profile.json"


def default_agent_profile() -> dict:
    return {
        "agent_name": "OpenClaw Trading Strategist",
        "mode": "advisor",  # advisor | semi_auto | auto
        "response_style": "standard",  # concise | standard | deep
        "language": "zh",  # zh | en | auto
        "risk_level": "balanced",  # conservative | balanced | aggressive
        "capabilities": {
            "market_brief": True,
            "technical_analysis": True,
            "news_reasoning": True,
            "portfolio_review": True,
            "risk_guard": True,
            "execution_plan": True,
        },
        "response_contract": {
            "require_sections": ["结论", "行动", "风险", "置信度", "需确认"],
            "max_action_items": 3,
            "include_disclaimer": True,
        },
    }


def _normalize_profile(profile: dict) -> dict:
    base = default_agent_profile()
    merged = {**base, **(profile or {})}

    caps = base["capabilities"].copy()
    caps.update((profile or {}).get("capabilities", {}))
    merged["capabilities"] = caps

    contract = base["response_contract"].copy()
    contract.update((profile or {}).get("response_contract", {}))
    merged["response_contract"] = contract

    return merged


def load_agent_profile() -> dict:
    if AGENT_PROFILE_PATH.exists():
        try:
            with open(AGENT_PROFILE_PATH) as f:
                return _normalize_profile(json.load(f))
        except Exception:
            return default_agent_profile()
    return default_agent_profile()


def save_agent_profile(profile: dict) -> dict:
    normalized = _normalize_profile(profile)
    AGENT_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AGENT_PROFILE_PATH, "w") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return normalized


def update_agent_profile(payload: dict) -> dict:
    current = load_agent_profile()
    merged = _normalize_profile({**current, **(payload or {})})

    if "capabilities" in (payload or {}):
        caps = current.get("capabilities", {}).copy()
        caps.update(payload.get("capabilities", {}))
        merged["capabilities"] = caps

    if "response_contract" in (payload or {}):
        contract = current.get("response_contract", {}).copy()
        contract.update(payload.get("response_contract", {}))
        merged["response_contract"] = contract

    saved = save_agent_profile(merged)
    return {"success": True, "profile": saved}


def build_agent_contract(profile: dict, context: dict | None = None) -> str:
    context = context or {}
    caps = profile.get("capabilities", {})
    contract = profile.get("response_contract", {})

    section_list = contract.get("require_sections", ["结论", "行动", "风险", "置信度", "需确认"])
    max_actions = int(contract.get("max_action_items", 3))

    caps_enabled = [k for k, v in caps.items() if v]
    symbol = context.get("activeSymbol") or context.get("ticker") or ""

    return (
        f"你是 {profile.get('agent_name', 'Trading Agent')}。\n"
        f"工作模式: {profile.get('mode','advisor')}；风险偏好: {profile.get('risk_level','balanced')}；"
        f"响应风格: {profile.get('response_style','standard')}；语言: {profile.get('language','zh')}。\n"
        f"启用能力: {', '.join(caps_enabled) if caps_enabled else 'none'}。\n"
        f"当前上下文标的: {symbol if symbol else 'N/A'}。\n"
        "你必须输出结构化回复，按以下标题逐段给出：\n"
        + "\n".join(f"- {x}" for x in section_list)
        + f"\n行动项最多 {max_actions} 条，每条必须可执行。"
        + "\n如果信息不足，在“需确认”中明确提问，不要编造数据。"
        + ("\n最后附上‘免责声明: 非投资建议。’" if contract.get("include_disclaimer", True) else "")
    )
