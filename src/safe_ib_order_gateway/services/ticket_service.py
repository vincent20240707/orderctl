from __future__ import annotations

from typing import Any

from safe_ib_order_gateway.services.storage import append_audit, load_plan, save_plan, ticket_path


def confirmation_phrase(plan: dict[str, Any]) -> str:
    intent = plan["intent"]
    price = intent.get("limit_price") or intent.get("stop_price") or "MKT"
    if isinstance(price, float):
        price_s = f"{price:.2f}"
    else:
        price_s = str(price)
    return f"CONFIRM {intent['symbol']} {intent['intent_type']} {intent['quantity']} @ {price_s}"


def generate_ticket(plan_id: str) -> dict[str, Any]:
    plan = load_plan(plan_id)
    intent = plan["intent"]
    hard = plan.get("hard_check") or {}
    ai_review = plan.get("ai_review") or {}
    preview = plan.get("preview") or {}
    phrase = confirmation_phrase(plan)

    lines = [
        "订单确认票据",
        "",
        f"Plan ID：{plan_id}",
        f"模式：{plan.get('mode')}",
        f"股票：{intent.get('symbol')}",
        f"订单语义：{intent.get('intent_type')}",
        f"订单角色：{intent.get('order_role')}",
        f"买卖方向：{intent.get('side')}",
        f"数量：{intent.get('quantity')} 股",
        f"订单类型：{intent.get('order_type')}",
        f"限价：{intent.get('limit_price')}",
        f"止损价：{intent.get('stop_price')}",
        f"允许盘前盘后：{intent.get('outside_rth')}",
        f"交易理由：{intent.get('reason')}",
        "",
        f"当前持仓：{preview.get('position_before') or hard.get('position_before')}",
        f"成交后预计持仓：{preview.get('position_after') or hard.get('position_after')}",
        f"预计金额：{preview.get('estimated_notional') or hard.get('estimated_notional')}",
        "",
        f"硬闸门结论：{hard.get('verdict')}",
        f"硬闸门 BLOCK：{hard.get('blocks')}",
        f"硬闸门 WARN：{hard.get('warnings')}",
        "",
        f"AI 审查结论：{ai_review.get('verdict')}",
        f"AI 审查摘要：{ai_review.get('summary')}",
        f"AI 审查问题：{ai_review.get('issues')}",
        "",
        "确认语：",
        phrase,
        "",
        "用户没有完整输入确认语，不得提交。",
    ]
    text = "\n".join(lines)
    path = ticket_path(plan_id)
    path.write_text(text, encoding="utf-8")
    plan["ticket"] = {"path": str(path), "confirmation_phrase": phrase, "text": text}
    plan["status"] = "TICKET_READY"
    save_plan(plan)
    append_audit("TICKET", {"plan_id": plan_id, "confirmation_phrase": phrase})
    return {"plan_id": plan_id, "confirmation_phrase": phrase, "ticket_path": str(path), "ticket": text}
