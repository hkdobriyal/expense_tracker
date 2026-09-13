import sys
from app.parser import parse_bank_sms

test_messages = [
    # 1. HDFC UPI
    "Dear HDFC Bank User, INR 340.00 debited from a/c **1234 to SWIGGY on 13-09-26 via UPI txn 42516781290. Bal: INR 34,210.00",
    # 2. SBI Debit
    "Dear SBI User, A/C ...5678 debited by 180.0 on 12Sep26 trf to Zepto UPI: 491823719283. Avl Bal: Rs 14,350",
    # 3. ICICI Salary Inflow
    "Dear Customer, your ICICI Bank Acct XX901 is credited with INR 85,000.00 on 01-Sep-26 towards Salary. Clear Bal is INR 1,12,400.00",
    # 4. Axis Bank Investment / Zerodha
    "Axis Bank: Rs 10000.00 debited from A/c no. XX345 on 10-09-26 towards Zerodha Broking. UPI Ref 41029384712",
    # 5. Kotak Credit Card
    "Kotak Bank: Spent Rs. 1,499.00 on your Credit Card XX4321 at ZARA on 08-09-2026. Avl Lmt: Rs 1,45,000",
    # 6. PhonePe / Utility
    "Paid Rs. 1,850.00 to BESCOM Electricity on PhonePe. Txn ID: T26091312345678. Debited from Bank of Baroda a/c **8765",
    # 7. Netflix subscription
    "Alert: Rs 649 debited from your HDFC card **3322 for NETFLIX on 05-Sep-26. Auto-debit successful.",
]

print("=== TESTING INDIAN BANK & UPI SMS PARSER ===")
all_passed = True
for idx, msg in enumerate(test_messages, 1):
    result = parse_bank_sms(msg)
    if not result:
        print(f"FAILED on test {idx}: {msg}")
        all_passed = False
    else:
        print(f"[{idx}] PASS: {result['kind'].upper():10} | Rs. {result['amount']:<8} | {result['title']:<18} | Cat: {result['category']:<15} | Method: {result['payment_method']}")

if all_passed:
    print("\nALL 7 REALISTIC BANK/UPI TEST CASES PASSED SUCCESSFULLY!")
else:
    print("\nSome tests failed!")
    sys.exit(1)
