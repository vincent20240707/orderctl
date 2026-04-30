from __future__ import annotations

from typing import Any

from safe_ib_order_gateway.config import PLANS_DIR
from safe_ib_order_gateway.services.health_service import make_client
from safe_ib_order_gateway.services.storage import append_audit, read_json

TERMINAL_PLAN_STATUSES = {
    "SUBMITTED",
    "SUBMIT_BLOCKED",
    "CANCEL_REQUESTED",
    "REPLACE_SUBMITTED",
    "ARCHIVED",
    "HISTORICAL",
}


def reconcile(
    config: dict[str, Any],
    symbol: str | None,
    mode: str,
    client_id: int | None = None,
    all_symbols: bool = False,
    compact: bool = False,
) -> dict[str, Any]:
    if all_symbols or not symbol:
        return reconcile_all(config, mode, client_id, compact=compact)

    symbol = symbol.upper().strip()
    client = make_client(config, "reconcile", client_id)
    snap = client.snapshot(symbol)
    issues = _symbol_issues(symbol, snap)
    plans = _plans_for_symbols({symbol})

    result = {
        "status": "WARN" if issues or snap.get("status") == "WARN" else "PASS",
        "verdict": "WARN" if issues or snap.get("status") == "WARN" else "PASS",
        "mode": mode,
        "scope": "symbol",
        "symbol": symbol,
        "ibkr_current_state": {
            "position": snap.get("position"),
            "open_orders": snap.get("open_orders", []),
            "market": snap.get("market"),
        },
        "local_state": plans,
        "risk_flags": issues,
        "warnings": snap.get("warnings", []),
        "summary": {
            "ibkr_open_orders_count": len(snap.get("open_orders", []) or []),
            "local_active_plans_count": len(plans["active_plans"]),
            "local_historical_plans_count": len(plans["historical_plans"]),
            "active_risk_count": len(issues),
        },
    }
    if compact:
        result = _compact_reconcile(result)
    append_audit("RECONCILE", result)
    return result


def reconcile_all(config: dict[str, Any], mode: str, client_id: int | None = None, compact: bool = False) -> dict[str, Any]:
    client = make_client(config, "reconcile", client_id)
    portfolio = client.portfolio_snapshot(with_quotes=False, with_pnl=False, compact=False)
    positions = portfolio.get("positions", []) or []
    open_orders = portfolio.get("open_orders", []) or []
    risk_flags: list[dict[str, Any]] = list(portfolio.get("risk_flags") or portfolio.get("issues") or [])

    symbols = set()
    for p in positions:
        if p.get("symbol"):
            symbols.add(str(p["symbol"]).upper())
    for o in open_orders:
        if o.get("symbol"):
            symbols.add(str(o["symbol"]).upper())

    plans = _plans_for_symbols(symbols if symbols else None)

    result = {
        "status": "WARN" if risk_flags or portfolio.get("status") == "WARN" else "PASS",
        "verdict": "WARN" if risk_flags or portfolio.get("status") == "WARN" else "PASS",
        "mode": mode,
        "scope": "all",
        "ibkr_current_state": {
            "positions": positions,
            "open_orders": open_orders,
        },
        "local_state": plans,
        "risk_flags": risk_flags,
        "warnings": portfolio.get("warnings", []),
        "summary": {
            "ibkr_positions_count": len(positions),
            "ibkr_open_orders_count": len(open_orders),
            "local_active_plans_count": len(plans["active_plans"]),
            "local_historical_plans_count": len(plans["historical_plans"]),
            "active_risk_count": len(risk_flags),
        },
        "note": "local_state.historical_plans are local orderctl records only; they are not current IBKR open orders.",
        "client_id_strategy": portfolio.get("client_id_strategy"),
        "client_id_used": portfolio.get("client_id_used"),
        "client_id_attempts": portfolio.get("client_id_attempts"),
    }
    if compact:
        result = _compact_reconcile(result)
    append_audit("RECONCILE_ALL", result)
    return result


