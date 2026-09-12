# Expense Tracker — Backend

Run locally (assuming Python 3.10+):

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The app uses a local SQLite database at `backend/expense_tracker.sqlite3`, so no database installation is required.

The API stores Indian personal finance fields including INR amounts, expense/income/investment type, Indian payment methods (UPI, cards, cash, net banking), merchant, recurring status, category, date, and notes. Existing databases are migrated automatically when the API starts.

CSV export is available at `GET /transactions/export.csv`.
