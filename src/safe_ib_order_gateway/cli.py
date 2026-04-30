from __future__ import annotations

import argparse

from safe_ib_order_gateway.config import load_config, print_json
from safe_ib_order_gateway.services.audit_service import audit_list, audit_show
from safe_ib_order_gateway.services.account_service import (
    account_summary,
    orders_list,
    portfolio_snapshot,
    positions_list,
)
from safe_ib_order_gateway.services.cancel_service import cancel_submit, cancel_ticket
from safe_ib_order_gateway.services.hard_gate_service import run_hard_check
from safe_ib_order_gateway.services.health_service import health
from safe_ib_order_gateway.services.intent_service import intent_examples, intent_schema, validate_intent
from safe_ib_order_gateway.services.plan_service import create_plan
from safe_ib_order_gateway.services.preview_service import ibkr_what_if_preview, local_preview
from safe_ib_order_gateway.services.reconcile_service import reconcile
from safe_ib_order_gateway.services.replace_service import replace_check, replace_plan, replace_submit, replace_ticket
from safe_ib_order_gateway.services.review_service import attach_review
from safe_ib_order_gateway.services.snapshot_service import snapshot
from safe_ib_order_gateway.services.submit_service import submit_order
from safe_ib_order_gateway.services.ticket_service import generate_ticket


