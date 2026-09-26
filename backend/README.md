# Ledgerly API

FastAPI + SQLAlchemy + Alembic. See the root README and `docs/`.

```powershell
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000   # API, docs at /api/docs
.\.venv\Scripts\python -m app.worker                                 # background worker
.\.venv\Scripts\python -m pytest -q                                   # tests
```
