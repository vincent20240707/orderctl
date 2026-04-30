from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from safe_ib_order_gateway.config import (
    AUDIT_FILE,
    LATEST_SNAPSHOT_FILE,
    PLANS_DIR,
    REVIEWS_DIR,
    TICKETS_DIR,
    ensure_var_dirs,
)
from safe_ib_order_gateway.domain.models import utc_now_iso


def stable_hash(data: dict[str, Any]) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def plan_path(plan_id: str) -> Path:
    return PLANS_DIR / f"{plan_id}.json"


def ticket_path(plan_id: str) -> Path:
    return TICKETS_DIR / f"{plan_id}.txt"


def review_path(plan_id: str) -> Path:
    return REVIEWS_DIR / f"{plan_id}.json"


def save_latest_snapshot(snapshot: dict[str, Any]) -> None:
    ensure_var_dirs()
    write_json(LATEST_SNAPSHOT_FILE, snapshot)


def load_latest_snapshot() -> dict[str, Any]:
    if not LATEST_SNAPSHOT_FILE.exists():
        raise FileNotFoundError("No latest snapshot found. Run orderctl snapshot first.")
    return read_json(LATEST_SNAPSHOT_FILE)


def save_plan(plan: dict[str, Any]) -> None:
    ensure_var_dirs()
    write_json(plan_path(plan["plan_id"]), plan)


def load_plan(plan_id: str) -> dict[str, Any]:
    path = plan_path(plan_id)
    if not path.exists():
        raise FileNotFoundError(f"Plan not found: {plan_id}")
    return read_json(path)


def append_audit(event_type: str, payload: dict[str, Any]) -> None:
    ensure_var_dirs()
    row = {"timestamp": utc_now_iso(), "event_type": event_type, "payload": payload}
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_audit_lines(limit: int = 50) -> list[dict[str, Any]]:
    if not AUDIT_FILE.exists():
        return []
    lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-limit:]:
        if line.strip():
            out.append(json.loads(line))
    return out
