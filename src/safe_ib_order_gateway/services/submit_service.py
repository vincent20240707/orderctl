from __future__ import annotations

from typing import Any

from safe_ib_order_gateway.services.hard_gate_service import run_hard_check
from safe_ib_order_gateway.services.health_service import make_client
from safe_ib_order_gateway.services.snapshot_service import snapshot as fresh_snapshot
from safe_ib_order_gateway.services.storage import append_audit, load_plan, save_plan, stable_hash


def _basic_submit_gates(config: dict[str, Any], plan: dict[str, Any], phrase: str, mode: str, approval_token: str | None) -> list[str]:
    blocks: list[str] = []

    if plan.get("mode") != mode:
        blocks.append("MODE_MISMATCH")

    intent = plan.get("intent") or {}
    if stable_hash(intent) != plan.get("intent_hash"):
        blocks.append("INTENT_HASH_MISMATCH")

    ticket = plan.get("ticket") or {}
    expected = ticket.get("confirmation_phrase")
    if not expected:
        blocks.append("MISSING_TICKET")
    elif phrase != expected:
        blocks.append("CONFIRMATION_PHRASE_MISMATCH")

    hard = plan.get("hard_check") or {}
    if hard.get("verdict") != "PASS":
        blocks.append("HARD_CHECK_NOT_PASS")

    ai_review = plan.get("ai_review") or {}
    if not ai_review:
        blocks.append("MISSING_AI_REVIEW")
    else:
        verdict = str(ai_review.get("verdict", "UNKNOWN")).upper()
        if verdict in {"BLOCK", "UNKNOWN", "ERROR"}:
            blocks.append("AI_REVIEW_NOT_ALLOWABLE")

    preview = plan.get("preview") or {}
    if not preview:
        blocks.append("MISSING_PREVIEW")

    if mode == "live":
        live = config.get("live_trading", {})
        if not bool(live.get("enabled", False)):
            blocks.append("LIVE_TRADING_DISABLED")
        if bool(live.get("require_approval_token", True)):
            expected_token = str(live.get("approval_token", "")).strip()
            if not approval_token:
                blocks.append("MISSING_LIVE_APPROVAL_TOKEN")
            elif expected_token and approval_token != expected_token:
                blocks.append("LIVE_APPROVAL_TOKEN_MISMATCH")
    elif mode == "paper":
        paper_exec = config.get("paper_trading", {})
        if not bool(paper_exec.get("allow_submit", True)):
            blocks.append("PAPER_SUBMIT_DISABLED")

    return blocks


def submit_order(config: dict[str, Any], plan_id: str, phrase: str, mode: str, approval_token: str | None = None, client_id: int | None = None) -> dict[str, Any]:
    """Submit an already-reviewed plan to IBKR.

    Safety design:
    - This function does not accept symbol/qty/price.
    - It only submits a saved plan_id after ticket phrase and gates pass.
    - It refreshes IBKR facts immediately before submit and re-runs hard gates.
    """
    plan = load_plan(plan_id)
    blocks = _basic_submit_gates(config, plan, phrase, mode, approval_token)

    # Do not touch IBKR if basic local gates already fail.
    if blocks:
        return _block_submit(plan, mode, blocks, "Submit blocked before fresh IBKR refresh.")

    symbol = plan["intent"]["symbol"]
    try:
        fresh = fresh_snapshot(config, symbol, fresh=True)
    except Exception as exc:
        return _block_submit(plan, mode, ["FRESH_SNAPSHOT_FAILED"], f"Fresh snapshot failed: {exc}")

    # Snapshot may return WARN when bid/ask/last is missing. A user-specified LIMIT order can still proceed.
    if fresh.get("status") == "ERROR":
        return _block_submit(plan, mode, ["FRESH_SNAPSHOT_ERROR"], "Fresh snapshot status is ERROR.")

    # Re-run deterministic gates against the just-refreshed snapshot. This also
    # updates plan[hard_check] in storage, so reload the plan after it.
    hard = run_hard_check(config, plan_id)
    if hard.get("verdict") != "PASS":
        return _block_submit(plan, mode, ["FRESH_HARD_CHECK_NOT_PASS", *hard.get("blocks", [])], "Fresh hard gate failed.")

    plan = load_plan(plan_id)
    # Re-check local gates after hard check refresh.
    blocks = _basic_submit_gates(config, plan, phrase, mode, approval_token)
    if blocks:
        return _block_submit(plan, mode, blocks, "Submit blocked after fresh hard gate.")

    try:
        client = make_client(config, "submit", client_id)
        submit_result = client.place_order(plan)
    except Exception as exc:
        return _block_submit(plan, mode, ["IBKR_PLACE_ORDER_FAILED"], f"IBKR placeOrder failed: {exc}")

    result = {
        "plan_id": plan_id,
        "mode": mode,
        "verdict": "SUBMITTED",
        "status": "SUBMITTED",
        "message": "Order was submitted to IBKR. Check TWS/IB Gateway and audit output for status.",
        "ibkr": submit_result,
    }
    plan["submit"] = result
    plan["status"] = "SUBMITTED"
    save_plan(plan)
    append_audit("SUBMIT_SUBMITTED", result)
    return result


def _block_submit(plan: dict[str, Any], mode: str, blocks: list[str], message: str) -> dict[str, Any]:
    result = {
        "plan_id": plan.get("plan_id"),
        "mode": mode,
        "verdict": "BLOCK",
        "status": "SUBMIT_BLOCKED",
        "blocks": blocks,
        "message": message,
    }
    plan["submit"] = result
    plan["status"] = "SUBMIT_BLOCKED"
    save_plan(plan)
    append_audit("SUBMIT_BLOCKED", result)
    return result


# Backward-compatible name for old tests/imports.
def safe_submit_blocking_mvp(config: dict[str, Any], plan_id: str, phrase: str, mode: str, approval_token: str | None = None) -> dict[str, Any]:
    return submit_order(config, plan_id, phrase, mode, approval_token)
