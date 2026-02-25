---
name: trading-os
description: |
  🚦 OpenClaw Trading OS — AI Agent 驱动的交易操作系统

  三大核心能力:
  1. 自动盯盘 + 多类型预警（价格/止损/信号变化/传言/热点）
  2. AI 市场解读（新闻 + 社交 + 数据 → 3条可执行结论）
  3. 多用户 Telegram Bot（Free / Pro 订阅制，$29/月）

  支持市场: 美股 (US Equities) / 港股 (HK Equities) / 加密货币 (24/7)

  Phase 1: Telegram AI 预警助手（可商业化）
  Phase 2: 可视化 Web 交易仪表盘（React + TradingView）

  依赖现有 skills:
  - stock-analysis: analyze_stock.py, hot_scanner.py, rumor_scanner.py
  - muquant: market_data.py (MarketDataProvider)
version: 0.1.0
homepage: https://github.com/jackypan9888-sys/openclaw-trading-os
commands:
  - /watch  - 添加自选股（支持目标价/止损价）
  - /unwatch - 移除自选股
  - /watchlist - 查看自选股列表 + 实时盈亏
  - /price  - 即时查价（美股/港股/加密）
  - /analyze - AI 8维度分析（Pro 专属）
  - /alerts - 今日预警历史
  - /subscribe - 查看订阅套餐 + 付款方式
  - /settings - 静默时间 / 时区 / 预警偏好
metadata:
  emoji: 🚦
  requires:
    bins: [python3, uv]
    env: []
  install: []
---

# OpenClaw Trading OS

> AI Agent 驱动的交易操作系统 MVP — 帮交易员**省时间 + 提效率 + 降错误**

## 项目状态

| 模块 | 状态 |
|---|---|
| `db/` — SQLite 数据层 | ✅ Day 1 完成 |
| `config.py` — 配置加载 | ✅ Day 1 完成 |
| `daemon/` — 监控 Daemon | 🚀 Day 2 进行中 |
| `alerts/` — 预警引擎 | 📋 Day 3 计划 |
| `ai/` — AI 分析流水线 | 📋 Day 4 计划 |
| `telegram/` — Bot + 推送 | 📋 Day 5 计划 |
| `dashboard/` — Web 仪表盘 | 📋 Phase 2 |

## 快速启动

```bash
cd ~/.openclaw/workspace/skills/trading-os

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python3 -c "import sys; sys.path.insert(0,'.');from db.store import DataStore; DataStore().init_db(); print('OK')"

# 启动 Daemon（Day 5 后可用）
python3 run_daemon.py
```

## 核心设计

### 监控 Daemon 轮询频率
| 市场 | 盘中 | 盘后/盘前 | 休市 |
|---|---|---|---|
| 美股 (ET 9:30-16:00) | 60s | 300s | 暂停 |
| 港股 (HKT 9:30-16:00) | 60s | 300s | 暂停 |
| 加密货币 (24/7) | 60s | 60s | 60s |

### 预警触发条件
| 类型 | 触发 | 冷却 | 层级 |
|---|---|---|---|
| stop_hit | 价格 ≤ 止损价 | 无 | Free + Pro |
| target_hit | 价格 ≥ 目标价 | 24h | Free + Pro |
| signal_change | AI 评级变化 | 4h | Pro |
| rumor | M&A/内幕信号 | 12h | Pro |
| hot | 新热点资产 | 24h | Pro |

### AI 分析流水线
```
预警事件 → Enrich (analyze_stock --fast + 新闻)
        → Kimi K2.5 → 3条可执行结论 (WHY / RISK / ACTION)
        → 先推送原始预警，AI 完成后 edit 同一条消息
```

### 订阅层级
| 层级 | 价格 | 自选股 | 预警/天 | AI 分析 |
|---|---|---|---|---|
| Free | $0 | 5只 | 10条 | 无 |
| Pro | $29/月 | 无限 | 100条 | 每条含 |

## 复用现有资产

```python
# 价格查询 — 直接 import
from muquant.market_query.market_data import MarketDataProvider

# 股票分析 — subprocess 调用（避免依赖冲突）
subprocess.run(["uv", "run", "analyze_stock.py", "AAPL", "--output", "json", "--fast"])

# 热点扫描 — 直接 import
from stock_analysis.scripts.hot_scanner import HotScanner

# 传言扫描 — 直接 import
from stock_analysis.scripts import rumor_scanner
```

## 数据存储

| 位置 | 内容 |
|---|---|
| `~/.openclaw/trading-os/trading_os.db` | 用户、自选股、预警日志、去重记录 |
| `~/.openclaw/trading-os/logs/` | Daemon 运行日志 |

## 风险提示

⚠️ **NOT FINANCIAL ADVICE** — 仅供技术研究与学习使用
