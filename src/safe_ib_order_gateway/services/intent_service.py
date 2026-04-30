from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safe_ib_order_gateway.domain.enums import IntentType, OrderRole, OrderType, Side
from safe_ib_order_gateway.domain.models import OrderIntent


def intent_schema() -> dict[str, Any]:
    return {
        "status": "PASS",
        "required_fields": ["symbol", "intent_type", "order_role", "side", "quantity", "order_type", "reason"],
        "optional_fields": ["limit_price", "stop_price", "trail_amount", "outside_rth", "time_in_force"],
        "allowed_values": {
            "intent_type": [x.value for x in IntentType],
            "order_role": [x.value for x in OrderRole],
            "side": [x.value for x in Side],
            "order_type": [x.value for x in OrderType],
        },
        "notes": [
            "OPEN_LONG/CLOSE_LONG/OPEN_SHORT/CLOSE_SHORT belong to intent_type, not order_role.",
            "ENTRY/STOP_LOSS/TAKE_PROFIT/SCALE_IN/SCALE_OUT/BACKSTOP/HEDGE/EMERGENCY_EXIT belong to order_role.",
            "submit never accepts symbol/quantity/price directly; it submits a saved plan_id only.",
        ],
    }


def intent_examples() -> dict[str, Any]:
    return {
        "status": "PASS",
        "examples": {
            "open_long_limit_entry": {
                "symbol": "WDC",
                "intent_type": "OPEN_LONG",
                "order_role": "ENTRY",
                "side": "BUY",
                "quantity": 20,
                "order_type": "LIMIT",
                "limit_price": 390.0,
                "outside_rth": False,
                "time_in_force": "DAY",
                "reason": "paper流程测试：限价做多开仓",
            },
            "close_long_take_profit": {
                "symbol": "WDC",
                "intent_type": "CLOSE_LONG",
                "order_role": "TAKE_PROFIT",
                "side": "SELL",
                "quantity": 20,
                "order_type": "LIMIT",
                "limit_price": 415.0,
                "outside_rth": False,
                "time_in_force": "DAY",
                "reason": "多头止盈卖出",
            },
            "open_short_limit_entry": {
                "symbol": "WDC",
                "intent_type": "OPEN_SHORT",
                "order_role": "ENTRY",
                "side": "SELL",
                "quantity": 10,
                "order_type": "LIMIT",
                "limit_price": 420.0,
                "outside_rth": False,
                "time_in_force": "DAY",
                "reason": "paper流程测试：限价做空开仓",
            },
            "close_short_take_profit": {
                "symbol": "WDC",
                "intent_type": "CLOSE_SHORT",
                "order_role": "TAKE_PROFIT",
                "side": "BUY",
                "quantity": 10,
                "order_type": "LIMIT",
                "limit_price": 390.0,
                "outside_rth": False,
                "time_in_force": "DAY",
                "reason": "空头止盈回补",
            },
        },
    }


def validate_intent(intent_file: str) -> dict[str, Any]:
    path = Path(intent_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "ERROR", "error": "INVALID_JSON", "message": str(exc)}
    try:
        intent = OrderIntent.from_dict(data)
    except Exception as exc:
        message = str(exc)
        result: dict[str, Any] = {"status": "ERROR", "error": "INVALID_ORDER_INTENT", "message": message}
        # Give direct hints for the most common OpenClaw mistake.
        if "OrderRole" in message or "valid OrderRole" in message or "is not a valid OrderRole" in message:
            result.update(
                {
                    "field": "order_role",
                    "allowed_values": [x.value for x in OrderRole],
                    "hint": "OPEN_LONG/CLOSE_LONG/OPEN_SHORT/CLOSE_SHORT belong to intent_type, not order_role.",
                }
            )
        if "IntentType" in message or "valid IntentType" in message:
            result.update({"field": "intent_type", "allowed_values": [x.value for x in IntentType]})
        return result
    return {"status": "PASS", "intent": intent.to_dict(), "message": "OrderIntent is valid."}
