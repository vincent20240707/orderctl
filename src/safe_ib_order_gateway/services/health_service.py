from __future__ import annotations

from typing import Any

from safe_ib_order_gateway.ibkr.client import IBKRClient
from safe_ib_order_gateway.ibkr.client_id import build_client_id_candidates, client_id_strategy


def make_client(config: dict[str, Any], command: str = "health", client_id_override: int | None = None) -> IBKRClient:
    ib_conf = config.get("ibkr", {}) or {}
    candidates = build_client_id_candidates(config, command, client_id_override)
    return IBKRClient(
        host=ib_conf.get("host", "127.0.0.1"),
        port=int(ib_conf.get("port", 4001)),
        client_id=candidates[0],
        account=str(ib_conf.get("account", "")),
        mode=str(config.get("mode", "paper")),
        market_data_config=config.get("market_data", {}) or {},
        client_id_candidates=candidates,
        client_id_strategy=client_id_strategy(config),
    )


def health(config: dict[str, Any], client_id_override: int | None = None) -> dict[str, Any]:
    client = make_client(config, "health", client_id_override)
    result = client.health()
    result["live_trading_enabled"] = bool(config.get("live_trading", {}).get("enabled", False))
    return result
