# Phase 2 Data Model (Implemented)

本阶段已在 SQLite 中落地交易域核心表：

- `strategies`：策略定义与状态（ACTIVE/PAUSED/ARCHIVED）
- `orders`：订单意图与执行状态（NEW/SUBMITTED/FILLED/CANCELED/REJECTED）
- `positions`：当前持仓快照（按 user + symbol 唯一）
- `risk_rules`：风控规则配置（JSON）
- `agent_runs`：Agent 运行日志（输入/输出/错误/状态）

对应 DataStore 方法：

- `create_strategy/list_strategies`
- `create_order/update_order_status/list_orders`
- `upsert_position/get_open_positions`
- `create_risk_rule/list_risk_rules`
- `record_agent_run/update_agent_run/list_recent_agent_runs`

说明：

- 当前是“基础域模型 + 存储接口”落地，下一步应接 API 层与执行流程。
- 订单与持仓尚未接入 Broker Adapter（Phase 3/4）。
