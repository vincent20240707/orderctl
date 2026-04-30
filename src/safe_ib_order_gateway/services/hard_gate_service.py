from __future__ import annotations

from typing import Any

from safe_ib_order_gateway.domain.enums import IntentType, OrderType, PositionSide, Side, Verdict
from safe_ib_order_gateway.services.storage import append_audit, load_latest_snapshot, load_plan, save_plan


def _market_reference_price(snapshot: dict[str, Any]) -> float | None:
    market = snapshot.get("market", {}) or {}
    for key in ("last", "ask", "bid"):
        value = market.get(key)
        if value is not None:
            try:
                return float(value)
            except Exception:
                pass
    return None


def _position_after(intent: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    pos = snapshot.get("position", {}) or {}
    side = pos.get("side", "UNKNOWN")
    qty = int(pos.get("quantity") or 0)
    order_qty = int(intent.get("quantity") or 0)
    order_side = intent.get("side")

    signed = 0
    if side == PositionSide.LONG.value:
        signed = qty
    elif side == PositionSide.SHORT.value:
        signed = -qty

    signed_after = signed + (order_qty if order_side == Side.BUY.value else -order_qty)
    if signed_after > 0:
        return {"side": "LONG", "quantity": signed_after}
    if signed_after < 0:
        return {"side": "SHORT", "quantity": abs(signed_after)}
    return {"side": "FLAT", "quantity": 0}


def _causes_reverse(intent: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    before = snapshot.get("position", {}) or {}
    after = _position_after(intent, snapshot)
    before_side = before.get("side")
    after_side = after.get("side")
    if before_side in ("LONG", "SHORT") and after_side in ("LONG", "SHORT"):
        return before_side != after_side
    return False


def run_hard_check(config: dict[str, Any], plan_id: str) -> dict[str, Any]:
    plan = load_plan(plan_id)
    snapshot = load_latest_snapshot()
    intent = plan["intent"]
    limits = config.get("risk_limits", {})
    blocks: list[str] = []
    warnings: list[str] = []

    if snapshot.get("symbol") != intent.get("symbol"):
        blocks.append("SNAPSHOT_SYMBOL_MISMATCH")
    if snapshot.get("mode") != plan.get("mode"):
        blocks.append("SNAPSHOT_MODE_MISMATCH")

    market_status = ((snapshot.get("market") or {}).get("market_data_status") or "UNKNOWN").upper()
    if market_status in {"MISSING", "DELAYED", "ERROR", "UNKNOWN"}:
        warnings.append(f"MARKET_DATA_STATUS_{market_status}")

    qty = int(intent.get("quantity") or 0)
    if qty <= 0:
        blocks.append("INVALID_QUANTITY")
    if qty > int(limits.get("max_single_order_qty", 0) or 0):
        blocks.append("QUANTITY_EXCEEDS_HARD_LIMIT")

    supported_types = limits.get("supported_order_types") or ["LIMIT", "STOP", "STOP_LIMIT", "MARKET"]
    if intent.get("order_type") not in supported_types:
        blocks.append("UNSUPPORTED_ORDER_TYPE_FOR_EXECUTION")

    if intent.get("order_type") == OrderType.MARKET.value and limits.get("forbid_market_order", True):
        blocks.append("MARKET_ORDER_FORBIDDEN")

    ref_price = intent.get("limit_price") or intent.get("stop_price") or _market_reference_price(snapshot)
    estimated_notional = None
    if ref_price is None:
        blocks.append("MISSING_PRICE_FOR_NOTIONAL")
    else:
        estimated_notional = float(ref_price) * qty
        if estimated_notional > float(limits.get("max_single_order_notional", 0) or 0):
            blocks.append("NOTIONAL_EXCEEDS_HARD_LIMIT")

    if bool(intent.get("outside_rth")) and not bool(limits.get("default_outside_rth", False)):
        warnings.append("OUTSIDE_RTH_REQUESTED")

    if _causes_reverse(intent, snapshot) and bool(limits.get("forbid_reverse_position", True)):
        blocks.append("REVERSE_POSITION_FORBIDDEN")

    after = _position_after(intent, snapshot)
    if intent.get("intent_type") in (IntentType.CLOSE_LONG.value, IntentType.CLOSE_SHORT.value):
        before = snapshot.get("position", {}) or {}
        if before.get("side") == "FLAT":
            blocks.append("CLOSE_REQUEST_WITH_NO_POSITION")

    verdict = Verdict.BLOCK.value if blocks else Verdict.PASS.value
    result = {
        "plan_id": plan_id,
        "verdict": verdict,
        "blocks": blocks,
        "warnings": warnings,
        "estimated_notional": estimated_notional,
        "position_before": snapshot.get("position"),
        "position_after": after,
    }
    plan["hard_check"] = result
    plan["status"] = "HARD_CHECKED_BLOCKED" if blocks else "HARD_CHECKED_PASS"
    save_plan(plan)
    append_audit("HARD_CHECK", result)
    return result
