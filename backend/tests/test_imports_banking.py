"""Statement import pipeline and bank sync (sandbox provider + demo isolation)."""

import io

from openpyxl import Workbook

from .conftest import make_account

HDFC_CSV = """HDFC BANK Ltd. Statement of account
Account No : XXXXXXXX1234

Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance
01/09/26,NEFT CR-PAYROLL ACME CORP SALARY SEP,N12345,01/09/26,,"85,000.00","1,12,400.00"
03/09/26,UPI/425167812/SWIGGY/swiggy@icici/Food,425167812,03/09/26,340.00,,"1,12,060.00"
03/09/26,UPI/425167813/SWIGGY/swiggy@icici/Food,425167813,03/09/26,340.00,,"1,11,720.00"
05/09/26,ACH D- ZERODHA MUTUAL FUND SIP,ACH991,05/09/26,"10,000.00",,"1,01,720.00"
07/09/26,UPI/429999999/AMAZON REFUND/REVERSAL,429999999,07/09/26,,499.00,"1,02,219.00"
bad-date,Broken row,,,,12.00,
"""

OFX = b"""OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260910120000<TRNAMT>-649.00<FITID>FIT001<NAME>NETFLIX.COM</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260911<TRNAMT>1200.50<FITID>FIT002<NAME>INTEREST CREDIT</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""


def upload(api, filename, content, account_id=None):
    data = {"account_id": str(account_id)} if account_id else {}
    return api.post("/api/imports", files={"file": (filename, content, "application/octet-stream")}, data=data)


def test_csv_import_preview_map_validate_commit_and_dedupe(api):
    acc = make_account(api, opening="27400")
    job = upload(api, "hdfc.csv", HDFC_CSV.encode())
    assert job["bank_detected"] == "HDFC Bank" and job["status"] == "preview"
    assert job["mapping"]["sign"] == "debit_credit"
    job = api.post(f"/api/imports/{job['id']}/validate", json={"account_id": acc["id"], "mapping": job["mapping"]})
    assert job["counts"] == {"ok": 5, "duplicates": 0, "errors": 1, "imported": 0, "skipped": 0}
    rows = {r["row"]: r for r in job["rows"]}
    assert rows[0]["type"] == "income" and rows[0]["amount"] == "85000.00"
    assert rows[1]["merchant"] == "Swiggy" and rows[1]["direction"] == "out"
    assert rows[3]["type"] == "investment" and rows[4]["type"] == "refund"

    result = api.post(f"/api/imports/{job['id']}/commit", json={})
    assert (result["imported"], result["duplicates_skipped"], result["errors"]) == (5, 0, 1)
    balance = next(a for a in api.get("/api/accounts") if a["id"] == acc["id"])["balance_minor"]
    assert balance == 10_221_900  # 1,02,219.00 – matches the statement's closing balance

    # Re-importing the same file: every row (including the two identical Swiggy orders) is a duplicate.
    again = upload(api, "hdfc.csv", HDFC_CSV.encode(), acc["id"])
    assert again["counts"]["duplicates"] == 5 and again["counts"]["ok"] == 0
    assert api.post(f"/api/imports/{again['id']}/commit", json={})["imported"] == 0

    # Undo removes exactly what the first import created.
    assert api.post(f"/api/imports/{job['id']}/undo")["removed"] == 5


def test_xlsx_and_ofx_imports(api):
    acc = make_account(api)
    wb = Workbook()
    ws = wb.active
    ws.append(["Transaction Date", "Description", "Amount", "Dr/Cr"])
    ws.append(["2026-09-01", "Rent September", 25000, "DR"])
    ws.append(["2026-09-02", "Cashback", 50.5, "CR"])
    buf = io.BytesIO()
    wb.save(buf)
    job = upload(api, "statement.xlsx", buf.getvalue(), acc["id"])
    assert job["file_format"] == "xlsx" and job["counts"]["ok"] == 2
    assert api.post(f"/api/imports/{job['id']}/commit", json={})["imported"] == 2

    ofx = upload(api, "bank.ofx", OFX, acc["id"])
    assert ofx["file_format"] == "ofx" and ofx["counts"]["ok"] == 2
    api.post(f"/api/imports/{ofx['id']}/commit", json={})
    again = upload(api, "bank.ofx", OFX, acc["id"])
    assert again["counts"]["duplicates"] == 2  # matched by FITID


def test_import_rejects_unsupported_files(api):
    api.post("/api/imports", files={"file": ("notes.docx", b"hello", "application/octet-stream")}, expected=422)


def test_sandbox_bank_is_refused_for_real_users(api):
    providers = {p["key"]: p for p in api.get("/api/banks/providers")}
    assert providers["demo"]["available"] is False and "Demo mode" in providers["demo"]["reason"]
    assert providers["setu_aa"]["available"] is False
    api.post("/api/banks/connections", json={"provider": "demo", "institution_id": "sandbox-bank"}, expected=422)


def test_demo_mode_is_isolated_and_sync_dedupes(api, anon):
    real_before = api.get("/api/transactions")["total"]
    demo = anon.post("/api/auth/demo")
    anon.csrf = demo["csrf_token"]
    assert demo["user"]["is_demo"] is True
    conns = anon.get("/api/banks/connections")
    assert len(conns) == 1 and conns[0]["status"] == "active"
    first = anon.get("/api/banks/sync-logs")[0]
    assert first["status"] == "success" and first["imported"] > 50

    second = anon.post(f"/api/banks/connections/{conns[0]['id']}/sync")["sync"]
    assert second["status"] == "success" and second["imported"] == 0 and second["duplicates"] > 0

    dash = anon.get("/api/dashboard")
    assert dash["totals"]["income"] > 0 and dash["net_worth"]["liabilities"] > 0
    assert anon.get("/api/alerts/events")  # the real engine fired on sample data
    # The real user's workspace is untouched.
    assert api.get("/api/transactions")["total"] == real_before


def test_disconnect_keeps_history_and_sync_failure_alerts(anon):
    anon.csrf = anon.post("/api/auth/demo")["csrf_token"]
    conn = anon.get("/api/banks/connections")[0]
    count = anon.get("/api/transactions")["total"]
    anon.delete(f"/api/banks/connections/{conn['id']}")
    assert anon.get("/api/transactions")["total"] == count
    failed = anon.post(f"/api/banks/connections/{conn['id']}/sync")["sync"]
    assert failed["status"] == "failed" and "disconnected" in failed["message"]
    assert any(e["metric"] == "sync_failed" for e in anon.get("/api/alerts/events"))


def test_sms_webhook_requires_token(api, anon):
    acc = make_account(api)
    text = "Dear HDFC Bank User, INR 340.00 debited from a/c **1234 to SWIGGY on 13-09-26 via UPI txn 42516781290. Bal: INR 34,210.00"
    anon.post("/api/sms/webhook", json={"text": text}, expected=401)
    token = api.post("/api/settings/sms-webhook-token")["token"]
    api.patch("/api/settings", json={"default_account_id": acc["id"]})
    created = anon.post("/api/sms/webhook", json={"text": text}, headers={"Authorization": f"Bearer {token}"})
    assert created["created"] is True
    assert anon.post("/api/sms/webhook", json={"text": text}, headers={"Authorization": f"Bearer {token}"})["created"] is False
    txn = api.get(f"/api/transactions/{created['transaction_id']}")
    assert (txn["amount_minor"], txn["source"], txn["reviewed"], txn["category"]) == (34_000, "sms", False, "Food delivery")
