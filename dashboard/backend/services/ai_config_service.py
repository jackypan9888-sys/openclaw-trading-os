"""Local AI config persistence helpers."""
import json
from pathlib import Path

AI_CONFIG_PATH = Path.home() / ".openclaw" / "trading-os" / "ai_config.json"


def load_ai_config() -> dict:
    if AI_CONFIG_PATH.exists():
        with open(AI_CONFIG_PATH) as f:
            return json.load(f)
    return {
        "provider": "anthropic",
        "api_key": "",
        "model": "claude-sonnet-4-20250514",
        "persona": "木木的小奴",
    }


def save_ai_config(config: dict):
    AI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AI_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_masked_ai_config() -> dict:
    config = load_ai_config()
    if config.get("api_key"):
        key = config["api_key"]
        config["api_key_masked"] = f"{key[:10]}...{key[-4:]}" if len(key) > 14 else "***"
        config["api_key_set"] = True
    else:
        config["api_key_masked"] = ""
        config["api_key_set"] = False
    config.pop("api_key", None)
    return config


def update_ai_config(payload: dict) -> dict:
    config = load_ai_config()
    if payload.get("api_key"):
        config["api_key"] = payload["api_key"]
    for key in ("model", "persona", "provider"):
        if key in payload:
            config[key] = payload[key]
    save_ai_config(config)
    return {"success": True, "message": "配置已保存"}
