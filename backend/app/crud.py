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


async def list_transactions(limit: int = 100) -> List[dict]:
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
