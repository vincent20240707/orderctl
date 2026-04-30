from pathlib import Path

from safe_ib_order_gateway.config import LATEST_SNAPSHOT_FILE, load_config
from safe_ib_order_gateway.services.hard_gate_service import run_hard_check
from safe_ib_order_gateway.services.plan_service import create_plan
from safe_ib_order_gateway.services.storage import read_json, save_latest_snapshot

ROOT = Path(__file__).resolve().parents[1]


def setup_snapshot():
    snap = read_json(ROOT / "examples" / "mock_latest_snapshot.json")
    save_latest_snapshot(snap)


def test_cover_20_passes_hard_gate():
    setup_snapshot()
    cfg = load_config("paper", str(ROOT / "config" / "paper.yaml"))
    result = create_plan(str(ROOT / "examples" / "wdc_cover_20.json"), "paper")
    check = run_hard_check(cfg, result["plan_id"])
    assert check["verdict"] == "PASS"
    assert check["position_after"] == {"side": "SHORT", "quantity": 40}


def test_reverse_block(tmp_path):
    setup_snapshot()
    intent = tmp_path / "reverse.json"
    intent.write_text(
        '{"symbol":"WDC","intent_type":"CLOSE_SHORT","order_role":"SCALE_OUT","side":"BUY","quantity":100,"order_type":"LIMIT","limit_price":386.0,"reason":"test"}',
        encoding="utf-8",
    )
    cfg = load_config("paper", str(ROOT / "config" / "paper.yaml"))
    result = create_plan(str(intent), "paper")
    check = run_hard_check(cfg, result["plan_id"])
    assert check["verdict"] == "BLOCK"
    assert "REVERSE_POSITION_FORBIDDEN" in check["blocks"]
