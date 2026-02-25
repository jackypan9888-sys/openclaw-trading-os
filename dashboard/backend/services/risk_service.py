"""Pre-trade risk checks for paper/live execution."""

import json

from core.state import provider, store


def _to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _resolve_price(symbol: str, price_hint: float = None, provider_obj=None) -> float:
    if price_hint is not None:
        return float(price_hint)

    provider_ref = provider_obj or provider
    data = provider_ref.get_price(symbol.upper())
    if not data or data.get("price") is None:
        return 0.0
    return _to_float(data.get("price"), 0.0)


def check_order_risk(
    user_id: int,
    symbol: str,
    side: str,
    quantity: float,
    price_hint: float = None,
    store_obj=None,
    provider_obj=None,
) -> tuple[bool, list[str], float]:
    """Return (allowed, reasons, reference_price)."""
    store_ref = store_obj or store

    side_u = side.upper()
    qty = _to_float(quantity, 0.0)
    if qty <= 0:
        return False, ["quantity must be > 0"], 0.0

    ref_price = _resolve_price(symbol, price_hint=price_hint, provider_obj=provider_obj)
    if ref_price <= 0:
        return False, ["unable to resolve market price"], 0.0

    reasons: list[str] = []
    rules = store_ref.list_risk_rules(user_id, enabled_only=True)
    pos = store_ref.get_position(user_id, symbol.upper())
    current_qty = pos.quantity if pos else 0.0

    # Hard guard: no shorting in current paper mode.
    if side_u == "SELL" and current_qty < qty:
        reasons.append("insufficient position quantity for SELL")

    for rule in rules:
        try:
            cfg = json.loads(rule.value_json or "{}")
        except Exception:
            reasons.append(f"invalid risk rule config: {rule.name}")
            continue

        rtype = rule.rule_type

        if rtype == "max_orders_per_day":
            limit = int(cfg.get("count", 0))
            if limit > 0 and store_ref.count_orders_today(user_id) >= limit:
                reasons.append(f"max_orders_per_day exceeded ({limit})")

        elif rtype == "max_order_notional_usd":
            limit = _to_float(cfg.get("usd", 0.0), 0.0)
            notional = qty * ref_price
            if limit > 0 and notional > limit:
                reasons.append(f"order notional {notional:.2f} > {limit:.2f}")

        elif rtype == "max_position_value_usd":
            limit = _to_float(cfg.get("usd", 0.0), 0.0)
            if limit > 0:
                projected_qty = current_qty + qty if side_u == "BUY" else max(0.0, current_qty - qty)
                projected_value = projected_qty * ref_price
                if projected_value > limit:
                    reasons.append(f"position value {projected_value:.2f} > {limit:.2f}")

        elif rtype == "allowed_symbols":
            symbols = [str(s).upper() for s in cfg.get("symbols", [])]
            if symbols and symbol.upper() not in symbols:
                reasons.append(f"symbol {symbol.upper()} not in allowed list")

    return len(reasons) == 0, reasons, ref_price
