import re
from datetime import datetime
from typing import Optional, Dict, Any

# Common merchant to category mappings in India
MERCHANT_CATEGORY_MAP = {
    # Food & Dining
    "swiggy": "Eating out",
    "zomato": "Eating out",
    "mcdonald": "Eating out",
    "domino": "Eating out",
    "starbucks": "Eating out",
    "chai point": "Eating out",
    "kfc": "Eating out",
    "subway": "Eating out",
    "eatsure": "Eating out",
    "burger king": "Eating out",
    # Groceries
    "zepto": "Groceries",
    "blinkit": "Groceries",
    "instamart": "Groceries",
    "bigbasket": "Groceries",
    "bb daily": "Groceries",
    "dmart": "Groceries",
    "reliance fresh": "Groceries",
    "nature basket": "Groceries",
    "country delight": "Groceries",
    # Transport
    "uber": "Transport",
    "ola": "Transport",
    "rapido": "Transport",
    "irctc": "Transport",
    "makemytrip": "Transport",
    "indigo": "Transport",
    "air india": "Transport",
    "metro": "Transport",
    "fastag": "Transport",
    "petrol": "Transport",
    "fuel": "Transport",
    "hpcl": "Transport",
    "iocl": "Transport",
    "bpcl": "Transport",
    # Shopping
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "myntra": "Shopping",
    "ajio": "Shopping",
    "nykaa": "Shopping",
    "tata cliq": "Shopping",
    "croma": "Shopping",
    "reliance digital": "Shopping",
    "zara": "Shopping",
    "h&m": "Shopping",
    "uniqlo": "Shopping",
    # Subscriptions & Entertainment
    "netflix": "Subscriptions",
    "spotify": "Subscriptions",
    "prime": "Subscriptions",
    "hotstar": "Subscriptions",
    "youtube": "Subscriptions",
    "apple": "Subscriptions",
    "google": "Subscriptions",
    "bookmyshow": "Subscriptions",
    "pvr": "Subscriptions",
    "inox": "Subscriptions",
    # Health
    "apollo": "Health",
    "pharmeasy": "Health",
    "1mg": "Health",
    "medplus": "Health",
    "netmeds": "Health",
    "cult.fit": "Health",
    "practo": "Health",
    "max healthcare": "Health",
    # Investments
    "zerodha": "Investments",
    "groww": "Investments",
    "coin": "Investments",
    "kuvera": "Investments",
    "upstox": "Investments",
    "angelone": "Investments",
    "indmoney": "Investments",
    "mfcentral": "Investments",
    "uti mf": "Investments",
    "sbi mutual": "Investments",
    "hdfc mutual": "Investments",
    "icici prudential": "Investments",
    "nippon": "Investments",
    "mirae": "Investments",
    # Utilities & Bills
    "bescom": "Rent & utilities",
    "tneb": "Rent & utilities",
    "mahadiscom": "Rent & utilities",
    "airtel": "Rent & utilities",
    "jio": "Rent & utilities",
    "vi": "Rent & utilities",
    "broadband": "Rent & utilities",
    "electricity": "Rent & utilities",
    "water": "Rent & utilities",
    "gas": "Rent & utilities",
    "igl": "Rent & utilities",
}

def infer_category(text: str, merchant: Optional[str] = None) -> str:
    haystack = f"{merchant or ''} {text}".lower()
    for keyword, cat in MERCHANT_CATEGORY_MAP.items():
        if keyword in haystack:
            return cat
    
    if any(w in haystack for w in ["salary", "payroll", "dividend", "interest credited", "bonus"]):
        return "Other"
    if any(w in haystack for w in ["rent", "maintenance", "society"]):
        return "Rent & utilities"
    if any(w in haystack for w in ["fee", "school", "college", "tuition", "course", "udemy"]):
        return "Education"
    if any(w in haystack for w in ["sip", "mutual fund", "stocks", "shares", "deposit", "nps"]):
        return "Investments"
    return "Other"


