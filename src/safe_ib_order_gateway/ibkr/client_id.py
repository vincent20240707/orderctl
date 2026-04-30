from __future__ import annotations

from typing import Any

COMMAND_OFFSETS = {
    "health": 1,
    "snapshot": 2,
    "portfolio": 3,
    "positions": 4,
    "orders": 5,
    "account": 6,
    "preview": 10,
    "submit": 13,
    "cancel": 14,
    "replace": 15,
    "reconcile": 16,
}


def resolve_client_id(config: dict[str, Any], command: str, override: int | None = None) -> int:
    """Backward-compatible single-clientId resolver.

    New code should prefer build_client_id_candidates(), but some tests/imports
    still call this function.
    """
    return build_client_id_candidates(config, command, override)[0]


def build_client_id_candidates(config: dict[str, Any], command: str, override: int | None = None) -> list[int]:
    """Return connect-time clientId candidates for this short-lived CLI process.

    This is not a global pool and does not maintain state when orderctl is not
    running. Each command chooses a deterministic starting point, then tries the
    next ids in the configured candidate range if IBKR returns error 326.
    """
    if override is not None:
        return [int(override)]

    ib = config.get("ibkr", {}) or {}
    if ib.get("client_id") is not None:
        return [int(ib["client_id"])]

    base = int(ib.get("client_id_base", 100) or 100)
    offset = COMMAND_OFFSETS.get(command, 19)
    start = base + offset

    candidate_count = int(ib.get("client_id_candidate_count", ib.get("client_id_pool_size", 20)) or 20)
    retry_count = int(ib.get("client_id_retry_count", 5) or 5)
    attempts = max(1, min(candidate_count, retry_count))
    return [start + i for i in range(attempts)]


def client_id_strategy(config: dict[str, Any]) -> str:
    ib = config.get("ibkr", {}) or {}
    return str(ib.get("client_id_strategy", "connect_time_fallback"))
