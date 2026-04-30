from pathlib import Path

from safe_ib_order_gateway.config import load_config
from safe_ib_order_gateway.services.hard_gate_service import run_hard_check
from safe_ib_order_gateway.services.plan_service import create_plan
from safe_ib_order_gateway.services.preview_service import local_preview
from safe_ib_order_gateway.services.review_service import attach_review
from safe_ib_order_gateway.services.storage import read_json, save_latest_snapshot
from safe_ib_order_gateway.services.submit_service import submit_order
from safe_ib_order_gateway.services.ticket_service import generate_ticket

ROOT = Path(__file__).resolve().parents[1]


def test_ticket_and_submit_blocks_on_bad_phrase_without_touching_ibkr():
    save_latest_snapshot(read_json(ROOT / "examples" / "mock_latest_snapshot.json"))
    cfg = load_config("paper", str(ROOT / "config" / "paper.yaml"))
    plan = create_plan(str(ROOT / "examples" / "wdc_cover_20.json"), "paper")
    plan_id = plan["plan_id"]
    run_hard_check(cfg, plan_id)
    attach_review(plan_id, str(ROOT / "examples" / "ai_review_warn.json"))
    local_preview(plan_id)
    ticket = generate_ticket(plan_id)
    result = submit_order(cfg, plan_id, ticket["confirmation_phrase"] + " BAD", "paper")
    assert result["verdict"] == "BLOCK"
    assert "CONFIRMATION_PHRASE_MISMATCH" in result["blocks"]
