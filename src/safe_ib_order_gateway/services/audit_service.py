from __future__ import annotations

from safe_ib_order_gateway.services.storage import load_plan, read_audit_lines


def audit_list(limit: int = 50) -> dict:
    return {"events": read_audit_lines(limit=limit)}


def audit_show(plan_id: str) -> dict:
    return load_plan(plan_id)
