from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from . import crud
from .schemas import (
    AccountCreate,
    BillCreate,
    BudgetCreate,
    GoalCreate,
    TransactionCreate,
    TransactionOut,
    BatchTransactionCreate,
    SMSParseRequest,
    SMSParseResponse,
    SyncWebhookPayload,
)
from .parser import parse_bank_sms
from .database import get_db
from datetime import datetime
from typing import Any, List
from fastapi.responses import StreamingResponse
import csv
import io
import json

app = FastAPI(title="Expense Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/dashboard/summary")
async def dashboard_summary():
    db = get_db()
    rows = [dict(row) for row in db.execute("SELECT amount, kind FROM transactions").fetchall()]
    bills = [dict(row) for row in db.execute("SELECT amount, due_date, status FROM bills ORDER BY due_date LIMIT 5").fetchall()]
    db.close()
    income = sum(row["amount"] for row in rows if row.get("kind") == "income")
    investments = sum(row["amount"] for row in rows if row.get("kind") == "investment")
    expenses = sum(row["amount"] for row in rows if (row.get("kind") or "expense") == "expense")
    return {"currency": "INR", "income": income, "expenses": expenses, "investments": investments, "savings": income - expenses - investments, "savings_rate": ((income - expenses - investments) / income * 100) if income else 0, "upcoming_bills": bills}


@app.post("/transactions", response_model=TransactionOut)
async def create_transaction(item: TransactionCreate):
    doc = item.model_dump()
    if not doc.get("date"):
        doc["date"] = datetime.utcnow()
    created = await crud.create_transaction(doc)
    return {"id": created["id"], **created}


@app.put("/transactions/{txn_id}", response_model=TransactionOut)
async def update_transaction(txn_id: str, item: TransactionCreate):
    updated = await crud.update_transaction(txn_id, item.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated


@app.get("/transactions", response_model=List[TransactionOut])
async def get_transactions():
    items = await crud.list_transactions()
    outs = []
    for it in items:
        outs.append({
            "id": it.get("id"),
            "title": it.get("title"),
            "amount": it.get("amount"),
            "category": it.get("category"),
            "notes": it.get("notes"),
            "date": it.get("date"),
            "kind": it.get("kind") or "expense",
            "payment_method": it.get("payment_method"),
            "merchant": it.get("merchant"),
            "recurring": bool(it.get("recurring")),
        })
    return outs


@app.get("/transactions/export.csv")
async def export_transactions():
    items = await crud.list_transactions(limit=10000)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "title", "amount_inr", "kind", "category", "payment_method", "merchant", "notes", "recurring"])
    for item in items:
        writer.writerow([item.get("date"), item.get("title"), item.get("amount"), item.get("kind") or "expense", item.get("category"), item.get("payment_method"), item.get("merchant"), item.get("notes"), bool(item.get("recurring"))])
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=ledgerly-transactions.csv"})


BACKUP_TABLES = ("transactions", "accounts", "budgets", "goals", "bills")
BACKUP_COLUMNS = {
    "transactions": ("id", "title", "amount", "category", "notes", "date", "kind", "payment_method", "merchant", "recurring"),
    "accounts": ("id", "name", "account_type", "institution", "opening_balance", "currency", "created_at"),
    "budgets": ("id", "name", "category", "amount", "period", "created_at"),
    "goals": ("id", "name", "target_amount", "current_amount", "target_date", "created_at"),
    "bills": ("id", "name", "amount", "due_date", "frequency", "status", "created_at"),
}


@app.get("/backup.json")
async def backup_json():
    db = get_db()
    payload = {}
    for table in BACKUP_TABLES:
        payload[table] = [dict(row) for row in db.execute(f"SELECT * FROM {table}").fetchall()]
    db.close()
    content = json.dumps({"version": 1, "exported_at": datetime.utcnow().isoformat(), "currency": "INR", "data": payload}, indent=2)
    return StreamingResponse(iter([content]), media_type="application/json", headers={"Content-Disposition": "attachment; filename=ledgerly-backup.json"})


@app.post("/backup/restore")
async def restore_backup(payload: dict[str, Any]):
    envelope = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(envelope, dict):
        raise HTTPException(status_code=400, detail="Invalid backup file")
    db = get_db()
    try:
        db.execute("BEGIN")
        for table in BACKUP_TABLES:
            rows = envelope.get(table) or []
            if not isinstance(rows, list):
                raise ValueError(f"Backup table {table} must be a list")
            db.execute(f"DELETE FROM {table}")
            allowed = BACKUP_COLUMNS[table]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                values = {key: row[key] for key in allowed if key in row}
                if not values:
                    continue
                columns = ", ".join(values.keys())
                placeholders = ", ".join("?" for _ in values)
                db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))
        db.commit()
        try:
            for table in BACKUP_TABLES:
                max_id = db.execute(f"SELECT MAX(id) FROM {table}").fetchone()[0]
                db.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
                if max_id:
                    db.execute("INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)", (table, max_id))
            db.commit()
        except Exception:
            pass
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not restore backup: {error}") from error
    finally:
        db.close()
    return {"restored": True}


