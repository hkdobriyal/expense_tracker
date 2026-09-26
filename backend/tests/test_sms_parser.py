"""The original SMS parser cases (from test_backend.py), now as assertions."""

import pytest

from app.services.sms_parser import parse_bank_sms

CASES = [
    ("Dear HDFC Bank User, INR 340.00 debited from a/c **1234 to SWIGGY on 13-09-26 via UPI txn 42516781290. Bal: INR 34,210.00", "expense", 340.0, "Swiggy", "UPI"),
    ("Dear SBI User, A/C ...5678 debited by 180.0 on 12Sep26 trf to Zepto UPI: 491823719283. Avl Bal: Rs 14,350", "expense", 180.0, "Zepto", "UPI"),
    ("Dear Customer, your ICICI Bank Acct XX901 is credited with INR 85,000.00 on 01-Sep-26 towards Salary. Clear Bal is INR 1,12,400.00", "income", 85000.0, None, None),
    ("Axis Bank: Rs 10000.00 debited from A/c no. XX345 on 10-09-26 towards Zerodha Broking. UPI Ref 41029384712", "investment", 10000.0, "Zerodha", "UPI"),
    ("Kotak Bank: Spent Rs. 1,499.00 on your Credit Card XX4321 at ZARA on 08-09-2026. Avl Lmt: Rs 1,45,000", "expense", 1499.0, "Zara", "Credit card"),
    ("Paid Rs. 1,850.00 to BESCOM Electricity on PhonePe. Txn ID: T26091312345678. Debited from Bank of Baroda a/c **8765", "expense", 1850.0, "Bescom", None),
    ("Alert: Rs 649 debited from your HDFC card **3322 for NETFLIX on 05-Sep-26. Auto-debit successful.", "expense", 649.0, "Netflix", None),
    ("Refund of Rs 499.00 credited to your a/c XX1234 from AMAZON. Ref 998877665544", "refund", 499.0, "Amazon", None),
]


@pytest.mark.parametrize("text,kind,amount,merchant,method", CASES)
def test_parses_indian_bank_sms(text, kind, amount, merchant, method):
    parsed = parse_bank_sms(text)
    assert parsed is not None
    assert parsed["kind"] == kind
    assert parsed["amount"] == amount  # the balance in the same SMS is never taken as the amount
    if merchant:
        assert parsed["merchant"] == merchant
    if method:
        assert parsed["payment_method"] == method


def test_rejects_non_transactional_text():
    assert parse_bank_sms("Your OTP is 123456. Do not share it.") is None
    assert parse_bank_sms("") is None
