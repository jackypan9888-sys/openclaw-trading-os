# Trading OS Refactor Roadmap

## Phase A: 基础可维护性（已完成）

- 补充仓库主文档 `README.md`
- 修复 `openclaw_client.py` 硬编码 token 风险
- 补全 Dashboard 后端关键依赖
- 修正文档与代码不一致项（启动命令、Free 限额）

## Phase B: 后端结构拆分（建议优先）

目标：把 `dashboard/backend/main.py`（>600 行）拆成模块化结构。

建议目录：

```text
dashboard/backend/
  app.py                 # FastAPI app 初始化
  routers/
    market.py            # price/chart/search/hot
    watchlist.py         # watchlist CRUD
    ai.py                # chat/analyze/config
    ws.py                # websocket endpoint
  services/
    market_service.py
    analysis_service.py
    chat_service.py
  core/
    paths.py
    settings.py
```

## Phase C: 业务模块落地

- `daemon/`：市场轮询、预警触发、冷却去重
- `alerts/`：预警规则与模板
- `telegram/`：Bot 命令与权限分层
- `ai/`：AI 解释与结果缓存策略

## Phase D: 测试与发布

- 引入 `pytest`
- 覆盖 `db/store.py` 与关键 API 路由
- 增加 `pre-commit`（lint/format/type check）
- 发布 `v0.2.0`（Dashboard + 基础预警）
