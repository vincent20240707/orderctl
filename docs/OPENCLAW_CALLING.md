# OpenClaw Calling Guide — orderctl Phase 2.2

Project path:

`/home/ryan/trading/safe-ib-order-gateway`

Command entry:

`orderctl`

## Key Phase 2.2 changes

- `orderctl` is a short-lived CLI, not a daemon.
- No global file lock and no persistent clientId pool.
- Each IBKR command uses connect-time clientId fallback and disconnects when done.
- Account overview should prefer one compact command instead of many smaller queries.
- Warnings are structured in JSON where possible.
- `reconcile` separates current IBKR state from local historical plans.

## Recommended lightweight query strategy

### User asks account overview / current live status

Use one command first:

```bash
orderctl portfolio snapshot --mode live --with-quotes --with-pnl --compact
```

Do not immediately run `account summary`, `positions list`, `orders list`, per-symbol snapshots, and `reconcile` unless the first command indicates a risk or the user asks for details.

### User asks all positions

```bash
orderctl positions list --mode live --compact
```

If PnL or quotes are needed:

```bash
orderctl portfolio snapshot --mode live --with-quotes --with-pnl --compact
```

### User asks all open orders

```bash
orderctl orders list --mode live --compact
```

### User asks abnormal orders / leftover protective orders / reconciliation

```bash
orderctl reconcile --all --mode live --compact
```

### User asks a single symbol

```bash
orderctl snapshot --symbol <SYMBOL> --mode live --fresh
```

## clientId rule

`orderctl` handles clientId automatically by trying a temporary candidate range.

If output includes:

```json
"client_id_attempts": [202, 203],
"client_id_used": 203
```

that is normal. It means a prior candidate was busy and orderctl connected with another id.

If all candidates fail, report the error and do not loop aggressively.

## Market data rule

If quotes are missing, do not invent real-time prices.

For explicit limit orders, missing quotes are a warning.

For requests like “buy at current price”, missing quotes means UNKNOWN; ask the user for an explicit limit price or request real-time data setup.

## Reconcile interpretation rule

`reconcile` output has separate sections:

- `ibkr_current_state.open_orders`: actual current IBKR open orders
- `local_state.active_plans`: local non-terminal orderctl plans
- `local_state.historical_plans`: local history only

Never describe `local_state.historical_plans` as current IBKR open orders.

## Standard order flow

```bash
orderctl health --mode <paper|live>
orderctl snapshot --symbol <SYMBOL> --mode <paper|live> --fresh
orderctl intent validate --intent <ORDER_INTENT_JSON>
orderctl plan create --intent <ORDER_INTENT_JSON> --mode <paper|live>
orderctl check hard --plan-id <PLAN_ID> --mode <paper|live>
# OpenClaw performs AI review and writes AI_REVIEW_JSON
orderctl review attach --plan-id <PLAN_ID> --review <AI_REVIEW_JSON>
orderctl preview --plan-id <PLAN_ID> --mode <paper|live>
orderctl ticket --plan-id <PLAN_ID>
# Wait for exact user confirmation phrase
orderctl submit --plan-id <PLAN_ID> --phrase "<CONFIRM_PHRASE>" --mode <paper|live> [--approval-token <TOKEN>]
```

## Never do this

- Never bypass `orderctl`.
- Never call ib_async / IBKR API directly from OpenClaw.
- Never submit without `ticket` and exact confirmation phrase.
- Never let `submit` receive symbol / quantity / price.
- Never enable live trading in config automatically.