@app.post("/accounts")
async def create_account(item: AccountCreate):
    return await crud.create_account(item.model_dump())


@app.put("/accounts/{record_id}")
async def update_account(record_id: str, item: AccountCreate):
    updated = await crud.update_simple("accounts", record_id, item.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return updated


@app.delete("/accounts/{record_id}")
async def delete_account(record_id: str):
    if not await crud.delete_simple("accounts", record_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"deleted": True}


@app.get("/accounts")
async def list_accounts():
    return await crud.list_accounts()


@app.post("/budgets")
async def create_budget(item: BudgetCreate):
    return await crud.create_budget(item.model_dump())


@app.put("/budgets/{record_id}")
async def update_budget(record_id: str, item: BudgetCreate):
    updated = await crud.update_simple("budgets", record_id, item.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Budget not found")
    return updated


@app.delete("/budgets/{record_id}")
async def delete_budget(record_id: str):
    if not await crud.delete_simple("budgets", record_id):
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"deleted": True}


@app.get("/budgets")
async def list_budgets():
    return await crud.list_budgets()


@app.post("/goals")
async def create_goal(item: GoalCreate):
    return await crud.create_goal(item.model_dump())


@app.put("/goals/{record_id}")
async def update_goal(record_id: str, item: GoalCreate):
    updated = await crud.update_simple("goals", record_id, item.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Goal not found")
    return updated


@app.delete("/goals/{record_id}")
async def delete_goal(record_id: str):
    if not await crud.delete_simple("goals", record_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"deleted": True}


@app.get("/goals")
async def list_goals():
    return await crud.list_goals()


@app.post("/bills")
async def create_bill(item: BillCreate):
    return await crud.create_bill(item.model_dump())


@app.put("/bills/{record_id}")
async def update_bill(record_id: str, item: BillCreate):
    updated = await crud.update_simple("bills", record_id, item.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Bill not found")
    return updated


@app.delete("/bills/{record_id}")
async def delete_bill(record_id: str):
    if not await crud.delete_simple("bills", record_id):
        raise HTTPException(status_code=404, detail="Bill not found")
    return {"deleted": True}


@app.get("/bills")
async def list_bills():
    return await crud.list_bills()


@app.get("/transactions/{txn_id}")
async def get_transaction(txn_id: str):
    doc = await crud.get_transaction(txn_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"id": doc.get("id"), "title": doc.get("title"), "amount": doc.get("amount"), "category": doc.get("category"), "notes": doc.get("notes"), "date": doc.get("date"), "kind": doc.get("kind") or "expense", "payment_method": doc.get("payment_method"), "merchant": doc.get("merchant"), "recurring": bool(doc.get("recurring"))}


@app.delete("/transactions/{txn_id}")
async def delete_transaction(txn_id: str):
    ok = await crud.delete_transaction(txn_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"deleted": True}


@app.post("/sync/parse-text", response_model=SMSParseResponse)
async def sync_parse_text(payload: SMSParseRequest):
    parsed = parse_bank_sms(payload.text)
    if not parsed:
        return SMSParseResponse(
            success=False,
            error="Could not extract a financial transaction from this text. Please ensure it includes an amount (e.g. INR 450) and transaction details.",
        )
    return SMSParseResponse(success=True, data=parsed)


@app.post("/sync/sms")
async def sync_sms_webhook(payload: SyncWebhookPayload):
    text = payload.text or ""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Empty text received")
    parsed = parse_bank_sms(text)
    if not parsed:
        raise HTTPException(status_code=422, detail="Text could not be parsed as a valid financial transaction")

    created = await crud.create_transaction({
        "title": parsed["title"],
        "amount": parsed["amount"],
        "category": parsed["category"],
        "notes": parsed["notes"],
        "date": datetime.utcnow(),
        "kind": parsed["kind"],
        "payment_method": parsed["payment_method"],
        "merchant": parsed["merchant"],
        "recurring": False,
    })
    return {"synced": True, "transaction": created}


@app.post("/transactions/batch")
async def create_transactions_batch(payload: BatchTransactionCreate):
    items = [item.model_dump() for item in payload.transactions]
    return await crud.create_batch_transactions(items)


@app.get("/analytics/advanced")
async def get_advanced_analytics():
    return await crud.get_advanced_analytics()

