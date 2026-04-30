from __future__ import annotations

from safe_ib_order_gateway.services.health_service import make_client
from safe_ib_order_gateway.services.storage import append_audit, save_latest_snapshot


def snapshot(config: dict, symbol: str, fresh: bool = True, client_id: int | None = None) -> dict:
    client = make_client(config, "snapshot", client_id)
    data = client.snapshot(symbol)
    save_latest_snapshot(data)
    append_audit("SNAPSHOT", data)
    return data
