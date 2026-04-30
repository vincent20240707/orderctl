from __future__ import annotations

from typing import Any

from safe_ib_order_gateway.services.hard_gate_service import _position_after
from safe_ib_order_gateway.services.health_service import make_client
from safe_ib_order_gateway.services.storage import append_audit, load_latest_snapshot, load_plan, save_plan


def local_preview(plan_id: str) -> dict[str, Any]:
    plan = load_plan(plan_id)
    snapshot = load_latest_snapshot()
    intent = plan["intent"]
    qty = int(intent["quantity"])
    price = intent.get("limit_price") or intent.get("stop_price") or snapshot.get("market", {}).get("last")
    estimated_notional = float(price) * qty if price is not None else None
    preview = {
        "plan_id": plan_id,
        "preview_type": "LOCAL_SAFE_PREVIEW_NOT_IBKR_WHAT_IF",
        "symbol": intent["symbol"],
        "side": intent["side"],
        "semantic_action": intent["intent_type"],
        "order_role": intent["order_role"],
        "quantity": qty,
        "order_type": intent["order_type"],
        "limit_price": intent.get("limit_price"),
        "stop_price": intent.get("stop_price"),
        "estimated_notional": estimated_notional,
        "position_before": snapshot.get("position"),
        "position_after": _position_after(intent, snapshot),
        "status": "PREVIEW_READY",
        "warnings": [
            "This is a local preview only. It does not query IBKR margin/commission impact."
        ],
    }
    plan["preview"] = preview
    plan["status"] = "PREVIEW_READY"
    save_plan(plan)
    append_audit("LOCAL_PREVIEW", preview)
    return preview


def ibkr_what_if_preview(config: dict[str, Any], plan_id: str, client_id: int | None = None) -> dict[str, Any]:
    plan = load_plan(plan_id)
    client = make_client(config, "preview", client_id)
    preview = client.what_if(plan)

    # Add local position/notional fields so the ticket remains readable even when
    # IBKR orderState omits margin values for some instruments/order types.
    snapshot = load_latest_snapshot()
    intent = plan["intent"]
    price = intent.get("limit_price") or intent.get("stop_price") or snapshot.get("market", {}).get("last")
    preview["estimated_notional"] = float(price) * int(intent["quantity"]) if price is not None else None
    preview["position_before"] = snapshot.get("position")
    preview["position_after"] = _position_after(intent, snapshot)

    plan["preview"] = preview
    plan["status"] = "PREVIEW_READY"
    save_plan(plan)
    append_audit("IBKR_WHAT_IF_PREVIEW", preview)
    return preview
