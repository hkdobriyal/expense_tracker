"""'Ask your money' assistant.

Two engines, same numbers:

* **rules** (always available): a small question parser for common questions
  ("how much did I spend on restaurants last month", "compare August and
  September", "which subscriptions cost the most"…).
* **local LLM** (optional, via services/llm.py): the model chooses tools and
  writes the sentence, but every figure comes from the ledger tools below –
  the model never computes or invents amounts.
"""

from __future__ import annotations

import calendar
import json
import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Category, Merchant, Subscription, Transaction
from ..money import format_display
from . import budgets as budget_svc
from . import ledger, llm, networth
from . import subscriptions as sub_svc
from .context import UserContext
from .periods import add_months, month_bounds, week_bounds, year_bounds

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m} | {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m} | {"sept": 9}


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------

def resolve_period(text: str | None, today: date) -> tuple[date, date, str]:
    t = (text or "this month").strip().lower()
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s*(?:\.\.|to|–|-)\s*(\d{4}-\d{2}-\d{2})", t)
    if m:
        a, b = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
        return a, b, f"{a:%d %b %Y} – {b:%d %b %Y}"
    m = re.fullmatch(r"(\d{4})-(\d{2})", t)
    if m:
        s, e = month_bounds(date(int(m.group(1)), int(m.group(2)), 1))
        return s, e, s.strftime("%B %Y")
    if "last month" in t or "previous month" in t:
        s, e = month_bounds(add_months(today, -1))
        return s, e, s.strftime("%B %Y")
    if "this week" in t:
        s, e = week_bounds(today)
        return s, today, "this week"
    if "last week" in t:
        s, e = week_bounds(today - timedelta(days=7))
        return s, e, "last week"
    if "today" in t:
        return today, today, "today"
    if "yesterday" in t:
        y = today - timedelta(days=1)
        return y, y, "yesterday"
    if "last year" in t:
        s, e = year_bounds(date(today.year - 1, 1, 1))
        return s, e, str(today.year - 1)
    if "this year" in t or "year to date" in t or "ytd" in t:
        return date(today.year, 1, 1), today, str(today.year)
    m = re.search(r"(?:last|past)\s+(\d+)\s*(day|week|month)s?", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        start = today - timedelta(days=n - 1) if unit == "day" else today - timedelta(weeks=n) if unit == "week" else add_months(today, -n) + timedelta(days=1)
        return start, today, f"last {n} {unit}s"
    for name, idx in MONTHS.items():
        m = re.search(rf"\b{name}\b(?:\s+(\d{{4}}))?", t)
        if m:
            year = int(m.group(1)) if m.group(1) else (today.year if idx <= today.month else today.year - 1)
            s, e = month_bounds(date(year, idx, 1))
            return s, e, s.strftime("%B %Y")
    s, e = month_bounds(today)
    return s, today, s.strftime("%B %Y")


def _months_in(question: str, today: date) -> list[tuple[date, date, str]]:
    found = []
    for m in re.finditer(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b(?:\s+(\d{4}))?", question.lower()):
        idx = MONTHS[m.group(1)]
        year = int(m.group(2)) if m.group(2) else (today.year if idx <= today.month else today.year - 1)
        s, e = month_bounds(date(year, idx, 1))
        if (s, e, s.strftime("%B %Y")) not in found:
            found.append((s, e, s.strftime("%B %Y")))
    return found


# ---------------------------------------------------------------------------
# Ledger tools (shared by both engines)
# ---------------------------------------------------------------------------

class Tools:
    def __init__(self, db: Session, ctx: UserContext):
        self.db, self.ctx = db, ctx
        self.cur = ctx.base_currency
        self.categories = db.scalars(select(Category).where(Category.user_id == ctx.user_id)).all()

    def m(self, minor: int) -> str:
        return format_display(minor, self.cur)

    def find_category(self, name: str | None) -> Category | None:
        if not name:
            return None
        n = name.strip().lower().rstrip("s")
        exact = [c for c in self.categories if c.name.lower().rstrip("s") == n]
        if exact:
            return sorted(exact, key=lambda c: c.parent_id is not None)[0]
        partial = [c for c in self.categories if n in c.name.lower() or c.name.lower().rstrip("s") in n]
        return sorted(partial, key=lambda c: (c.parent_id is not None, len(c.name)))[0] if partial else None

    def find_merchant(self, name: str | None) -> Merchant | None:
        if not name:
            return None
        return self.db.scalar(select(Merchant).where(Merchant.user_id == self.ctx.user_id, Merchant.name.ilike(f"%{name.strip()}%")).limit(1))

    def spending(self, period: str = "this month", category: str | None = None, merchant: str | None = None) -> dict:
        s, e, label = resolve_period(period, self.ctx.today)
        if merchant and not category:
            mer = self.find_merchant(merchant)
            if mer is None:
                return {"error": f"No merchant matching '{merchant}'"}
            rows = self.db.execute(select(Transaction.type, Transaction.base_amount_minor).where(
                Transaction.user_id == self.ctx.user_id, Transaction.merchant_id == mer.id, Transaction.date >= s, Transaction.date <= e,
                Transaction.type.in_(("expense", "refund")))).all()
            total = sum(a if t == "expense" else -a for t, a in rows)
            return {"period": label, "merchant": mer.name, "spent": total, "spent_text": self.m(total), "transactions": len(rows)}
        cat = self.find_category(category) if category else None
        if category and cat is None:
            return {"error": f"No category matching '{category}'"}
        ids = ledger.descendant_ids(self.categories, cat.id) if cat else None
        total = ledger.spent_in_categories(self.db, self.ctx.user_id, ids, s, e)
        out = {"period": label, "category": cat.name if cat else "all spending", "spent": total, "spent_text": self.m(total)}
        if cat is None:
            out["top_categories"] = [{"name": g["name"], "amount": self.m(g["amount"]), "share_pct": g["share"]} for g in ledger.category_breakdown(self.db, self.ctx.user_id, s, e)[:6]]
        return out

    def income(self, period: str = "this month") -> dict:
        s, e, label = resolve_period(period, self.ctx.today)
        t = ledger.period_totals(self.db, self.ctx.user_id, s, e)
        return {"period": label, "income": self.m(t.income), "expenses": self.m(t.expenses), "saved": self.m(t.savings), "savings_rate_pct": t.savings_rate}

    def compare(self, period_a: str, period_b: str) -> dict:
        a0, a1, la = resolve_period(period_a, self.ctx.today)
        b0, b1, lb = resolve_period(period_b, self.ctx.today)
        ta, tb = ledger.period_totals(self.db, self.ctx.user_id, a0, a1), ledger.period_totals(self.db, self.ctx.user_id, b0, b1)
        ca = {g["name"]: g["amount"] for g in ledger.category_breakdown(self.db, self.ctx.user_id, a0, a1)}
        cb = {g["name"]: g["amount"] for g in ledger.category_breakdown(self.db, self.ctx.user_id, b0, b1)}
        changes = sorted(((n, cb.get(n, 0) - ca.get(n, 0)) for n in set(ca) | set(cb)), key=lambda x: -abs(x[1]))
        return {
            "a": la, "b": lb, "expenses_a": self.m(ta.expenses), "expenses_b": self.m(tb.expenses), "income_a": self.m(ta.income), "income_b": self.m(tb.income),
            "expense_change": self.m(tb.expenses - ta.expenses), "biggest_changes": [{"category": n, "change": self.m(d)} for n, d in changes[:5] if d],
            "_raw": {"a": ta.expenses, "b": tb.expenses, "changes": changes[:5]},
        }

    def top_merchants(self, period: str = "this month", limit: int = 5) -> dict:
        s, e, label = resolve_period(period, self.ctx.today)
        rows = ledger.merchant_breakdown(self.db, self.ctx.user_id, s, e, int(limit))
        return {"period": label, "merchants": [{"name": r["name"], "amount": self.m(r["amount"]), "transactions": r["count"]} for r in rows]}

    def largest_expenses(self, period: str = "this month", limit: int = 5) -> dict:
        s, e, label = resolve_period(period, self.ctx.today)
        rows = self.db.scalars(select(Transaction).where(Transaction.user_id == self.ctx.user_id, Transaction.type == "expense", Transaction.date >= s, Transaction.date <= e)
                               .order_by(Transaction.base_amount_minor.desc()).limit(int(limit))).all()
        return {"period": label, "expenses": [{"date": t.date.isoformat(), "description": t.description, "amount": self.m(t.base_amount_minor), "category": t.category.name if t.category else None} for t in rows]}

    def subscriptions(self) -> dict:
        subs = self.db.scalars(select(Subscription).where(Subscription.user_id == self.ctx.user_id, Subscription.active.is_(True))).all()
        items = sorted(({"name": s.name, "price": format_display(s.amount_minor, s.currency), "frequency": s.frequency, "monthly": sub_svc.equivalents(s)["monthly_equivalent"],
                         "next_payment": s.next_payment_date.isoformat() if s.next_payment_date else None} for s in subs), key=lambda x: -x["monthly"])
        total = sum(i["monthly"] for i in items)
        for i in items:
            i["monthly"] = self.m(i["monthly"])
        return {"count": len(items), "monthly_total": self.m(total), "annual_total": self.m(total * 12), "subscriptions": items}

    def category_trend(self, period: str = "this month") -> dict:
        s, e, label = resolve_period(period, self.ctx.today)
        prev_s, prev_e = month_bounds(add_months(s, -1)) if s.day == 1 else (s - (e - s) - timedelta(days=1), s - timedelta(days=1))
        cur = {g["name"]: g["amount"] for g in ledger.category_breakdown(self.db, self.ctx.user_id, s, e)}
        prev = {g["name"]: g["amount"] for g in ledger.category_breakdown(self.db, self.ctx.user_id, prev_s, prev_e)}
        changes = sorted(((n, cur.get(n, 0) - prev.get(n, 0), prev.get(n, 0)) for n in set(cur) | set(prev)), key=lambda x: -x[1])
        return {"period": label, "compared_with": f"{prev_s:%d %b} – {prev_e:%d %b}",
                "increases": [{"category": n, "change": self.m(d), "change_pct": round(d / p * 100) if p else None} for n, d, p in changes if d > 0][:5],
                "decreases": [{"category": n, "change": self.m(d)} for n, d, _ in reversed(changes) if d < 0][:3]}

    def budgets(self) -> dict:
        rows = budget_svc.all_budget_statuses(self.db, self.ctx.user_id, self.ctx.today, self.ctx.week_start)
        return {"budgets": [{"name": b.name, "spent": self.m(st["spent"]), "limit": self.m(st["limit"]), "used_pct": st["usage_pct"], "remaining": self.m(st["remaining"]), "status": st["status"]} for b, st in rows]}

    def net_worth(self) -> dict:
        nw = networth.net_worth(self.db, self.ctx.user_id, self.cur, self.ctx.today)
        return {"net_worth": self.m(nw["net_worth"]), "assets": self.m(nw["assets"]), "liabilities": self.m(nw["liabilities"])}

    SCHEMAS = [
        ("spending", "Total spending in a period, optionally for one category or merchant. Also returns top categories.", {"period": "string", "category": "string", "merchant": "string"}),
        ("income", "Income, expenses, amount saved and savings rate for a period.", {"period": "string"}),
        ("compare", "Compare spending and income between two periods, with the categories that changed most.", {"period_a": "string", "period_b": "string"}),
        ("top_merchants", "Merchants with the highest spending in a period.", {"period": "string", "limit": "integer"}),
        ("largest_expenses", "Largest individual expenses in a period.", {"period": "string", "limit": "integer"}),
        ("subscriptions", "Active subscriptions with monthly/annual cost, most expensive first.", {}),
        ("category_trend", "Which categories increased or decreased versus the previous period.", {"period": "string"}),
        ("budgets", "Budget usage for the current period.", {}),
        ("net_worth", "Current net worth, assets and liabilities.", {}),
    ]

    def openai_tools(self) -> list[dict]:
        period_help = "e.g. 'this month', 'last month', 'August 2026', '2026-08', 'last 30 days', 'this year'"
        return [{"type": "function", "function": {"name": n, "description": d, "parameters": {
            "type": "object", "properties": {k: {"type": t, "description": period_help if "period" in k else ""} for k, t in props.items()}}}} for n, d, props in self.SCHEMAS]

    def call(self, name: str, args: dict) -> dict:
        if name not in {n for n, _, _ in self.SCHEMAS}:
            return {"error": f"unknown tool {name}"}
        allowed = next(p for n, _, p in self.SCHEMAS if n == name)
        try:
            return getattr(self, name)(**{k: v for k, v in (args or {}).items() if k in allowed and v not in (None, "")})
        except Exception as exc:  # noqa: BLE001 - tool errors go back to the model/user as data
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Rules engine
# ---------------------------------------------------------------------------

def _rules_answer(tools: Tools, q: str) -> dict:
    text = q.lower()
    today = tools.ctx.today
    months = _months_in(q, today)
    if "compare" in text or " vs " in text or "versus" in text:
        if len(months) >= 2:
            a, b = months[0], months[1]
        elif "last month" in text or "this month" in text:
            a, b = resolve_period("last month", today), resolve_period("this month", today)
        else:
            return {"answer": "Which two periods? For example: “Compare August and September”."}
        r = tools.compare(a[0].strftime("%Y-%m"), b[0].strftime("%Y-%m")) if a[0].day == 1 else tools.compare("last month", "this month")
        changes = ", ".join(f"{c['category']} {c['change']}" for c in r["biggest_changes"][:3])
        diff = r["_raw"]["b"] - r["_raw"]["a"]
        answer = (f"You spent {r['expenses_a']} in {r['a']} and {r['expenses_b']} in {r['b']} – "
                  f"{'up' if diff > 0 else 'down'} {tools.m(abs(diff))}." + (f" Biggest changes: {changes}." if changes else ""))
        return {"answer": answer, "data": {k: v for k, v in r.items() if k != "_raw"}}
    period_text = q
    if "subscription" in text:
        r = tools.subscriptions()
        if not r["count"]:
            return {"answer": "You have no active subscriptions tracked yet.", "data": r}
        top = ", ".join(f"{s['name']} ({s['monthly']}/month)" for s in r["subscriptions"][:4])
        return {"answer": f"{r['count']} active subscriptions cost {r['monthly_total']} a month ({r['annual_total']} a year). Most expensive: {top}.", "data": r}
    if "net worth" in text or "worth" in text:
        r = tools.net_worth()
        return {"answer": f"Your net worth is {r['net_worth']}: {r['assets']} in assets minus {r['liabilities']} in liabilities.", "data": r}
    if "budget" in text:
        r = tools.budgets()
        if not r["budgets"]:
            return {"answer": "You haven't created any budgets yet.", "data": r}
        worst = sorted(r["budgets"], key=lambda b: -b["used_pct"])
        return {"answer": " ".join(f"{b['name']}: {b['spent']} of {b['limit']} ({b['used_pct']:.0f}%)." for b in worst[:4]), "data": r}
    if re.search(r"increas|went up|grew|rising|more than usual", text):
        r = tools.category_trend(period_text)
        if not r["increases"]:
            return {"answer": f"No category increased in {r['period']} compared with {r['compared_with']}.", "data": r}
        top = r["increases"][0]
        pct = f" ({top['change_pct']:+d}%)" if top["change_pct"] is not None else ""
        return {"answer": f"{top['category']} increased the most in {r['period']}: {top['change']} more{pct} than {r['compared_with']}.", "data": r}
    if re.search(r"earn|income|salary|saved|saving", text):
        r = tools.income(period_text)
        return {"answer": f"In {r['period']} you earned {r['income']}, spent {r['expenses']} and saved {r['saved']} ({r['savings_rate_pct']:.0f}% savings rate).", "data": r}
    if re.search(r"largest|biggest|highest (?:expense|payment|transaction)|most expensive", text) and "categor" not in text and "merchant" not in text:
        r = tools.largest_expenses(period_text)
        if not r["expenses"]:
            return {"answer": f"No expenses in {r['period']}.", "data": r}
        e = r["expenses"][0]
        return {"answer": f"Your largest expense in {r['period']} was {e['description']} – {e['amount']} on {e['date']}.", "data": r}
    if "merchant" in text or re.search(r"\bwhere\b.*\bmost\b|\bwho\b.*\bmost\b", text) and "categor" not in text:
        r = tools.top_merchants(period_text)
        if not r["merchants"]:
            return {"answer": f"No merchant spending in {r['period']}.", "data": r}
        return {"answer": f"Top merchants in {r['period']}: " + ", ".join(f"{m['name']} {m['amount']}" for m in r["merchants"][:5]) + ".", "data": r}
    # "how much did I spend on X", "spent on restaurants last month", "where did I spend the most"
    m = re.search(r"(?:spen[dt]|pay|paid|cost)\s+(?:on|at|for|in)\s+([a-z0-9 &'.-]+?)(?:\s+(?:in|during|this|last|past|over|for|since|today|yesterday)\b|\?|$)", text)
    target = m.group(1).strip() if m else None
    if target and tools.find_category(target):
        r = tools.spending(period_text, category=target)
        return {"answer": f"You spent {r['spent_text']} on {r['category']} in {r['period']}.", "data": r}
    if target and tools.find_merchant(target):
        r = tools.spending(period_text, merchant=target)
        return {"answer": f"You spent {r['spent_text']} at {r['merchant']} in {r['period']} ({r['transactions']} transactions).", "data": r}
    if re.search(r"spen[dt]|expense|where", text):
        r = tools.spending(period_text)
        top = r.get("top_categories") or []
        tail = f" Most went to {top[0]['name']} ({top[0]['amount']}, {top[0]['share_pct']:.0f}%)" + (f", then {top[1]['name']} ({top[1]['amount']})" if len(top) > 1 else "") + "." if top else ""
        return {"answer": f"You spent {r['spent_text']} in {r['period']}.{tail}", "data": r}
    return {"answer": "I can answer questions about spending, income, savings, budgets, subscriptions, merchants and net worth. Try: "
                      "“How much did I spend on food delivery last month?”, “Compare August and September”, or “Which category increased the most?”"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def ask(db: Session, ctx: UserContext, question: str, use_llm: bool = True) -> dict:
    tools = Tools(db, ctx)
    question = question.strip()[:500]
    if use_llm and llm.status()["available"]:
        try:
            return _llm_answer(tools, question)
        except llm.LLMUnavailable:
            pass  # fall through to the rules engine
    result = _rules_answer(tools, question)
    return {**result, "engine": "rules"}


def _llm_answer(tools: Tools, question: str) -> dict:
    system = (
        f"You are the assistant inside a personal finance app. Today is {tools.ctx.today:%d %B %Y}; amounts are in {tools.cur}. "
        "Always call a tool to get numbers – never calculate or guess amounts yourself, and only state figures that appear in tool results. "
        "Answer in 1–3 short sentences. If a tool returns an error, say what is missing."
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    used: list[dict] = []
    for _ in range(4):
        msg = llm.chat(messages, tools=tools.openai_tools())
        calls = msg.get("tool_calls") or []
        if not calls:
            if not used:
                raise llm.LLMUnavailable("model answered without using data")  # don't trust ungrounded answers
            return {"answer": (msg.get("content") or "").strip(), "engine": "llm", "data": used[-1]["result"], "tools_used": [u["tool"] for u in used]}
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}") if isinstance(fn.get("arguments"), str) else (fn.get("arguments") or {})
            except ValueError:
                args = {}
            result = tools.call(fn.get("name", ""), args)
            result.pop("_raw", None)
            used.append({"tool": fn.get("name"), "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "name": fn.get("name", ""), "content": json.dumps(result, ensure_ascii=False)})
    raise llm.LLMUnavailable("too many tool rounds")
