# OpenClaw Trading OS

AI Agent 驱动的交易操作系统（MVP）。

当前仓库重点是一个可运行的 Web Dashboard 后端 + SQLite 数据层，支持：
- 自选股管理
- 实时行情轮询与 WebSocket 推送
- 基础分析与热点扫描接口
- OpenClaw Agent 聊天入口

## Repository Layout

```text
trading-os/
  SKILL.md                    # Codex/OpenClaw skill 元数据
  README.md                   # 项目说明（本文件）
  requirements.txt            # Python 依赖
  config.py                   # 配置加载（~/.openclaw 下）
  db/                         # SQLite schema + store
  dashboard/
    static/index.html         # 前端页面（单文件）
    backend/main.py           # FastAPI 后端
    backend/openclaw_client.py
    backend/openclaw_queue.py
  ai/ alerts/ daemon/ telegram/  # 预留模块目录（待实现）
```

## Quick Start

```bash
cd /Users/vv/.openclaw/workspace/skills/trading-os
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -c "import sys; sys.path.insert(0,'.'); from db.store import DataStore; DataStore().init_db(); print('DB OK')"
uvicorn dashboard.backend.main:app --host 127.0.0.1 --port 8080 --reload
```

打开：`http://127.0.0.1:8080`

## Runtime Dependencies

仓库会复用你本地 OpenClaw 工作区中的其他技能：
- `~/.openclaw/workspace/skills/stock-analysis`
- `~/.openclaw/workspace/skills/muquant`
- 可选：`~/.openclaw/workspace/skills/crypto-price`

若这些目录不存在，部分接口会返回错误信息，但 Dashboard 仍可启动。

## Configuration

默认读取：
- `~/.openclaw/openclaw.json`（Telegram token）
- `~/.openclaw/trading-os/config.json`（可覆盖）

`dashboard/backend/openclaw_client.py` 调试模式使用环境变量：
- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_GATEWAY_URL`（可选，自定义时才需要）

## Security Notes

- 不要把 Gateway token、Telegram token、API key 写入代码或提交到 Git。
- 仓库内已避免硬编码 token；本地调试请使用环境变量或 `~/.openclaw` 配置文件。

## Roadmap (Suggested)

1. 把 `dashboard/backend/main.py` 拆成 routers/services（降低单文件复杂度）。
2. 为 `ai/alerts/daemon/telegram` 增加最小可运行骨架与测试。
3. 加入 `pytest` + 基础 API 测试，确保改动可回归。
