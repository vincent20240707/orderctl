from __future__ import annotations

import math
from contextlib import contextmanager
from typing import Any, Iterator

from safe_ib_order_gateway.domain.enums import OrderType, PositionSide
from safe_ib_order_gateway.domain.models import (
    AccountSnapshot,
    MarketSnapshot,
    PositionSnapshot,
    Snapshot,
)


def _clean_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


class IBKRUnavailableError(RuntimeError):
    pass


class ClientIdInUseError(RuntimeError):
    pass


class IBKRClient:
    """Thin ib_async wrapper used by orderctl.

    It reads facts from IBKR, creates standard stock contracts/orders, runs What-If,
    submits, cancels, and modifies simple stock orders. Complex reasoning belongs
    to OpenClaw; this class should stay deterministic and boring.
    """

    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        account: str,
        mode: str,
        market_data_config: dict[str, Any] | None = None,
        client_id_candidates: list[int] | None = None,
        client_id_strategy: str = "connect_time_fallback",
    ):
        self.host = host
        self.port = int(port)
        self.client_id = int(client_id)
        self.account = account
        self.mode = mode
        self.market_data_config = market_data_config or {}
        self.ib = None
        self.client_id_candidates = [int(x) for x in (client_id_candidates or [client_id])]
        self.client_id_strategy = client_id_strategy
        self.connected_client_id = self.client_id_candidates[0]
        self.client_id_attempts: list[int] = []
        self.warnings: list[dict[str, Any]] = []

    def _import(self):
        try:
            from ib_async import IB, Stock  # type: ignore
            from ib_async import LimitOrder, MarketOrder, Order, StopLimitOrder, StopOrder  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise IBKRUnavailableError("ib_async is not installed or could not be imported") from exc
        return IB, Stock, Order, MarketOrder, LimitOrder, StopOrder, StopLimitOrder

    @contextmanager
    def connected(self) -> Iterator[Any]:
        IB, *_ = self._import()
        last_exc: Exception | None = None
        self.client_id_attempts = []
        self.warnings = []
        for cid in self.client_id_candidates:
            ib = IB()
            self.client_id_attempts.append(int(cid))
            try:
                ib.connect(self.host, self.port, clientId=int(cid), timeout=8)
                self.connected_client_id = int(cid)
                self.ib = ib
                try:
                    yield ib
                finally:
                    try:
                        ib.disconnect()
                    except Exception:
                        pass
                    self.ib = None
                return
            except Exception as exc:  # pragma: no cover - needs live IBKR
                last_exc = exc
                try:
                    if ib.isConnected():
                        ib.disconnect()
                except Exception:
                    pass
                if self._is_client_id_in_use(exc):
                    self._warn(
                        "CLIENT_ID_IN_USE_RETRY",
                        f"IBKR clientId {cid} is already in use; trying next candidate.",
                        "Non-fatal if another candidate connects successfully.",
                    )
                    continue
                raise
        raise ClientIdInUseError(
            f"IBKR clientId appears to be in use. Tried: {self.client_id_attempts}. Last error: {last_exc}"
        )

    def _is_client_id_in_use(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return "326" in msg or "client id" in msg or "clientid" in msg

    def _warn(self, code: str, message: str, impact: str = "") -> None:
        self.warnings.append({"code": code, "message": message, "impact": impact})

    def _connection_meta(self) -> dict[str, Any]:
        return {
            "client_id_strategy": self.client_id_strategy,
            "client_id_used": self.connected_client_id,
            "client_id_attempts": list(self.client_id_attempts),
            "warnings": list(self.warnings),
        }

    def _merge_meta(self, data: dict[str, Any]) -> dict[str, Any]:
        meta = self._connection_meta()
        existing = data.get("warnings") or []
        if isinstance(existing, list):
            meta["warnings"] = existing + meta["warnings"]
        data.update(meta)
        return data

    def health(self) -> dict[str, Any]:
        with self.connected() as ib:
            accounts = list(ib.managedAccounts())
            return self._merge_meta({
                "ok": True,
                "mode": self.mode,
                "ib_connected": bool(ib.isConnected()),
                "host": self.host,
                "port": self.port,
                "client_id_requested": self.client_id,
                "configured_account": self.account,
                "managed_accounts": accounts,
                "account_found": self.account in accounts if self.account else None,
                "status": "PASS" if (not self.account or self.account in accounts) else "ACCOUNT_MISMATCH",
            })

    def snapshot(self, symbol: str) -> dict[str, Any]:
        symbol = symbol.upper().strip()
        with self.connected() as ib:
            contract = self._stock_contract(ib, symbol)
            position = self._read_position(ib, symbol)
            open_orders = self._read_open_orders(ib, symbol)
            account_summary = self._read_account_summary(ib)
            market = self._read_market(ib, contract)

            status = "PASS"
            warnings: list[str] = []
            if market.market_data_status in {"MISSING", "ERROR", "UNKNOWN"}:
                status = "WARN"
                warnings.append({
                    "code": "MARKET_DATA_MISSING",
                    "message": "bid/ask/last 缺失，可能未开通实时行情或当前无可用行情。",
                    "suggestion": "明确限价单可继续流程，但不能依赖实时价格判断；如需实时价格，建议开通 IBKR 实时行情。"
                })
            elif market.market_data_status == "DELAYED":
                status = "WARN"
                warnings.append({
                    "code": "MARKET_DATA_DELAYED",
                    "message": "当前行情可能是 delayed data，不能当作实时行情使用。",
                    "suggestion": "如需实时价格，请检查 IBKR 实时行情订阅。"
                })

            snap = Snapshot(
                symbol=symbol,
                mode=self.mode,
                account=self.account,
                position=position,
                market=market,
                account_summary=account_summary,
                open_orders=open_orders,
                status=status,
            ).to_dict()
            snap["warnings"] = warnings
            return self._merge_meta(snap)

    def what_if(self, plan: dict[str, Any]) -> dict[str, Any]:
        intent = plan["intent"]
        with self.connected() as ib:
            contract = self._stock_contract(ib, intent["symbol"])
            order = self._build_order(intent, what_if=True)
            trade = ib.placeOrder(contract, order)
            ib.sleep(3)
            order_state = getattr(trade, "orderState", None)
            order_status = getattr(trade, "orderStatus", None)
            result = {
                "plan_id": plan["plan_id"],
                "preview_type": "IBKR_WHAT_IF",
                "symbol": intent["symbol"],
                "side": intent["side"],
                "semantic_action": intent["intent_type"],
                "order_role": intent["order_role"],
                "quantity": intent["quantity"],
                "order_type": intent["order_type"],
                "limit_price": intent.get("limit_price"),
                "stop_price": intent.get("stop_price"),
                "ib_order_id": getattr(order, "orderId", None),
                "status": "PREVIEW_READY",
                "order_status": getattr(order_status, "status", None),
                "what_if": self._order_state_to_dict(order_state),
                "warnings": [],
            }
            warning_text = result["what_if"].get("warning_text")
            if warning_text:
                result["warnings"].append({"code": "IBKR_WARNING_TEXT", "message": str(warning_text)})
            return self._merge_meta(result)

    def place_order(self, plan: dict[str, Any]) -> dict[str, Any]:
        intent = plan["intent"]
        with self.connected() as ib:
            contract = self._stock_contract(ib, intent["symbol"])
            order = self._build_order(intent, what_if=False)
            trade = ib.placeOrder(contract, order)
            ib.sleep(2)
            return self._trade_submit_result(plan["plan_id"], intent, trade, order)

    def cancel_order(self, order_id: int | None = None, symbol: str | None = None) -> dict[str, Any]:
        with self.connected() as ib:
            matches = self._find_open_trades(ib, order_id=order_id, symbol=symbol)
            if not matches:
                return {"status": "ERROR", "error": "ORDER_NOT_FOUND_OR_NOT_OPEN", "order_id": order_id, "symbol": symbol}
            cancelled = []
            for trade in matches:
                order = getattr(trade, "order", None)
                if not order:
                    continue
                ib.cancelOrder(order)
                ib.sleep(1)
                status = getattr(getattr(trade, "orderStatus", None), "status", None)
                cancelled.append(self._trade_order_summary(trade) | {"post_cancel_status": status})
            return self._merge_meta({
                "status": "CANCEL_REQUESTED",
                "mode": self.mode,
                "requested_order_id": order_id,
                "requested_symbol": symbol,
                "cancelled": cancelled,
            })

    def replace_limit_price(self, order_id: int, new_limit_price: float) -> dict[str, Any]:
        with self.connected() as ib:
            matches = self._find_open_trades(ib, order_id=order_id, symbol=None)
            if not matches:
                return {"status": "ERROR", "error": "ORDER_NOT_FOUND_OR_NOT_OPEN", "order_id": order_id}
            trade = matches[0]
            contract = getattr(trade, "contract", None)
            order = getattr(trade, "order", None)
            if not order or not contract:
                return {"status": "ERROR", "error": "MISSING_TRADE_ORDER_OR_CONTRACT", "order_id": order_id}
            if str(getattr(order, "orderType", "")).upper() != "LMT":
                return {"status": "ERROR", "error": "ONLY_LIMIT_ORDER_REPLACE_SUPPORTED", "order_id": order_id}
            old_price = _clean_float(getattr(order, "lmtPrice", None))
            order.lmtPrice = float(new_limit_price)
            trade2 = ib.placeOrder(contract, order)
            ib.sleep(2)
            return self._merge_meta({
                "status": "REPLACE_SUBMITTED",
                "mode": self.mode,
                "order_id": order_id,
                "symbol": getattr(contract, "symbol", None),
                "old_limit_price": old_price,
                "new_limit_price": float(new_limit_price),
                "order_status": getattr(getattr(trade2, "orderStatus", None), "status", None),
                "order": self._trade_order_summary(trade2),
            })

    def account_summary(self) -> dict[str, Any]:
        """Return account-level summary tags for the configured account."""
        with self.connected() as ib:
            summary = self._read_account_summary_full(ib)
            return self._merge_meta({
                "status": "PASS",
                "mode": self.mode,
                "account": self.account,
                "host": self.host,
                "port": self.port,
                "account_summary": summary,
            })

    def positions_list(self) -> dict[str, Any]:
        """Return all positions for the configured account."""
        with self.connected() as ib:
            positions = self._read_all_positions(ib)
            return self._merge_meta({
                "status": "PASS",
                "mode": self.mode,
                "account": self.account,
                "positions": positions,
                "count": len(positions),
            })

    def orders_list(self) -> dict[str, Any]:
        """Return all currently open orders visible to this API client/session."""
        with self.connected() as ib:
            open_orders = self._read_all_open_orders(ib)
            return self._merge_meta({
                "status": "PASS",
                "mode": self.mode,
                "account": self.account,
                "open_orders": open_orders,
                "count": len(open_orders),
            })

    def portfolio_snapshot(self, with_quotes: bool = False, with_pnl: bool = False, compact: bool = False) -> dict[str, Any]:
        """Return account summary + all positions + all open orders in one call.

        Phase 2.2 adds optional quotes/PnL so OpenClaw can inspect account
        status with one compact command instead of many per-symbol snapshots.
        Missing market data is non-fatal and is returned as structured warnings.
        """
        with self.connected() as ib:
            account_summary = self._read_account_summary_full(ib)
            positions = self._read_all_positions(ib)
            open_orders = self._read_all_open_orders(ib)
            if with_quotes or with_pnl:
                positions = self._enrich_positions_with_quotes(ib, positions, with_pnl=with_pnl)
            risk_flags = self._portfolio_issues(positions, open_orders)
            warnings: list[dict[str, Any]] = []
            for p in positions:
                if p.get("market_data_status") in {"MISSING", "ERROR", "UNKNOWN"}:
                    warnings.append({
                        "code": "POSITION_MARKET_DATA_MISSING",
                        "symbol": p.get("symbol"),
                        "message": f"No bid/ask/last available for {p.get('symbol')}; PnL may be null.",
                        "suggestion": "Check IBKR real-time market data subscription if real-time quotes are needed."
                    })
                elif p.get("market_data_status") == "DELAYED":
                    warnings.append({
                        "code": "POSITION_MARKET_DATA_DELAYED",
                        "symbol": p.get("symbol"),
                        "message": f"Delayed quote used for {p.get('symbol')}; do not treat it as real-time.",
                    })

            pnl_values = [p.get("unrealized_pnl") for p in positions if p.get("unrealized_pnl") is not None]
            pnl_summary = {
                "total_unrealized_pnl": round(sum(float(x) for x in pnl_values), 2) if pnl_values else None,
                "positions_with_pnl": len(pnl_values),
                "positions_without_pnl": len(positions) - len(pnl_values),
            }
            status = "WARN" if risk_flags or warnings else "PASS"
            result = {
                "status": status,
                "mode": self.mode,
                "account": self.account,
                "host": self.host,
                "port": self.port,
                "account_summary": account_summary,
                "positions": positions,
                "open_orders": open_orders,
                "pnl_summary": pnl_summary,
                "risk_flags": risk_flags,
                "issues": risk_flags,  # backward-compatible alias
                "warnings": warnings,
                "counts": {
                    "positions": len(positions),
                    "open_orders": len(open_orders),
                    "risk_flags": len(risk_flags),
                    "warnings": len(warnings),
                },
            }
            if compact:
                result = self._compact_portfolio_result(result)
            return self._merge_meta(result)

    def _enrich_positions_with_quotes(self, ib: Any, positions: list[dict[str, Any]], with_pnl: bool) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for pos in positions:
            item = dict(pos)
            symbol = str(item.get("symbol") or "").upper()
            if not symbol:
                enriched.append(item)
                continue
            try:
                contract = self._stock_contract(ib, symbol)
                market = self._read_market(ib, contract).to_dict()
            except Exception as exc:
                market = {"market_data_status": "ERROR", "message": str(exc)}
            item["quote"] = market
            item["bid"] = market.get("bid")
            item["ask"] = market.get("ask")
            item["last"] = market.get("last")
            item["close"] = market.get("close")
            item["market_data_status"] = market.get("market_data_status", "UNKNOWN")
            if with_pnl:
                price = self._usable_market_price(market)
                qty = float(item.get("quantity") or 0)
                avg_cost = _clean_float(item.get("avg_cost"))
                if price is not None and avg_cost is not None and qty:
                    if str(item.get("side") or "").upper() == "SHORT":
                        item["market_value"] = round(-price * qty, 2)
                        item["unrealized_pnl"] = round((avg_cost - price) * qty, 2)
                    else:
                        item["market_value"] = round(price * qty, 2)
                        item["unrealized_pnl"] = round((price - avg_cost) * qty, 2)
                    item["pnl_price_used"] = price
                else:
                    item["market_value"] = None
                    item["unrealized_pnl"] = None
                    item["pnl_price_used"] = None
            enriched.append(item)
        return enriched

    def _usable_market_price(self, market: dict[str, Any]) -> float | None:
        last = _clean_float(market.get("last"))
        if last is not None:
            return last
        bid = _clean_float(market.get("bid"))
        ask = _clean_float(market.get("ask"))
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        close = _clean_float(market.get("close"))
        return close

    def _compact_portfolio_result(self, result: dict[str, Any]) -> dict[str, Any]:
        summary_tags = (result.get("account_summary") or {}).get("tags", {})
        compact_summary = {
            key: summary_tags.get(key)
            for key in ("NetLiquidation", "AvailableFunds", "BuyingPower", "ExcessLiquidity", "GrossPositionValue")
            if key in summary_tags
        }
        positions = []
        for p in result.get("positions", []) or []:
            positions.append({
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "quantity": p.get("quantity"),
                "avg_cost": p.get("avg_cost"),
                "last": p.get("last"),
                "market_data_status": p.get("market_data_status"),
                "market_value": p.get("market_value"),
                "unrealized_pnl": p.get("unrealized_pnl"),
            })
        open_orders = []
        for o in result.get("open_orders", []) or []:
            open_orders.append({
                "symbol": o.get("symbol"),
                "order_id": o.get("order_id"),
                "side": o.get("side"),
                "quantity": o.get("quantity"),
                "order_type": o.get("order_type"),
                "limit_price": o.get("limit_price"),
                "stop_price": o.get("stop_price"),
                "status": o.get("status"),
                "outside_rth": o.get("outside_rth"),
            })
        return {
            "status": result.get("status"),
            "mode": result.get("mode"),
            "account": result.get("account"),
            "account_summary": compact_summary,
            "positions": positions,
            "open_orders": open_orders,
            "pnl_summary": result.get("pnl_summary"),
            "risk_flags": result.get("risk_flags", []),
            "warnings": result.get("warnings", []),
            "counts": result.get("counts"),
        }

    def find_open_orders(self, order_id: int | None = None, symbol: str | None = None) -> list[dict[str, Any]]:
        with self.connected() as ib:
            return [self._trade_order_summary(t) for t in self._find_open_trades(ib, order_id=order_id, symbol=symbol)]

    def _find_open_trades(self, ib: Any, order_id: int | None = None, symbol: str | None = None) -> list[Any]:
        try:
            trades = ib.openTrades()
        except Exception:
            trades = []
        out = []
        for trade in trades:
            contract = getattr(trade, "contract", None)
            order = getattr(trade, "order", None)
            status = getattr(trade, "orderStatus", None)
            if not contract or not order:
                continue
            if order_id is not None and int(getattr(order, "orderId", -1)) != int(order_id):
                continue
            if symbol is not None and getattr(contract, "symbol", "").upper() != symbol.upper():
                continue
            if getattr(status, "status", "") in {"Filled", "Cancelled", "Inactive"}:
                continue
            out.append(trade)
        return out

    def _trade_order_summary(self, trade: Any) -> dict[str, Any]:
        contract = getattr(trade, "contract", None)
        order = getattr(trade, "order", None)
        status = getattr(trade, "orderStatus", None)
        return {
            "symbol": getattr(contract, "symbol", None),
            "order_id": getattr(order, "orderId", None),
            "perm_id": getattr(order, "permId", None),
            "side": getattr(order, "action", None),
            "quantity": _clean_float(getattr(order, "totalQuantity", None)),
            "order_type": getattr(order, "orderType", None),
            "limit_price": _clean_float(getattr(order, "lmtPrice", None)),
            "stop_price": _clean_float(getattr(order, "auxPrice", None)),
            "outside_rth": getattr(order, "outsideRth", None),
            "tif": getattr(order, "tif", None),
            "status": getattr(status, "status", None),
            "filled": _clean_float(getattr(status, "filled", None)),
            "remaining": _clean_float(getattr(status, "remaining", None)),
        }

    def _trade_submit_result(self, plan_id: str, intent: dict[str, Any], trade: Any, order: Any) -> dict[str, Any]:
        order_status = getattr(trade, "orderStatus", None)
        order_obj = getattr(trade, "order", order)
        fills = []
        for fill in getattr(trade, "fills", []) or []:
            fills.append(
                {
                    "exec_id": _clean_str(getattr(getattr(fill, "execution", None), "execId", None)),
                    "time": str(getattr(getattr(fill, "execution", None), "time", "")),
                    "shares": _clean_float(getattr(getattr(fill, "execution", None), "shares", None)),
                    "price": _clean_float(getattr(getattr(fill, "execution", None), "price", None)),
                }
            )
        result = {
            "plan_id": plan_id,
            "mode": self.mode,
            "symbol": intent["symbol"],
            "side": intent["side"],
            "quantity": intent["quantity"],
            "order_type": intent["order_type"],
            "status": "SUBMITTED",
            "ib_order": {
                "order_id": getattr(order_obj, "orderId", None),
                "perm_id": getattr(order_obj, "permId", None),
                "client_id": getattr(order_obj, "clientId", None),
                "account": getattr(order_obj, "account", None),
                "action": getattr(order_obj, "action", None),
                "total_quantity": _clean_float(getattr(order_obj, "totalQuantity", None)),
                "order_type": getattr(order_obj, "orderType", None),
                "lmt_price": _clean_float(getattr(order_obj, "lmtPrice", None)),
                "aux_price": _clean_float(getattr(order_obj, "auxPrice", None)),
                "tif": getattr(order_obj, "tif", None),
                "outside_rth": getattr(order_obj, "outsideRth", None),
                "transmit": getattr(order_obj, "transmit", None),
            },
            "order_status": {
                "status": getattr(order_status, "status", None),
                "filled": _clean_float(getattr(order_status, "filled", None)),
                "remaining": _clean_float(getattr(order_status, "remaining", None)),
                "avg_fill_price": _clean_float(getattr(order_status, "avgFillPrice", None)),
            },
            "fills": fills,
        }
        return self._merge_meta(result)

    def _stock_contract(self, ib: Any, symbol: str) -> Any:
        _, Stock, *_ = self._import()
        contract = Stock(symbol.upper().strip(), "SMART", "USD")
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            raise RuntimeError(f"IBKR could not qualify stock contract: {symbol}")
        return qualified[0]

    def _build_order(self, intent: dict[str, Any], what_if: bool = False) -> Any:
        _, _, Order, MarketOrder, LimitOrder, StopOrder, StopLimitOrder = self._import()
        action = str(intent["side"]).upper()
        qty = int(intent["quantity"])
        order_type = str(intent["order_type"]).upper()
        tif = str(intent.get("time_in_force") or "DAY").upper()
        outside_rth = bool(intent.get("outside_rth", False))

        if order_type == OrderType.LIMIT.value:
            price = intent.get("limit_price")
            if price is None:
                raise ValueError("LIMIT order requires limit_price")
            order = LimitOrder(action, qty, float(price))
        elif order_type == OrderType.STOP.value:
            stop_price = intent.get("stop_price")
            if stop_price is None:
                raise ValueError("STOP order requires stop_price")
            order = StopOrder(action, qty, float(stop_price))
        elif order_type == OrderType.STOP_LIMIT.value:
            limit_price = intent.get("limit_price")
            stop_price = intent.get("stop_price")
            if limit_price is None or stop_price is None:
                raise ValueError("STOP_LIMIT order requires limit_price and stop_price")
            order = StopLimitOrder(action, qty, float(limit_price), float(stop_price))
        elif order_type == OrderType.MARKET.value:
            order = MarketOrder(action, qty)
        else:
            raise ValueError(f"Unsupported order_type for live execution: {order_type}")

        order.tif = tif
        order.outsideRth = outside_rth
        order.transmit = True
        order.whatIf = bool(what_if)
        if self.account:
            order.account = self.account
        return order

    def _read_all_positions(self, ib: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            positions = ib.positions()
        except Exception:
            positions = []
        for p in positions:
            account = getattr(p, "account", None)
            if self.account and account != self.account:
                continue
            contract = getattr(p, "contract", None)
            qty = _clean_float(getattr(p, "position", None)) or 0.0
            if qty == 0:
                continue
            side = "LONG" if qty > 0 else "SHORT"
            out.append(
                {
                    "account": account,
                    "symbol": getattr(contract, "symbol", None),
                    "sec_type": getattr(contract, "secType", None),
                    "exchange": getattr(contract, "exchange", None),
                    "currency": getattr(contract, "currency", None),
                    "con_id": getattr(contract, "conId", None),
                    "side": side,
                    "position": qty,
                    "quantity": abs(qty),
                    "avg_cost": _clean_float(getattr(p, "avgCost", None)),
                }
            )
        return sorted(out, key=lambda x: (str(x.get("symbol") or ""), str(x.get("sec_type") or "")))

    def _read_all_open_orders(self, ib: Any) -> list[dict[str, Any]]:
        # reqAllOpenOrders helps expose orders from other API clients/TWS where permitted.
        try:
            ib.reqAllOpenOrders()
            ib.sleep(1)
        except Exception as exc:
            msg = str(exc)
            code = "COMPLETED_ORDERS_TIMEOUT" if "completed" in msg.lower() and "timeout" in msg.lower() else "REQ_ALL_OPEN_ORDERS_WARNING"
            self._warn(code, msg, "Non-fatal if current openTrades can still be read.")
        try:
            trades = ib.openTrades()
        except Exception as exc:
            self._warn("OPEN_TRADES_READ_FAILED", str(exc), "Open order list may be incomplete.")
            trades = []
        out = []
        for trade in trades:
            contract = getattr(trade, "contract", None)
            order = getattr(trade, "order", None)
            status = getattr(trade, "orderStatus", None)
            if not contract or not order:
                continue
            if self.account and getattr(order, "account", None) and getattr(order, "account", None) != self.account:
                continue
            if getattr(status, "status", "") in {"Filled", "Cancelled", "Inactive"}:
                continue
            out.append(self._trade_order_summary(trade))
        return sorted(out, key=lambda x: (str(x.get("symbol") or ""), int(x.get("order_id") or 0)))

    def _read_account_summary_full(self, ib: Any) -> dict[str, Any]:
        try:
            rows = ib.accountSummary(account=self.account) if self.account else ib.accountSummary()
        except TypeError:
            rows = ib.accountSummary()
        except Exception:
            rows = []
        wanted = {
            "AccountType",
            "NetLiquidation",
            "TotalCashValue",
            "SettledCash",
            "AccruedCash",
            "BuyingPower",
            "EquityWithLoanValue",
            "PreviousEquityWithLoanValue",
            "GrossPositionValue",
            "RegTEquity",
            "RegTMargin",
            "SMA",
            "InitMarginReq",
            "MaintMarginReq",
            "AvailableFunds",
            "ExcessLiquidity",
            "Cushion",
            "FullInitMarginReq",
            "FullMaintMarginReq",
            "FullAvailableFunds",
            "FullExcessLiquidity",
            "LookAheadNextChange",
            "LookAheadInitMarginReq",
            "LookAheadMaintMarginReq",
            "LookAheadAvailableFunds",
            "LookAheadExcessLiquidity",
            "HighestSeverity",
            "DayTradesRemaining",
        }
        out: dict[str, Any] = {"account": self.account, "tags": {}}
        for row in rows:
            tag = getattr(row, "tag", "")
            if tag not in wanted:
                continue
            out["tags"][tag] = {
                "value": getattr(row, "value", None),
                "currency": getattr(row, "currency", None),
                "account": getattr(row, "account", None),
            }
        return out

    def _portfolio_issues(self, positions: list[dict[str, Any]], open_orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        pos_by_symbol = {str(p.get("symbol") or "").upper(): p for p in positions}
        orders_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for order in open_orders:
            sym = str(order.get("symbol") or "").upper()
            if sym:
                orders_by_symbol.setdefault(sym, []).append(order)
        for sym, orders in orders_by_symbol.items():
            pos = pos_by_symbol.get(sym)
            if not pos:
                issues.append(
                    {
                        "level": "WARN",
                        "category": "OPEN_ORDERS_WITH_FLAT_OR_UNKNOWN_POSITION",
                        "symbol": sym,
                        "message": f"{sym} 有 {len(orders)} 张未成交订单，但当前账户未显示该标的持仓；请确认是否为开仓计划或残留订单。",
                    }
                )
                continue
            pos_qty = float(pos.get("quantity") or 0)
            pos_side = str(pos.get("side") or "").upper()
            closing_qty = 0.0
            for o in orders:
                side = str(o.get("side") or "").upper()
                if (pos_side == "LONG" and side == "SELL") or (pos_side == "SHORT" and side == "BUY"):
                    closing_qty += float(o.get("quantity") or 0)
            if pos_qty > 0 and closing_qty > pos_qty:
                issues.append(
                    {
                        "level": "WARN",
                        "category": "CLOSING_ORDERS_EXCEED_POSITION",
                        "symbol": sym,
                        "message": f"{sym} 平仓/保护方向未成交订单合计数量 {closing_qty} 超过当前持仓 {pos_qty}，可能导致意外反手。",
                    }
                )
        return issues

    def _read_position(self, ib: Any, symbol: str) -> PositionSnapshot:
        qty = 0
        avg_cost = None
        for p in ib.positions():
            if getattr(p.contract, "symbol", "").upper() == symbol.upper() and (
                not self.account or p.account == self.account
            ):
                qty += int(p.position)
                avg_cost = _clean_float(getattr(p, "avgCost", None))
        if qty > 0:
            side = PositionSide.LONG
        elif qty < 0:
            side = PositionSide.SHORT
        else:
            side = PositionSide.FLAT
        return PositionSnapshot(side=side, quantity=abs(qty), avg_cost=avg_cost)

    def _read_open_orders(self, ib: Any, symbol: str) -> list[dict[str, Any]]:
        return [self._trade_order_summary(t) for t in self._find_open_trades(ib, order_id=None, symbol=symbol)]

    def _read_account_summary(self, ib: Any) -> AccountSnapshot:
        summary = AccountSnapshot(account=self.account)
        try:
            rows = ib.accountSummary(account=self.account) if self.account else ib.accountSummary()
        except TypeError:
            rows = ib.accountSummary()
        except Exception:
            rows = []
        for row in rows:
            tag = getattr(row, "tag", "")
            value = _clean_float(getattr(row, "value", None))
            if tag == "AvailableFunds":
                summary.available_funds = value
            elif tag == "BuyingPower":
                summary.buying_power = value
            elif tag == "ExcessLiquidity":
                summary.excess_liquidity = value
        return summary

    def _read_market(self, ib: Any, contract: Any) -> MarketSnapshot:
        try:
            try:
                ib.reqMarketDataType(1)  # live
            except Exception:
                pass
            ticker = ib.reqMktData(contract, "", False, False)
            ib.sleep(2)
            market = self._ticker_to_market(ticker, "LIVE")
            if market.bid is not None or market.ask is not None or market.last is not None:
                try:
                    ib.cancelMktData(contract)
                except Exception:
                    pass
                return market

            if bool(self.market_data_config.get("try_delayed_if_live_missing", True)):
                try:
                    ib.cancelMktData(contract)
                except Exception:
                    pass
                try:
                    ib.reqMarketDataType(3)  # delayed
                except Exception:
                    pass
                ticker = ib.reqMktData(contract, "", False, False)
                ib.sleep(3)
                delayed = self._ticker_to_market(ticker, "DELAYED")
                try:
                    ib.cancelMktData(contract)
                except Exception:
                    pass
                if delayed.bid is not None or delayed.ask is not None or delayed.last is not None:
                    return delayed

            close_val = _clean_float(getattr(ticker, "close", None))
            return MarketSnapshot(
                close=close_val,
                market_data_status="MISSING",
                message="bid/ask/last not available. This may be caused by missing real-time market data subscription.",
            )
        except Exception as exc:
            return MarketSnapshot(market_data_status="ERROR", message=str(exc))

    def _ticker_to_market(self, ticker: Any, status: str) -> MarketSnapshot:
        bid = _clean_float(getattr(ticker, "bid", None))
        ask = _clean_float(getattr(ticker, "ask", None))
        last = _clean_float(getattr(ticker, "last", None))
        close = _clean_float(getattr(ticker, "close", None))
        message = ""
        if status == "DELAYED":
            message = "Delayed market data. Do not treat it as real-time bid/ask/last."
        return MarketSnapshot(bid=bid, ask=ask, last=last, close=close, market_data_status=status, message=message)

    def _order_state_to_dict(self, order_state: Any) -> dict[str, Any]:
        if order_state is None:
            return {}
        fields = {
            "status": "status",
            "init_margin_before": "initMarginBefore",
            "maint_margin_before": "maintMarginBefore",
            "equity_with_loan_before": "equityWithLoanBefore",
            "init_margin_change": "initMarginChange",
            "maint_margin_change": "maintMarginChange",
            "equity_with_loan_change": "equityWithLoanChange",
            "init_margin_after": "initMarginAfter",
            "maint_margin_after": "maintMarginAfter",
            "equity_with_loan_after": "equityWithLoanAfter",
            "commission": "commission",
            "min_commission": "minCommission",
            "max_commission": "maxCommission",
            "commission_currency": "commissionCurrency",
            "warning_text": "warningText",
            "completed_time": "completedTime",
            "completed_status": "completedStatus",
        }
        out: dict[str, Any] = {}
        for key, attr in fields.items():
            out[key] = getattr(order_state, attr, None)
        return out
