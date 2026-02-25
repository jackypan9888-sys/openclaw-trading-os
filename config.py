import json
import os
from dataclasses import dataclass, field

CONFIG_PATH = os.path.expanduser("~/.openclaw/trading-os/config.json")
OPENCLAW_PATH = os.path.expanduser("~/.openclaw/openclaw.json")


@dataclass
class TelegramConfig:
    bot_token: str


@dataclass
class AIConfig:
    primary_model: str = "kimi/kimi-k2.5"
    fallback_model: str = "anthropic-custom/claude-sonnet-4"
    timeout_seconds: int = 15


@dataclass
class Config:
    telegram: TelegramConfig
    ai: AIConfig = field(default_factory=AIConfig)
    workspace_path: str = os.path.expanduser("~/.openclaw/workspace")
    data_path: str = os.path.expanduser("~/.openclaw/trading-os")
    log_level: str = "INFO"

    @property
    def stock_analysis_path(self) -> str:
        return os.path.join(self.workspace_path, "skills/stock-analysis/scripts")

    @property
    def market_data_path(self) -> str:
        return os.path.join(self.workspace_path, "muquant/market-query")

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_path, "trading_os.db")

    @property
    def log_path(self) -> str:
        return os.path.join(self.data_path, "logs")


def load_config() -> Config:
    """
    加载配置。优先级：
    1. ~/.openclaw/trading-os/config.json（覆盖项）
    2. ~/.openclaw/openclaw.json（自动读取 Telegram token）
    """
    # 从 openclaw.json 读取 Telegram bot token
    bot_token = ""
    if os.path.exists(OPENCLAW_PATH):
        with open(OPENCLAW_PATH) as f:
            oc = json.load(f)
        bot_token = (
            oc.get("channels", {}).get("telegram", {}).get("botToken", "")
        )

    # 读取可选覆盖配置
    overrides: dict = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            overrides = json.load(f)

    ai_overrides = overrides.get("ai", {})
    ai_cfg = AIConfig(
        primary_model=ai_overrides.get("primary_model", AIConfig.primary_model),
        fallback_model=ai_overrides.get("fallback_model", AIConfig.fallback_model),
        timeout_seconds=ai_overrides.get("timeout_seconds", AIConfig.timeout_seconds),
    )

    return Config(
        telegram=TelegramConfig(
            bot_token=overrides.get("telegram_token", bot_token)
        ),
        ai=ai_cfg,
        log_level=overrides.get("log_level", "INFO"),
    )
