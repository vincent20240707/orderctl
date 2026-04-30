from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safe_ib_order_gateway.services.storage import append_audit, review_path, save_plan, load_plan, write_json


def attach_review(plan_id: str, review_file: str) -> dict[str, Any]:
    plan = load_plan(plan_id)
    review = json.loads(Path(review_file).read_text(encoding="utf-8"))
    verdict = str(review.get("verdict", "UNKNOWN")).upper()
    if verdict not in {"ALLOW", "WARN", "BLOCK", "UNKNOWN", "PASS"}:
        verdict = "UNKNOWN"
        review["verdict"] = verdict
    plan["ai_review"] = review
    plan["status"] = "AI_REVIEW_ATTACHED"
    save_plan(plan)
    write_json(review_path(plan_id), review)
    append_audit("AI_REVIEW_ATTACHED", {"plan_id": plan_id, "review": review})
    return {"plan_id": plan_id, "verdict": verdict, "status": "AI_REVIEW_ATTACHED"}
