from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .enums import IntentType, OrderRole, OrderType, PositionSide, Side


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    intent_type: IntentType
    order_role: OrderRole
    side: Side
    quantity: int
    order_type: OrderType
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    trail_amount: Optional[float] = None
    outside_rth: bool = False
    time_in_force: str = "DAY"
    reason: str = ""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "OrderIntent":
        try:
            return OrderIntent(
                symbol=str(data["symbol"]).upper().strip(),
                intent_type=IntentType(str(data["intent_type"]).upper()),
                order_role=OrderRole(str(data["order_role"]).upper()),
                side=Side(str(data["side"]).upper()),
                quantity=int(data["quantity"]),
                order_type=OrderType(str(data["order_type"]).upper()),
                limit_price=_optional_float(data.get("limit_price")),
                stop_price=_optional_float(data.get("stop_price")),
                trail_amount=_optional_float(data.get("trail_amount")),
                outside_rth=bool(data.get("outside_rth", False)),
                time_in_force=str(data.get("time_in_force", "DAY")).upper(),
                reason=str(data.get("reason", "")).strip(),
            )
        except KeyError as exc:
            raise ValueError(f"Missing required OrderIntent field: {exc.args[0]}") from exc

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("intent_type", "order_role", "side", "order_type"):
            data[key] = data[key].value
        return data


@dataclass
class PositionSnapshot:
    side: PositionSide = PositionSide.UNKNOWN
    quantity: int = 0
    avg_cost: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {"side": self.side.value, "quantity": self.quantity, "avg_cost": self.avg_cost}


@dataclass
class MarketSnapshot:
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    close: Optional[float] = None
    market_data_status: str = "UNKNOWN"
    message: str = ""
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AccountSnapshot:
    account: str = ""
    available_funds: Optional[float] = None
    buying_power: Optional[float] = None
    excess_liquidity: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Snapshot:
    symbol: str
    mode: str
    account: str
    position: PositionSnapshot
    market: MarketSnapshot
    account_summary: AccountSnapshot
    open_orders: list[dict[str, Any]]
    status: str = "PASS"
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "mode": self.mode,
            "account": self.account,
            "position": self.position.to_dict(),
            "market": self.market.to_dict(),
            "account_summary": self.account_summary.to_dict(),
            "open_orders": self.open_orders,
            "status": self.status,
            "timestamp": self.timestamp,
        }


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)
