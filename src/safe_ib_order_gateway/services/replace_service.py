from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from safe_ib_order_gateway.config import VAR_DIR
from safe_ib_order_gateway.domain.models import utc_now_iso
from safe_ib_order_gateway.services.health_service import make_client
from safe_ib_order_gateway.services.storage import append_audit, read_json, write_json

REPLACE_DIR = VAR_DIR / "replace_plans"


def _replace_path(replace_plan_id: str) -> Path:
    return REPLACE_DIR / f"{replace_plan_id}.json"


def replace_plan(config: dict[str, Any], mode: str, order_id: int, new_limit_price: float, client_id: int | None = None) -> dict[str, Any]:
    client = make_client(config, "replace", client_id)
    matches = client.find_open_orders(order_id=order_id)
    if not matches:
        return {"status": "ERROR", "error": "ORDER_NOT_FOUND_OR_NOT_OPEN", "order_id": order_id}
    original = matches[0]
    if str(original.get("order_type", "")).upper() != "LMT":
        return {"status": "ERROR", "error": "ONLY_LIMIT_ORDER_REPLACE_SUPPORTED", "order_id": order_id}
    replace_plan_id = "RPL-" + utc_now_iso().replace(":", "").replace("-", "").split(".")[0] + "-" + uuid.uuid4().hex[:6]
    plan = {
        "replace_plan_id": replace_plan_id,
        "mode": mode,
        "created_at": utc_now_iso(),
        "status": "DRAFT",
        "original_order": original,
        "changes": {"limit_price": {"old": original.get("limit_price"), "new": float(new_limit_price)}},
        "confirmation_phrase": f"REPLACE ORDER {order_id} LIMIT {float(new_limit_price):.2f}",
    }
    write_json(_replace_path(replace_plan_id), plan)
    append_audit("REPLACE_PLAN_CREATED", plan)
    return plan


def replace_check(replace_plan_id: str) -> dict[str, Any]:
    plan = read_json(_replace_path(replace_plan_id))
    blocks: list[str] = []
    warnings: list[str] = []
    original = plan.get("original_order", {})
    new_price = plan.get("changes", {}).get("limit_price", {}).get("new")
    if new_price is None:
        blocks.append("MISSING_NEW_LIMIT_PRICE")
    if str(original.get("order_type", "")).upper() != "LMT":
        blocks.append("ONLY_LIMIT_ORDER_REPLACE_SUPPORTED")
    # Keep v2 flexible but safe: do not allow quantity/direction/order type edits.
    result = {
        "replace_plan_id": replace_plan_id,
        "verdict": "BLOCK" if blocks else "PASS",
        "blocks": blocks,
        "warnings": warnings,
        "changes": plan.get("changes"),
        "original_order": original,
        "status": "REPLACE_CHECKED_BLOCKED" if blocks else "REPLACE_CHECKED_PASS",
    }
    plan["check"] = result
    plan["status"] = result["status"]
    write_json(_replace_path(replace_plan_id), plan)
    append_audit("REPLACE_CHECK", result)
    return result


def replace_ticket(replace_plan_id: str) -> dict[str, Any]:
    plan = read_json(_replace_path(replace_plan_id))
    original = plan.get("original_order", {})
    phrase = plan.get("confirmation_phrase")
    lines = [
        "改单确认票据",
        "",
        f"Replace Plan ID：{replace_plan_id}",
        f"原订单号：{original.get('order_id')}",
        f"股票：{original.get('symbol')}",
        f"方向：{original.get('side')}",
        f"数量：{original.get('quantity')}",
        f"订单类型：{original.get('order_type')}",
        f"原限价：{plan.get('changes', {}).get('limit_price', {}).get('old')}",
        f"新限价：{plan.get('changes', {}).get('limit_price', {}).get('new')}",
        "",
        "确认语：",
        str(phrase),
        "",
        "当前版本只支持修改限价，不支持修改数量、方向或订单类型。",
    ]
    text = "\n".join(lines)
    plan["ticket"] = {"text": text, "confirmation_phrase": phrase}
    plan["status"] = "REPLACE_TICKET_READY"
    write_json(_replace_path(replace_plan_id), plan)
    append_audit("REPLACE_TICKET", {"replace_plan_id": replace_plan_id, "confirmation_phrase": phrase})
    return {"replace_plan_id": replace_plan_id, "confirmation_phrase": phrase, "ticket": text}


def replace_submit(config: dict[str, Any], mode: str, replace_plan_id: str, phrase: str, client_id: int | None = None) -> dict[str, Any]:
    plan = read_json(_replace_path(replace_plan_id))
    expected = plan.get("confirmation_phrase")
    if phrase != expected:
        return {"status": "ERROR", "error": "CONFIRMATION_PHRASE_MISMATCH", "expected": expected}
    check = plan.get("check") or replace_check(replace_plan_id)
    if check.get("verdict") != "PASS":
        return {"status": "ERROR", "error": "REPLACE_CHECK_NOT_PASS", "check": check}
    original = plan["original_order"]
    new_price = float(plan["changes"]["limit_price"]["new"])
    client = make_client(config, "replace", client_id)
    result = client.replace_limit_price(int(original["order_id"]), new_price)
    result["replace_plan_id"] = replace_plan_id
    plan["submit"] = result
    plan["status"] = result.get("status", "REPLACE_SUBMITTED")
    write_json(_replace_path(replace_plan_id), plan)
    append_audit("REPLACE_SUBMIT", result)
    return result
