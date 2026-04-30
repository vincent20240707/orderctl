from __future__ import annotations

from typing import Any

from safe_ib_order_gateway.services.health_service import make_client
from safe_ib_order_gateway.services.storage import append_audit


def account_summary(config: dict[str, Any], mode: str, client_id: int | None = None) -> dict[str, Any]:
    client = make_client(config, "account", client_id)
    result = client.account_summary()
    append_audit("ACCOUNT_SUMMARY", result)
    return result


def positions_list(config: dict[str, Any], mode: str, client_id: int | None = None, compact: bool = False) -> dict[str, Any]:
    client = make_client(config, "positions", client_id)
    result = client.positions_list()
    if compact:
        result["positions"] = [
            {
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "quantity": p.get("quantity"),
                "avg_cost": p.get("avg_cost"),
                "currency": p.get("currency"),
            }
            for p in result.get("positions", []) or []
        ]
        result["compact"] = True
    append_audit("POSITIONS_LIST", result)
    return result


def orders_list(config: dict[str, Any], mode: str, client_id: int | None = None, compact: bool = False) -> dict[str, Any]:
    client = make_client(config, "orders", client_id)
    result = client.orders_list()
    if compact:
        result["open_orders"] = [
            {
                "symbol": o.get("symbol"),
                "order_id": o.get("order_id"),
                "side": o.get("side"),
                "quantity": o.get("quantity"),
                "order_type": o.get("order_type"),
                "limit_price": o.get("limit_price"),
                "stop_price": o.get("stop_price"),
                "status": o.get("status"),
                "outside_rth": o.get("outside_rth"),
            }
            for o in result.get("open_orders", []) or []
        ]
        result["compact"] = True
    append_audit("ORDERS_LIST", result)
    return result


def portfolio_snapshot(
    config: dict[str, Any],
    mode: str,
    client_id: int | None = None,
    with_quotes: bool = False,
    with_pnl: bool = False,
    compact: bool = False,
) -> dict[str, Any]:
    client = make_client(config, "portfolio", client_id)
    result = client.portfolio_snapshot(with_quotes=with_quotes, with_pnl=with_pnl, compact=compact)
    append_audit("PORTFOLIO_SNAPSHOT", result)
    return result