def _symbol_issues(symbol: str, snap: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    position = snap.get("position", {}) or {}
    open_orders = snap.get("open_orders", []) or []

    if position.get("side") == "FLAT" and open_orders:
        issues.append(
            {
                "level": "WARN",
                "category": "OPEN_ORDERS_WITH_FLAT_POSITION",
                "symbol": symbol,
                "message": f"当前 {symbol} 无持仓，但仍有 {len(open_orders)} 张未成交订单，请确认是否为开仓计划或残留订单。",
            }
        )

    pos_qty = int(position.get("quantity") or 0)
    if pos_qty > 0:
        closing_qty = 0.0
        for order in open_orders:
            side = str(order.get("side") or "").upper()
            if (position.get("side") == "LONG" and side == "SELL") or (
                position.get("side") == "SHORT" and side == "BUY"
            ):
                closing_qty += float(order.get("quantity") or 0)
        if closing_qty > pos_qty:
            issues.append(
                {
                    "level": "WARN",
                    "category": "CLOSING_ORDERS_EXCEED_POSITION",
                    "symbol": symbol,
                    "message": f"平仓/保护类订单合计数量 {closing_qty} 超过当前持仓 {pos_qty}，可能导致反手。",
                }
            )
    return issues


def _plans_for_symbols(symbols: set[str] | None) -> dict[str, list[dict[str, Any]]]:
    active: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []
    if not PLANS_DIR.exists():
        return {"active_plans": active, "historical_plans": historical}

    for path in sorted(PLANS_DIR.glob("*.json"))[-200:]:
        try:
            plan = read_json(path)
            intent = plan.get("intent") or {}
            sym = str(intent.get("symbol") or "").upper()
            if symbols is not None and sym not in symbols:
                continue
            status = str(plan.get("status") or "UNKNOWN").upper()
            item = {
                "plan_id": plan.get("plan_id"),
                "symbol": sym,
                "status": status,
                "intent_type": intent.get("intent_type"),
                "side": intent.get("side"),
                "quantity": intent.get("quantity"),
                "limit_price": intent.get("limit_price"),
                "note": "Local orderctl plan; not an IBKR open order unless matched in ibkr_current_state.open_orders.",
            }
            if status in TERMINAL_PLAN_STATUSES or plan.get("submit"):
                item["note"] = "Historical local plan, not a current IBKR open order."
                historical.append(item)
            else:
                active.append(item)
        except Exception:
            continue
    return {"active_plans": active, "historical_plans": historical}


def _compact_reconcile(result: dict[str, Any]) -> dict[str, Any]:
    ibkr = result.get("ibkr_current_state", {}) or {}
    positions = ibkr.get("positions") or ([] if ibkr.get("position") is None else [ibkr.get("position")])
    open_orders = ibkr.get("open_orders", []) or []
    return {
        "status": result.get("status"),
        "verdict": result.get("verdict"),
        "mode": result.get("mode"),
        "scope": result.get("scope"),
        "summary": result.get("summary"),
        "ibkr_current_state": {
            "positions": positions,
            "open_orders": [
                {
                    "symbol": o.get("symbol"),
                    "order_id": o.get("order_id"),
                    "side": o.get("side"),
                    "quantity": o.get("quantity"),
                    "order_type": o.get("order_type"),
                    "limit_price": o.get("limit_price"),
                    "stop_price": o.get("stop_price"),
                    "status": o.get("status"),
                }
                for o in open_orders
            ],
        },
        "local_state": {
            "active_plans_count": len((result.get("local_state") or {}).get("active_plans", [])),
            "historical_plans_count": len((result.get("local_state") or {}).get("historical_plans", [])),
            "historical_plans_note": "Historical local plans are not current IBKR open orders.",
        },
        "risk_flags": result.get("risk_flags", []),
        "warnings": result.get("warnings", []),
        "client_id_strategy": result.get("client_id_strategy"),
        "client_id_used": result.get("client_id_used"),
        "client_id_attempts": result.get("client_id_attempts"),
    }