def add_common_mode(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--config", default=None, help="Optional config YAML path")


def add_client_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--client-id", type=int, default=None, help="Override IBKR clientId for this command")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orderctl", description="Safe IBKR order gateway CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("health", help="Check IBKR connectivity and config")
    add_common_mode(p); add_client_id(p)

    p = sub.add_parser("snapshot", help="Read fresh symbol/account/order snapshot")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--symbol", required=True)
    p.add_argument("--fresh", action="store_true", help="Force fresh IBKR read; default behavior is fresh")

    intent = sub.add_parser("intent", help="OrderIntent schema/examples/validate commands")
    intent_sub = intent.add_subparsers(dest="intent_command", required=True)
    intent_sub.add_parser("schema", help="Print OrderIntent schema and allowed enum values")
    intent_sub.add_parser("examples", help="Print valid OrderIntent examples")
    p = intent_sub.add_parser("validate", help="Validate OrderIntent JSON")
    p.add_argument("--intent", required=True)

    plan = sub.add_parser("plan", help="Plan commands")
    plan_sub = plan.add_subparsers(dest="plan_command", required=True)
    p = plan_sub.add_parser("create", help="Create immutable order plan from OrderIntent JSON")
    add_common_mode(p)
    p.add_argument("--intent", required=True, help="Path to OrderIntent JSON")

    check = sub.add_parser("check", help="Check commands")
    check_sub = check.add_subparsers(dest="check_command", required=True)
    p = check_sub.add_parser("hard", help="Run deterministic hard gates")
    add_common_mode(p)
    p.add_argument("--plan-id", required=True)

    review = sub.add_parser("review", help="AI review commands")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    p = review_sub.add_parser("attach", help="Attach OpenClaw AI review JSON to a plan")
    p.add_argument("--plan-id", required=True)
    p.add_argument("--review", required=True, help="Path to AI review JSON")

    p = sub.add_parser("preview", help="Generate IBKR What-If preview for a plan; use --local for offline local preview")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--plan-id", required=True)
    p.add_argument("--local", action="store_true", help="Use local preview only; does not query IBKR What-If")

    p = sub.add_parser("ticket", help="Generate confirmation ticket")
    p.add_argument("--plan-id", required=True)

    p = sub.add_parser("submit", help="Submit reviewed and confirmed plan to IBKR. Only accepts plan_id + confirmation phrase.")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--plan-id", required=True)
    p.add_argument("--phrase", required=True)
    p.add_argument("--approval-token", default=None)

    cancel = sub.add_parser("cancel", help="Cancel order commands")
    cancel_sub = cancel.add_subparsers(dest="cancel_command", required=True)
    p = cancel_sub.add_parser("ticket", help="Generate cancel confirmation ticket")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--order-id", type=int, default=None)
    p.add_argument("--symbol", default=None)
    p = cancel_sub.add_parser("submit", help="Submit cancel request after confirmation phrase")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--order-id", type=int, default=None)
    p.add_argument("--symbol", default=None)
    p.add_argument("--phrase", required=True)

    replace = sub.add_parser("replace", help="Replace/modify order commands; v2 supports limit-price changes only")
    replace_sub = replace.add_subparsers(dest="replace_command", required=True)
    p = replace_sub.add_parser("plan", help="Create replace plan for limit price change")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--order-id", type=int, required=True)
    p.add_argument("--new-limit-price", type=float, required=True)
    p = replace_sub.add_parser("check", help="Check replace plan")
    p.add_argument("--replace-plan-id", required=True)
    p = replace_sub.add_parser("ticket", help="Generate replace confirmation ticket")
    p.add_argument("--replace-plan-id", required=True)
    p = replace_sub.add_parser("submit", help="Submit replace after confirmation phrase")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--replace-plan-id", required=True)
    p.add_argument("--phrase", required=True)

    account = sub.add_parser("account", help="Account summary commands")
    account_sub = account.add_subparsers(dest="account_command", required=True)
    p = account_sub.add_parser("summary", help="List account-level summary tags")
    add_common_mode(p); add_client_id(p)

    positions = sub.add_parser("positions", help="Position commands")
    positions_sub = positions.add_subparsers(dest="positions_command", required=True)
    p = positions_sub.add_parser("list", help="List all positions for the configured account")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--compact", action="store_true", help="Return compact position fields")

    orders = sub.add_parser("orders", help="Open order commands")
    orders_sub = orders.add_subparsers(dest="orders_command", required=True)
    p = orders_sub.add_parser("list", help="List all open orders for the configured account")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--compact", action="store_true", help="Return compact order fields")

    portfolio = sub.add_parser("portfolio", help="Portfolio-wide snapshot commands")
    portfolio_sub = portfolio.add_subparsers(dest="portfolio_command", required=True)
    p = portfolio_sub.add_parser("snapshot", help="Read account summary + all positions + all open orders")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--with-quotes", action="store_true", help="Fetch quotes for each position")
    p.add_argument("--with-pnl", action="store_true", help="Calculate per-position and total unrealized PnL when quotes are available")
    p.add_argument("--compact", action="store_true", help="Return compact token-efficient portfolio output")

    p = sub.add_parser("reconcile", help="Compare IBKR current state with local plans/audit")
    add_common_mode(p); add_client_id(p)
    p.add_argument("--symbol", default=None)
    p.add_argument("--all", action="store_true", help="Reconcile the whole account instead of a single symbol")
    p.add_argument("--compact", action="store_true", help="Return compact reconcile output")

    audit = sub.add_parser("audit", help="Audit commands")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)
    p = audit_sub.add_parser("list", help="List recent audit events")
    p.add_argument("--limit", type=int, default=50)
    p = audit_sub.add_parser("show", help="Show full saved plan/audit object")
    p.add_argument("--plan-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "health":
            cfg = load_config(args.mode, args.config)
            print_json(health(cfg, args.client_id)); return 0

        if args.command == "snapshot":
            cfg = load_config(args.mode, args.config)
            print_json(snapshot(cfg, args.symbol, fresh=True, client_id=args.client_id)); return 0

        if args.command == "intent":
            if args.intent_command == "schema": print_json(intent_schema()); return 0
            if args.intent_command == "examples": print_json(intent_examples()); return 0
            if args.intent_command == "validate": print_json(validate_intent(args.intent)); return 0

        if args.command == "plan" and args.plan_command == "create":
            load_config(args.mode, args.config)
            print_json(create_plan(args.intent, args.mode)); return 0

        if args.command == "check" and args.check_command == "hard":
            cfg = load_config(args.mode, args.config)
            print_json(run_hard_check(cfg, args.plan_id)); return 0

        if args.command == "review" and args.review_command == "attach":
            print_json(attach_review(args.plan_id, args.review)); return 0

        if args.command == "preview":
            if args.local: print_json(local_preview(args.plan_id))
            else:
                cfg = load_config(args.mode, args.config)
                print_json(ibkr_what_if_preview(cfg, args.plan_id, args.client_id))
            return 0

        if args.command == "ticket":
            result = generate_ticket(args.plan_id)
            print(result["ticket"]); return 0

        if args.command == "submit":
            cfg = load_config(args.mode, args.config)
            print_json(submit_order(cfg, args.plan_id, args.phrase, args.mode, args.approval_token, args.client_id)); return 0

        if args.command == "cancel":
            cfg = load_config(args.mode, args.config)
            if args.cancel_command == "ticket":
                print_json(cancel_ticket(cfg, args.mode, args.order_id, args.symbol, args.client_id)); return 0
            if args.cancel_command == "submit":
                print_json(cancel_submit(cfg, args.mode, args.phrase, args.order_id, args.symbol, args.client_id)); return 0

        if args.command == "replace":
            if args.replace_command == "plan":
                cfg = load_config(args.mode, args.config)
                print_json(replace_plan(cfg, args.mode, args.order_id, args.new_limit_price, args.client_id)); return 0
            if args.replace_command == "check": print_json(replace_check(args.replace_plan_id)); return 0
            if args.replace_command == "ticket":
                result = replace_ticket(args.replace_plan_id)
                print(result["ticket"]); return 0
            if args.replace_command == "submit":
                cfg = load_config(args.mode, args.config)
                print_json(replace_submit(cfg, args.mode, args.replace_plan_id, args.phrase, args.client_id)); return 0

        if args.command == "account" and args.account_command == "summary":
            cfg = load_config(args.mode, args.config)
            print_json(account_summary(cfg, args.mode, args.client_id)); return 0

        if args.command == "positions" and args.positions_command == "list":
            cfg = load_config(args.mode, args.config)
            print_json(positions_list(cfg, args.mode, args.client_id, compact=args.compact)); return 0

        if args.command == "orders" and args.orders_command == "list":
            cfg = load_config(args.mode, args.config)
            print_json(orders_list(cfg, args.mode, args.client_id, compact=args.compact)); return 0

        if args.command == "portfolio" and args.portfolio_command == "snapshot":
            cfg = load_config(args.mode, args.config)
            print_json(portfolio_snapshot(cfg, args.mode, args.client_id, with_quotes=args.with_quotes, with_pnl=args.with_pnl, compact=args.compact)); return 0

        if args.command == "reconcile":
            cfg = load_config(args.mode, args.config)
            print_json(reconcile(cfg, args.symbol, args.mode, args.client_id, all_symbols=args.all, compact=args.compact)); return 0

        if args.command == "audit" and args.audit_command == "list":
            print_json(audit_list(args.limit)); return 0

        if args.command == "audit" and args.audit_command == "show":
            print_json(audit_show(args.plan_id)); return 0

        parser.error("Unsupported command")
        return 2
    except Exception as exc:
        print_json({"status": "ERROR", "error": str(exc), "type": exc.__class__.__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
