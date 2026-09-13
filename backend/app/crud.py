from .database import get_db
from typing import List
from datetime import datetime


async def create_transaction(doc: dict) -> dict:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO transactions (title, amount, category, notes, date, kind, payment_method, merchant, recurring) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (doc["title"], doc["amount"], doc.get("category"), doc.get("notes"), doc["date"].isoformat(), doc.get("kind", "expense"), doc.get("payment_method"), doc.get("merchant"), int(doc.get("recurring", False))),
    )
    db.commit()
    created = {**doc, "id": str(cursor.lastrowid)}
    db.close()
    return created


async def list_transactions(limit: int = 10000) -> List[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM transactions ORDER BY date DESC LIMIT ?", (limit,)).fetchall()
    items = [dict(row) for row in rows]
    for item in items:
        item["id"] = str(item.pop("id"))
    db.close()
    return items


async def get_transaction(txn_id: str) -> dict:
    db = get_db()
    row = db.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
    doc = dict(row) if row else None
    if doc:
        doc["id"] = str(doc.pop("id"))
    db.close()
    return doc


async def delete_transaction(txn_id: str) -> bool:
    db = get_db()
    result = db.execute("DELETE FROM transactions WHERE id = ?", (txn_id,))
    db.commit()
    db.close()
    return result.rowcount == 1

async def update_simple(table: str, record_id: str, fields: dict) -> dict | None:
    db = get_db()
    allowed = {
        "accounts": {"name", "account_type", "institution", "opening_balance"},
        "budgets": {"name", "category", "amount", "period"},
        "goals": {"name", "target_amount", "current_amount", "target_date"},
        "bills": {"name", "amount", "due_date", "frequency", "status"},
    }[table]
    values = {key: value for key, value in fields.items() if key in allowed and value is not None}
    assignments = ", ".join(f"{key} = ?" for key in values)
    result = db.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*values.values(), record_id))
    db.commit()
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    db.close()
    if result.rowcount == 0 or not row:
        return None
    updated = dict(row)
    updated["id"] = str(updated.pop("id"))
    return updated


async def delete_simple(table: str, record_id: str) -> bool:
    db = get_db()
    result = db.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
    db.commit()
    db.close()
    return result.rowcount == 1


async def update_transaction(txn_id: str, doc: dict) -> dict | None:
    db = get_db()
    fields = {key: value for key, value in doc.items() if key in {"title", "amount", "category", "notes", "date", "kind", "payment_method", "merchant", "recurring"} and value is not None}
    if "date" in fields and hasattr(fields["date"], "isoformat"):
        fields["date"] = fields["date"].isoformat()
    if "recurring" in fields:
        fields["recurring"] = int(fields["recurring"])
    assignments = ", ".join(f"{key} = ?" for key in fields)
    result = db.execute(f"UPDATE transactions SET {assignments} WHERE id = ?", (*fields.values(), txn_id))
    db.commit()
    row = db.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
    db.close()
    if result.rowcount == 0 or not row:
        return None
    updated = dict(row)
    updated["id"] = str(updated.pop("id"))
    updated["recurring"] = bool(updated["recurring"])
    return updated


def _create_simple(table: str, fields: dict) -> dict:
    db = get_db()
    values = {**fields, "created_at": datetime.utcnow().isoformat()}
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    cursor = db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))
    db.commit()
    result = {"id": str(cursor.lastrowid), **values}
    db.close()
    return result


def _list_simple(table: str) -> List[dict]:
    db = get_db()
    rows = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id DESC").fetchall()]
    for row in rows:
        row["id"] = str(row["id"])
    db.close()
    return rows


async def create_account(data: dict) -> dict:
    return _create_simple("accounts", data)


async def list_accounts() -> List[dict]:
    return _list_simple("accounts")


async def create_budget(data: dict) -> dict:
    return _create_simple("budgets", data)


async def list_budgets() -> List[dict]:
    return _list_simple("budgets")


async def create_goal(data: dict) -> dict:
    return _create_simple("goals", data)


async def list_goals() -> List[dict]:
    return _list_simple("goals")


async def create_bill(data: dict) -> dict:
    return _create_simple("bills", data)


async def list_bills() -> List[dict]:
    return _list_simple("bills")


