"""Trading domain APIs (strategies/orders/positions/risk/agent-runs)."""

import json
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.state import demo_user, store
from services.execution_service import (
    execute_order,
    execute_paper_order,
    get_execution_config,
    set_execution_config,
)

router = APIRouter(prefix="/api")


class CreateStrategyRequest(BaseModel):
    name: str
    market: str
    symbol: str
    timeframe: str = "1d"
    status: str = "ACTIVE"
    config: dict = Field(default_factory=dict)


class CreateRiskRuleRequest(BaseModel):
    name: str
    rule_type: str
    value: dict = Field(default_factory=dict)
    enabled: bool = True


class PaperOrderRequest(BaseModel):
    symbol: str
    side: str
    order_type: str = "MARKET"
    quantity: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    tif: str = "DAY"
    strategy_id: Optional[int] = None
    price_hint: Optional[float] = None


class UpdateOrderStatusRequest(BaseModel):
    status: str
    broker_order_id: Optional[str] = None
    reject_reason: Optional[str] = None


class UpdateExecutionConfigRequest(BaseModel):
    mode: Optional[str] = None
    kill_switch: Optional[bool] = None


@router.get("/strategies")
async def list_strategies(status: Optional[str] = None):
    rows = store.list_strategies(demo_user.id, status=status)
    return [asdict(x) for x in rows]


@router.post("/strategies")
async def create_strategy(req: CreateStrategyRequest):
    strategy_id = store.create_strategy(
        user_id=demo_user.id,
        name=req.name,
        market=req.market,
        symbol=req.symbol,
        timeframe=req.timeframe,
        config_json=json.dumps(req.config, ensure_ascii=False),
        status=req.status,
    )
    return {"success": True, "strategy_id": strategy_id}


@router.get("/orders")
async def list_orders(status: Optional[str] = None, limit: int = 100):
    rows = store.list_orders(demo_user.id, status=status, limit=limit)
    return [asdict(x) for x in rows]


@router.post("/orders/paper")
async def place_paper_order(req: PaperOrderRequest):
    result = execute_paper_order(demo_user.id, req.model_dump())
    return result


@router.post("/orders/execute")
async def execute_order_unified(req: PaperOrderRequest):
    result = execute_order(demo_user.id, req.model_dump())
    return result


@router.post("/orders/{order_id}/status")
async def update_order_status(order_id: int, req: UpdateOrderStatusRequest):
    store.update_order_status(
        order_id,
        req.status,
        broker_order_id=req.broker_order_id,
        reject_reason=req.reject_reason,
    )
    order = store.get_order_by_id(order_id)
    return {"success": True, "order": asdict(order) if order else None}


@router.get("/positions")
async def list_positions():
    rows = store.get_open_positions(demo_user.id)
    return [asdict(x) for x in rows]


@router.get("/risk-rules")
async def list_risk_rules(enabled_only: bool = True):
    rows = store.list_risk_rules(demo_user.id, enabled_only=enabled_only)
    return [asdict(x) for x in rows]


@router.post("/risk-rules")
async def create_risk_rule(req: CreateRiskRuleRequest):
    rid = store.create_risk_rule(
        user_id=demo_user.id,
        name=req.name,
        rule_type=req.rule_type,
        value_json=json.dumps(req.value, ensure_ascii=False),
        enabled=req.enabled,
    )
    return {"success": True, "risk_rule_id": rid}


@router.get("/agent-runs")
async def list_agent_runs(limit: int = 50):
    rows = store.list_recent_agent_runs(demo_user.id, limit=limit)
    return [asdict(x) for x in rows]


@router.get("/execution/config")
async def fetch_execution_config():
    return get_execution_config()


@router.post("/execution/config")
async def update_execution_config(req: UpdateExecutionConfigRequest):
    return set_execution_config(mode=req.mode, kill_switch=req.kill_switch)
