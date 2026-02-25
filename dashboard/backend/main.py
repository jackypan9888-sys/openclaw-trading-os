"""ASGI entrypoint for the dashboard backend."""
import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app import app

__all__ = ["app"]
