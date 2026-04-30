from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from safe_ib_order_gateway.config import VAR_DIR
from safe_ib_order_gateway.services.health_service import make_client
from safe_ib_order_gateway.services.storage import append_audit, read_json, write_json

CANCEL_TICKETS_DIR = VAR_DIR / "cancel_tickets"


def _ticket_id(order_id: int | None = None, symbol: str | None = None) -> str:
    if order_id is not None:
        return f"CXL-ORDER-{order_id}"
    if symbol:
        return f"CXL-SYMBOL-{symbol.upper()}"
    raise ValueError("order_id or symbol is required")


def _ticket_path(cancel_id: str) -> Path:
    return CANCEL_TICKETS_DIR / f"{cancel_id}.json"


def cancel_ticket(config: dict[str, Any], mode: str, order_id: int | None = None, symbol: str | None = None, client_id: int | None = None) -> dict[str, Any]:
    if order_id is None and not symbol:
        return {"status": "ERROR", "error": "ORDER_ID_OR_SYMBOL_REQUIRED"}
    client = make_client(config, "cancel", client_id)
    orders = client.find_open_orders(order_id=order_id, symbol=symbol)
    if not orders:
        return {"status": "ERROR", "error": "NO_MATCHING_OPEN_ORDERS", "order_id": order_id, "symbol": symbol}
    cancel_id = _ticket_id(order_id=order_id, symbol=symbol)
    if order_id is not None:
        phrase = f"CANCEL ORDER {order_id}"
    else:
        phrase = f"CANCEL ALL {symbol.upper()} ORDERS"
    ticket = {
        "cancel_id": cancel_id,
        "mode": mode,
        "order_id": order_id,
        "symbol": symbol.upper() if symbol else None,
        "orders": orders,
        "confirmation_phrase": phrase,
        "status": "CANCEL_TICKET_READY",
    }
    write_json(_ticket_path(cancel_id), ticket)
    append_audit("CANCEL_TICKET", ticket)
    return ticket


def cancel_submit(config: dict[str, Any], mode: str, phrase: str, order_id: int | None = None, symbol: str | None = None, client_id: int | None = None) -> dict[str, Any]:
    cancel_id = _ticket_id(order_id=order_id, symbol=symbol)
    path = _ticket_path(cancel_id)
    if not path.exists():
        return {"status": "ERROR", "error": "CANCEL_TICKET_NOT_FOUND", "cancel_id": cancel_id}
    ticket = read_json(path)
    expected = ticket.get("confirmation_phrase")
    if phrase != expected:
        return {"status": "ERROR", "error": "CONFIRMATION_PHRASE_MISMATCH", "expected": expected}
    client = make_client(config, "cancel", client_id)
    result = client.cancel_order(order_id=order_id, symbol=symbol)
    result["cancel_id"] = cancel_id
    append_audit("CANCEL_SUBMIT", result)
    return result