async def create_batch_transactions(items: List[dict]) -> dict:
    db = get_db()
    existing = set()
    rows = db.execute("SELECT title, amount, substr(date, 1, 10) as day FROM transactions").fetchall()
    for row in rows:
        existing.add((row["title"].strip().lower(), round(float(row["amount"]), 2), row["day"]))

    created_ids = []
    skipped_count = 0
    for item in items:
        title = item["title"].strip()
        amount = round(float(item["amount"]), 2)
        date_str = item.get("date")
        if isinstance(date_str, datetime):
            date_str = date_str.isoformat()
        elif not date_str:
            date_str = datetime.utcnow().isoformat()
        day_str = str(date_str)[:10]

        key = (title.lower(), amount, day_str)
        if key in existing:
            skipped_count += 1
            continue

        cursor = db.execute(
            "INSERT INTO transactions (title, amount, category, notes, date, kind, payment_method, merchant, recurring) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                amount,
                item.get("category"),
                item.get("notes"),
                date_str,
                item.get("kind", "expense"),
                item.get("payment_method"),
                item.get("merchant"),
                int(item.get("recurring", False)),
            ),
        )
        existing.add(key)
        created_ids.append(str(cursor.lastrowid))

    db.commit()
    db.close()
    return {
        "created_count": len(created_ids),
        "skipped_count": skipped_count,
        "created_ids": created_ids,
    }


async def get_advanced_analytics() -> dict:
    db = get_db()
    rows = [dict(row) for row in db.execute("SELECT * FROM transactions ORDER BY date DESC").fetchall()]
    budgets = [dict(row) for row in db.execute("SELECT * FROM budgets").fetchall()]
    goals = [dict(row) for row in db.execute("SELECT * FROM goals").fetchall()]
    bills = [dict(row) for row in db.execute("SELECT * FROM bills").fetchall()]
    db.close()

    total_expense = sum(r["amount"] for r in rows if (r.get("kind") or "expense") == "expense")
    total_income = sum(r["amount"] for r in rows if r.get("kind") == "income")
    total_investment = sum(r["amount"] for r in rows if r.get("kind") == "investment")

    # 1. Payment Methods Breakdown (for expenses)
    methods: dict[str, float] = {}
    for r in rows:
        if (r.get("kind") or "expense") == "expense":
            m = r.get("payment_method") or "UPI"
            methods[m] = methods.get(m, 0.0) + float(r["amount"])

    payment_method_breakdown = [
        {"method": m, "amount": round(amt, 2), "percentage": round((amt / total_expense * 100), 1) if total_expense else 0}
        for m, amt in sorted(methods.items(), key=lambda x: x[1], reverse=True)
    ]

    # 2. Top Merchants (for expenses)
    merchants: dict[str, dict] = {}
    for r in rows:
        if (r.get("kind") or "expense") == "expense":
            name = r.get("merchant") or r.get("title")
            if name:
                name = name.strip()
                if name not in merchants:
                    merchants[name] = {"name": name, "amount": 0.0, "count": 0, "category": r.get("category")}
                merchants[name]["amount"] += float(r["amount"])
                merchants[name]["count"] += 1

    top_merchants = sorted(merchants.values(), key=lambda x: x["amount"], reverse=True)[:8]

    # 3. Daily Burn Rate & Velocity (estimated across recorded days or 30 days)
    now = datetime.utcnow()
    last_30_days_expense = 0.0
    for r in rows:
        if (r.get("kind") or "expense") == "expense":
            try:
                dt = datetime.fromisoformat(str(r.get("date")).replace("Z", "+00:00").split("+")[0])
                if (now - dt).days <= 30:
                    last_30_days_expense += float(r["amount"])
            except Exception:
                pass
    daily_burn_rate = round(last_30_days_expense / 30, 2) if last_30_days_expense else round(total_expense / max(len(rows), 1), 2)

    # 4. Financial Health Score (0 - 100)
    savings_rate = ((total_income - total_expense - total_investment) / total_income * 100) if total_income else 0
    health_score = 50
    if savings_rate >= 40:
        health_score += 35
    elif savings_rate >= 20:
        health_score += 25
    elif savings_rate >= 0:
        health_score += 10
    else:
        health_score -= 20

    # Overdue bills penalty
    overdue_bills = [b for b in bills if b.get("status") != "paid" and str(b.get("due_date")) < now.strftime("%Y-%m-%d")]
    if not overdue_bills:
        health_score += 10
    else:
        health_score -= len(overdue_bills) * 8

    # Goals active bonus
    if goals:
        health_score += 5

    health_score = max(5, min(100, health_score))

    return {
        "payment_methods": payment_method_breakdown,
        "top_merchants": top_merchants,
        "daily_burn_rate": daily_burn_rate,
        "last_30_days_expense": round(last_30_days_expense, 2),
        "financial_health_score": health_score,
        "total_expense": round(total_expense, 2),
        "total_income": round(total_income, 2),
        "total_investment": round(total_investment, 2),
        "transaction_count": len(rows),
    }

