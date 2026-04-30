# Safe IBKR Order Gateway — Phase 2.2

`orderctl` is a short-lived, safety-first CLI for IBKR / ib_async order workflows.

Core design:

- OpenClaw does natural-language understanding and AI order review.
- `orderctl` reads IBKR facts, validates schemas, enforces hard gates, generates tickets, and performs submit/cancel/replace only after confirmation.
- `orderctl` is **not** a daemon and does **not** maintain a global clientId pool or file lock.
- Each command chooses a temporary clientId candidate range at connect time, retries on IBKR 326, disconnects, and exits.

## Current accounts

Paper:

```yaml
mode: paper
ibkr:
  host: "192.168.3.99"
  port: 4002
  account: "DUH705022"
  client_id_base: 100
  client_id_strategy: "connect_time_fallback"
```

Live:

```yaml
mode: live
ibkr:
  host: "192.168.3.50"
  port: 4001
  account: "U13288503"
  client_id_base: 200
  client_id_strategy: "connect_time_fallback"
```

Live trading remains disabled by default in `config/live.yaml`.

## Install

```bash
cd /home/ryan/trading/safe-ib-order-gateway
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optional wrapper:

```bash
sudo tee /usr/local/bin/orderctl >/dev/null <<'EOF'
#!/usr/bin/env bash
cd /home/ryan/trading/safe-ib-order-gateway || exit 1
exec /home/ryan/trading/safe-ib-order-gateway/.venv/bin/orderctl "$@"
EOF
sudo chmod +x /usr/local/bin/orderctl
```

## Phase 2.2 highlights

### 1. Connect-time clientId fallback

No global lock and no daemon.

Each command attempts a small candidate range. If IBKR returns error 326, the command tries the next candidate id.

Returned JSON includes:

```json
{
  "client_id_strategy": "connect_time_fallback",
  "client_id_used": 203,
  "client_id_attempts": [202, 203]
}
```

### 2. One-command portfolio overview

Preferred OpenClaw account overview command:

```bash
orderctl portfolio snapshot --mode live --with-quotes --with-pnl --compact
```

This returns account summary, all positions, open orders, quote/PnL where available, risk flags, and warnings.

If market data is missing, the command returns warnings and keeps the portfolio usable:

```json
{
  "code": "POSITION_MARKET_DATA_MISSING",
  "message": "No bid/ask/last available for WDC; PnL may be null."
}
```

### 3. Reconcile output separated by source

```bash
orderctl reconcile --all --mode live --compact
```

The output separates:

- `ibkr_current_state`: real current IBKR positions and open orders
- `local_state.active_plans`: local non-terminal orderctl plans
- `local_state.historical_plans`: local history only, not current IBKR orders
- `risk_flags`: active risks detected from current state

OpenClaw must not treat `historical_plans` as live IBKR open orders.

## Common commands

```bash
orderctl intent schema
orderctl intent examples
orderctl intent validate --intent examples/open_long_entry.json

orderctl health --mode live
orderctl portfolio snapshot --mode live --with-quotes --with-pnl --compact
orderctl positions list --mode live --compact
orderctl orders list --mode live --compact
orderctl reconcile --all --mode live --compact
```

Single-symbol workflow:

```bash
orderctl snapshot --symbol WDC --mode live --fresh
orderctl plan create --intent /tmp/order_intent.json --mode live
orderctl check hard --plan-id <PLAN_ID> --mode live
orderctl review attach --plan-id <PLAN_ID> --review /tmp/ai_review.json
orderctl preview --plan-id <PLAN_ID> --mode live
orderctl ticket --plan-id <PLAN_ID>
orderctl submit --plan-id <PLAN_ID> --phrase "<CONFIRM_PHRASE>" --mode live --approval-token "<TOKEN>"
```

Submit still only accepts `plan_id + phrase + mode + approval-token`; it never accepts symbol/quantity/price.
