from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from . import crud
from .schemas import AccountCreate, BillCreate, BudgetCreate, GoalCreate, TransactionCreate, TransactionOut
from .database import get_db
from datetime import datetime
from typing import List
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


@app.get("/backup.json")
async def backup_json():
    db = get_db()
    payload = {}
    for table in ("transactions", "accounts", "budgets", "goals", "bills"):
        payload[table] = [dict(row) for row in db.execute(f"SELECT * FROM {table}").fetchall()]
    db.close()
    content = json.dumps({"version": 1, "exported_at": datetime.utcnow().isoformat(), "currency": "INR", "data": payload}, indent=2)
    return StreamingResponse(iter([content]), media_type="application/json", headers={"Content-Disposition": "attachment; filename=ledgerly-backup.json"})


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
