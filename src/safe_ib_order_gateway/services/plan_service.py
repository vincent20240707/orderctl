from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from safe_ib_order_gateway.domain.models import OrderIntent, utc_now_iso
from safe_ib_order_gateway.services.storage import append_audit, save_plan, stable_hash


def create_plan(intent_file: str, mode: str) -> dict[str, Any]:
    path = Path(intent_file)
    data = json.loads(path.read_text(encoding="utf-8"))
    intent = OrderIntent.from_dict(data)
    intent_data = intent.to_dict()
    plan_id = "ORD-" + utc_now_iso().replace(":", "").replace("-", "").split(".")[0] + "-" + uuid.uuid4().hex[:6]
    plan = {
        "plan_id": plan_id,
        "mode": mode,
        "created_at": utc_now_iso(),
        "status": "DRAFT",
        "intent": intent_data,
        "intent_hash": stable_hash(intent_data),
        "hard_check": None,
        "ai_review": None,
        "preview": None,
        "ticket": None,
        "submit": None,
    }
    save_plan(plan)
    append_audit("PLAN_CREATED", {"plan_id": plan_id, "intent": intent_data})
    return {"plan_id": plan_id, "intent_hash": plan["intent_hash"], "status": "DRAFT"}
