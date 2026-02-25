"""Filesystem paths used by Trading OS backend."""
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
WORKSPACE = Path.home() / ".openclaw" / "workspace"
STATIC_DIR = ROOT / "dashboard" / "static"
SCRIPTS_DIR = WORKSPACE / "skills" / "stock-analysis" / "scripts"
MARKET_DIR = WORKSPACE / "muquant" / "market-query"