def parse_bank_sms(text: str) -> Optional[Dict[str, Any]]:
    """
    Parses transactional SMS from Indian banks and UPI applications.
    Supports HDFC, SBI, ICICI, Axis, Kotak, PNB, PhonePe, GPay, Paytm, CRED, etc.
    """
    if not text or not text.strip():
        return None

    cleaned = " ".join(text.split())
    lower_text = cleaned.lower()

    # 1. Determine Kind: expense, income, or investment
    kind = "expense"
    if any(w in lower_text for w in ["credited", "received", "deposited", "refund", "salary", "cashback"]):
        kind = "income"
    elif any(w in lower_text for w in ["sip", "invested", "mutual fund", "zerodha", "groww", "folio"]):
        kind = "investment"
    elif any(w in lower_text for w in ["debited", "spent", "paid", "sent", "withdrawn", "txn of", "purchase of"]):
        kind = "expense"
    else:
        # If no explicit keyword, check for negative/positive signs or default to expense
        kind = "expense"

    # 2. Extract Amount (Prioritize transaction amount over remaining balance)
    amount = 0.0
    # Strip out balance strings first so they are never confused with transaction amounts
    text_without_bal = re.sub(
        r'(?:avl\s*bal|clear\s*bal|avail\s*bal|bal|balance|avl\s*lmt|limit)\s*(?:is|:)?\s*(?:inr|rs\.?)?\s*[\d,]+(?:\.\d{1,2})?',
        ' ',
        cleaned,
        flags=re.IGNORECASE,
    )

    # First, look specifically for amount tied to debit/credit/spent/paid/transferred:
    amt_match = re.search(
        r'(?:debited\s*(?:by|with|for)?|credited\s*(?:by|with|for)?|spent|paid|sent|withdrawn|purchase\s+of|towards|inflow\s+of)\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d{1,2})?)',
        text_without_bal,
        re.IGNORECASE,
    )
    if not amt_match:
        amt_match = re.search(
            r'(?:rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)\s*(?:debited|credited|spent|paid|transferred|sent)',
            text_without_bal,
            re.IGNORECASE,
        )
    if not amt_match:
        amt_match = re.search(r'(?:rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)', text_without_bal, re.IGNORECASE)
    if not amt_match:
        amt_match = re.search(r'\b(?:debited|credited|paid|spent|sent|transfer)\s+(?:for\s+)?(?:rs\.?|inr)?\s*([\d,]+(?:\.\d{1,2})?)', text_without_bal, re.IGNORECASE)

    if amt_match:
        raw_amt = amt_match.group(1).replace(",", "")
        try:
            amount = float(raw_amt)
        except ValueError:
            amount = 0.0

    if amount <= 0:
        return None

    # 3. Detect Payment Method
    payment_method = "UPI"
    if "upi" in lower_text or "vpa" in lower_text or "@ok" in lower_text or "@icici" in lower_text or "@okhdfcbank" in lower_text or "@ybl" in lower_text:
        payment_method = "UPI"
    elif any(w in lower_text for w in ["credit card", "cc ending", "card ending", "card xx", "card 4321"]):
        payment_method = "Credit card"
    elif any(w in lower_text for w in ["debit card", "dc ending"]):
        payment_method = "Debit card"
    elif any(w in lower_text for w in ["net banking", "neft", "rtgs", "imps"]):
        payment_method = "Net banking"
    elif "auto-debit" in lower_text or "nach" in lower_text or "mandate" in lower_text:
        payment_method = "Auto-debit"

    # 4. Extract Merchant / Beneficiary
    merchant = None
    # Check known brands first for maximum accuracy
    for brand in sorted(MERCHANT_CATEGORY_MAP.keys(), key=len, reverse=True):
        if re.search(rf'\b{re.escape(brand)}\b', lower_text):
            merchant = brand.title()
            break

    if not merchant:
        m_match = re.search(
            r'(?:to|at|info:|trf to|beneficiary|towards|spent on|paid to|for)\s+([A-Za-z0-9\s\.\&\*\-]+?)(?=\s+(?:on|via|ref|using|avail|bal|balance|avl|upi|dated|clear|\.|\,|$))',
            cleaned,
            re.IGNORECASE,
        )
        if m_match:
            candidate = m_match.group(1).strip()
            # Clean punctuation and stop words
            candidate = re.sub(r'[\.\,\;]+$', '', candidate).strip()
            if not re.search(r'^(a\/c|account|vpa|your|my|our)\b', candidate, re.IGNORECASE) and len(candidate) > 1:
                if "@" in candidate:
                    candidate = candidate.split("@")[0]
                # Strip trailing "clear", "bal"
                candidate = re.sub(r'\s+(?:clear|bal|balance|avl)$', '', candidate, flags=re.IGNORECASE).strip()
                if candidate:
                    merchant = candidate.title()

    # 5. Extract Bank / Account reference
    account_ref = None
    acct_match = re.search(r'(?:a\/c|acct|account|card)\s*(?:no\.?)?\s*[\*xX]*(\d{3,4})', cleaned, re.IGNORECASE)
    if acct_match:
        account_ref = f"A/C **{acct_match.group(1)}"

    # Detect institution name
    institution = None
    banks = ["HDFC", "SBI", "ICICI", "Axis", "Kotak", "PNB", "Canara", "IndusInd", "Paytm", "Federal", "Bank of Baroda", "Standard Chartered"]
    for b in banks:
        if b.lower() in lower_text:
            institution = b
            break

    # 6. Extract Reference / UPI Ref / UTR
    ref_match = re.search(r'(?:ref(?:\s*no\.?)?|rrn|utr|txn\s*id|upi\s*ref(?:\s*no)?)\s*[:\-\s]*([A-Za-z0-9]{6,16})', cleaned, re.IGNORECASE)
    ref_id = ref_match.group(1) if ref_match else None

    # 7. Extract or infer Category
    category = infer_category(cleaned, merchant)

    # 8. Title creation
    if merchant:
        title = f"{merchant}"
    else:
        if kind == "income":
            title = "Bank Deposit / Inflow"
        elif kind == "investment":
            title = "Investment Deposit"
        else:
            title = f"{category} Spend"

    # Notes creation
    note_parts = []
    if institution:
        note_parts.append(institution)
    if account_ref:
        note_parts.append(account_ref)
    if ref_id:
        note_parts.append(f"Ref: {ref_id}")
    notes = " · ".join(note_parts) if note_parts else "Auto-synced transaction"

    return {
        "title": title,
        "amount": amount,
        "kind": kind,
        "category": category,
        "payment_method": payment_method,
        "merchant": merchant,
        "notes": notes,
        "date": datetime.utcnow().isoformat(),
        "recurring": False,
        "institution": institution,
        "account_ref": account_ref,
        "ref_id": ref_id,
        "raw_text": cleaned,
    }
