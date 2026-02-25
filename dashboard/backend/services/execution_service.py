"""Paper execution workflow with risk guard and run logging."""

import json

from core.state import store
from services.risk_service import check_order_risk


def _safe_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def _apply_fill_to_position(store_ref, user_id: int, symbol: str, side: str, qty: float, fill_price: float):
    pos = store_ref.get_position(user_id, symbol.upper())
    cur_qty = pos.quantity if pos else 0.0
    cur_avg = pos.avg_cost if pos else 0.0

    side_u = side.upper()
    if side_u == "BUY":
        new_qty = cur_qty + qty
        if new_qty <= 0:
            new_avg = 0.0
        else:
            new_avg = ((cur_qty * cur_avg) + (qty * fill_price)) / new_qty
    else:  # SELL
        new_qty = max(0.0, cur_qty - qty)
        new_avg = 0.0 if new_qty == 0 else cur_avg

    store_ref.upsert_position(
        user_id=user_id,
        symbol=symbol.upper(),
        quantity=new_qty,
        avg_cost=new_avg,
        last_price=fill_price,
    )


def execute_paper_order(
    user_id: int,
    payload: dict,
    store_obj=None,
    provider_obj=None,
    create_run: bool = True,
    run_id: int = None,
) -> dict:
    """Create + risk-check + simulate order execution in paper mode."""
    store_ref = store_obj or store

    symbol = str(payload.get("symbol", "")).upper().strip()
    side = str(payload.get("side", "BUY")).upper().strip()
    order_type = str(payload.get("order_type", "MARKET")).upper().strip()
    quantity = float(payload.get("quantity", 0))
    limit_price = payload.get("limit_price")
    stop_price = payload.get("stop_price")
    tif = str(payload.get("tif", "DAY")).upper().strip()
    strategy_id = payload.get("strategy_id")

    if create_run:
        run_id = store_ref.record_agent_run(
            user_id=user_id,
            strategy_id=strategy_id,
            run_type="execute",
            input_json=_safe_json(payload),
        )

    if not symbol:
        store_ref.update_agent_run(run_id, "FAILED", error="missing symbol")
        return {"success": False, "error": "missing symbol", "run_id": run_id}

    allowed, reasons, ref_price = check_order_risk(
        user_id=user_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price_hint=payload.get("price_hint"),
        store_obj=store_ref,
        provider_obj=provider_obj,
    )

    if not allowed:
        reason = "; ".join(reasons)
        order_id = store_ref.create_order(
            user_id=user_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
            tif=tif,
            status="REJECTED",
        )
        store_ref.update_order_status(order_id, "REJECTED", reject_reason=reason)
        store_ref.update_agent_run(
            run_id,
            "FAILED",
            output_json=_safe_json({"order_id": order_id}),
            error=reason,
        )
        return {
            "success": False,
            "status": "REJECTED",
            "error": reason,
            "order_id": order_id,
            "run_id": run_id,
        }

    order_id = store_ref.create_order(
        user_id=user_id,
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
        stop_price=stop_price,
        tif=tif,
        status="SUBMITTED",
    )

    filled = False
    fill_price = ref_price

    if order_type == "MARKET":
        filled = True

    elif order_type == "LIMIT":
        if limit_price is None:
            store_ref.update_order_status(order_id, "REJECTED", reject_reason="missing limit_price")
            store_ref.update_agent_run(run_id, "FAILED", output_json=_safe_json({"order_id": order_id}), error="missing limit_price")
            return {
                "success": False,
                "status": "REJECTED",
                "error": "missing limit_price",
                "order_id": order_id,
                "run_id": run_id,
            }
        lp = float(limit_price)
        if (side == "BUY" and fill_price <= lp) or (side == "SELL" and fill_price >= lp):
            filled = True

    if filled:
        store_ref.update_order_status(order_id, "FILLED", broker_order_id=f"paper-{order_id}")
        _apply_fill_to_position(store_ref, user_id, symbol, side, quantity, fill_price)
        store_ref.update_agent_run(
            run_id,
            "SUCCESS",
            output_json=_safe_json({"order_id": order_id, "status": "FILLED", "fill_price": fill_price}),
        )
        return {
            "success": True,
            "status": "FILLED",
            "order_id": order_id,
            "fill_price": fill_price,
            "run_id": run_id,
        }

    store_ref.update_agent_run(
        run_id,
        "SUCCESS",
        output_json=_safe_json({"order_id": order_id, "status": "SUBMITTED"}),
    )
    return {
        "success": True,
        "status": "SUBMITTED",
        "order_id": order_id,
        "reference_price": fill_price,
        "run_id": run_id,
    }


def get_execution_config(store_obj=None) -> dict:
    store_ref = store_obj or store
    return {
        "mode": store_ref.get_execution_mode(),
        "kill_switch": store_ref.is_kill_switch_on(),
    }


def set_execution_config(mode: str = None, kill_switch: bool = None, store_obj=None) -> dict:
    store_ref = store_obj or store
    if mode is not None:
        mode_u = mode.upper()
        if mode_u not in {"PAPER", "LIVE"}:
            return {"success": False, "error": "mode must be PAPER or LIVE"}
        store_ref.set_execution_mode(mode_u)
    if kill_switch is not None:
        store_ref.set_kill_switch(bool(kill_switch))
    return {"success": True, **get_execution_config(store_ref)}


def execute_order(user_id: int, payload: dict, store_obj=None, provider_obj=None) -> dict:
    """Unified execution gateway with global mode + kill switch guards."""
    store_ref = store_obj or store
    config = get_execution_config(store_ref)

    run_id = store_ref.record_agent_run(
        user_id=user_id,
        strategy_id=payload.get("strategy_id"),
        run_type="execute",
        input_json=_safe_json(payload),
    )

    if config["kill_switch"]:
        store_ref.update_agent_run(run_id, "FAILED", error="kill_switch_enabled")
        return {
            "success": False,
            "status": "BLOCKED",
            "reason_code": "KILL_SWITCH",
            "error": "kill switch is enabled",
            "run_id": run_id,
            "mode": config["mode"],
        }

    if config["mode"] == "LIVE":
        store_ref.update_agent_run(run_id, "FAILED", error="live_mode_not_implemented")
        return {
            "success": False,
            "status": "REJECTED",
            "reason_code": "LIVE_NOT_IMPLEMENTED",
            "error": "live execution adapter not implemented yet",
            "run_id": run_id,
            "mode": config["mode"],
        }

    # PAPER mode
    result = execute_paper_order(
        user_id=user_id,
        payload=payload,
        store_obj=store_ref,
        provider_obj=provider_obj,
        create_run=False,
        run_id=run_id,
    )
    result["mode"] = config["mode"]
    return result
