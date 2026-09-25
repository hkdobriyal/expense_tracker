import csv
import io
import re
import datetime
from typing import Dict, Any, List, Optional, Tuple
from pypdf import PdfReader


def clean_narration_to_transaction(
    narration: str,
    amount: float,
    txn_type: str,
    raw_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Parses an Indian retail bank narration string into a structured Ledgerly transaction.
    """
    clean_narration = narration.strip().replace("\n", " ")
    upper_narr = clean_narration.upper()
    
    # Defaults
    kind = "income" if txn_type.upper() in ["CREDIT", "CR", "INCOME"] else "expense"
    category = "Other"
    payment_method = "Bank transfer"
    merchant = ""
    title = clean_narration[:45]
    recurring = False

    # 1. UPI narrations: UPI/CR/42516781290/SWIGGY/HDFCBK/ or UPI/42516781290/ZEPTO/
    if "UPI" in upper_narr:
        payment_method = "UPI"
        upi_match = re.search(r'UPI/(?:(?:CR|DR)/)?(?:\d+/)?([^/]+)', clean_narration, re.IGNORECASE)
        if upi_match:
            merchant = upi_match.group(1).strip()
            title = f"{merchant.title()} via UPI"
        else:
            title = "UPI Payment"

    # 2. Point of Sale (POS) Card Transactions
    elif "POS " in upper_narr or "ECOM" in upper_narr:
        payment_method = "Card"
        pos_match = re.search(r'(?:POS|ECOM)\s*(?:\d+\s+)?([A-Za-z0-9\s&]+?)(?:\s+(?:MUMBAI|BANGALORE|BLR|DELHI|GURGAON|HYD|CHENNAI|PUNE|IND))?', clean_narration, re.IGNORECASE)
        if pos_match:
            merchant = pos_match.group(1).strip()
            title = f"{merchant.title()}"
        else:
            title = "Card Payment"

    # 3. Salary & Payroll credits
    elif "SALARY" in upper_narr or "PAYROLL" in upper_narr:
        kind = "income"
        category = "Salary"
        payment_method = "Bank transfer"
        title = "Monthly Salary Credit"
        recurring = True

    # 4. Mutual Funds, SIP, Investments
    elif any(k in upper_narr for k in ["ZERODHA", "GROWW", "MUTUAL FUND", "SIP", "NIFTY", "KFINTECH", "CAMS", "EQUITY"]):
        kind = "investment"
        category = "Investments"
        payment_method = "Bank transfer"
        title = "Investment / Mutual Fund SIP"
        merchant = "Zerodha/Groww" if "ZERODHA" in upper_narr or "GROWW" in upper_narr else "AMC"
        recurring = True

    # 5. Utilities & Bills (BESCOM, TNEB, TATA POWER, AIRTEL, JIO)
    elif any(k in upper_narr for k in ["BESCOM", "ELECTRICITY", "BILLDESK", "BBPS", "AIRTEL", "JIO", "WATER"]):
        category = "Utilities"
        payment_method = "Netbanking"
        if "BESCOM" in upper_narr:
            title = "BESCOM Electricity Bill"
            merchant = "BESCOM"
        elif "AIRTEL" in upper_narr:
            title = "Airtel Broadband/Mobile"
            merchant = "Airtel"
        else:
            title = "Utility Bill Payment"
        recurring = True

    # 6. Food Delivery
    elif any(k in upper_narr for k in ["SWIGGY", "ZOMATO", "MCDONALD", "DOMINOS", "STARBUCKS"]):
        category = "Food & Dining"
        merchant = "Swiggy" if "SWIGGY" in upper_narr else "Zomato" if "ZOMATO" in upper_narr else "Restaurant"
        title = f"{merchant} Order"

    # 7. Quick Commerce & Groceries
    elif any(k in upper_narr for k in ["ZEPTO", "BLINKIT", "INSTAMART", "BIGBASKET", "DMART", "NATURES BASKET"]):
        category = "Groceries"
        merchant = "Zepto" if "ZEPTO" in upper_narr else "Blinkit" if "BLINKIT" in upper_narr else "Instamart" if "INSTAMART" in upper_narr else "Groceries"
        title = f"{merchant} Groceries"

    # 8. Cabs & Transit
    elif any(k in upper_narr for k in ["UBER", "OLA", "RAPIDO", "IRCTC", "METRO"]):
        category = "Transit"
        merchant = "Uber" if "UBER" in upper_narr else "Ola" if "OLA" in upper_narr else "IRCTC" if "IRCTC" in upper_narr else "Transit"
        title = f"{merchant} Ride/Ticket"

    # 9. Subscriptions
    elif any(k in upper_narr for k in ["NETFLIX", "SPOTIFY", "PRIME", "YOUTUBE", "APPLE.COM", "HOTSTAR"]):
        category = "Entertainment"
        payment_method = "Card"
        merchant = "Netflix" if "NETFLIX" in upper_narr else "Spotify" if "SPOTIFY" in upper_narr else "Subscription"
        title = f"{merchant} Subscription"
        recurring = True

    # Parse date or use now
    date_str = datetime.datetime.utcnow().isoformat()
    if raw_date:
        try:
            # Try formats: DD-MM-YYYY, DD/MM/YYYY, YYYY-MM-DD
            clean_date = raw_date.strip().split(" ")[0]
            for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d/%b/%Y", "%d-%m-%y", "%d/%m/%y"):
                try:
                    parsed_dt = datetime.datetime.strptime(clean_date, fmt)
                    date_str = parsed_dt.isoformat()
                    break
                except ValueError:
                    continue
        except Exception:
            pass

    return {
        "title": title,
        "amount": round(abs(amount), 2),
        "kind": kind,
        "category": category,
        "payment_method": payment_method,
        "merchant": merchant,
        "date": date_str,
        "notes": clean_narration,
        "recurring": recurring,
    }


def parse_csv_statement(file_bytes: bytes) -> Tuple[List[Dict[str, Any]], str]:
    """
    Parses official CSV statements from HDFC, SBI, ICICI, Axis, Kotak.
    """
    text = file_bytes.decode("utf-8", errors="replace")
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return [], "Unknown"

    bank = "Bank"
    lower_first_few = "\n".join(lines[:10]).lower()
    if "hdfc" in lower_first_few:
        bank = "HDFC Bank"
    elif "state bank" in lower_first_few or "sbi" in lower_first_few:
        bank = "State Bank of India"
    elif "icici" in lower_first_few:
        bank = "ICICI Bank"
    elif "axis" in lower_first_few:
        bank = "Axis Bank"
    elif "kotak" in lower_first_few:
        bank = "Kotak Mahindra Bank"

    reader = csv.reader(lines)
    rows = list(reader)
    if not rows:
        return [], bank

    # Find the header row (contains date, narration/description/particulars, amount or debit/credit)
    header_idx = -1
    for idx, row in enumerate(rows[:20]):
        row_str = " ".join(row).lower()
        if ("date" in row_str or "txn" in row_str) and ("narration" in row_str or "particular" in row_str or "description" in row_str or "remark" in row_str):
            header_idx = idx
            break

    if header_idx == -1:
        # Fallback: assume first row is header
        header_idx = 0

    headers = [h.strip().lower() for h in rows[header_idx]]
    date_col = next((i for i, h in enumerate(headers) if "date" in h or "txn date" in h), 0)
    narr_col = next((i for i, h in enumerate(headers) if any(k in h for k in ["narration", "particular", "desc", "remark"])), 1)
    debit_col = next((i for i, h in enumerate(headers) if "debit" in h or "withdrawal" in h or "dr" in h), -1)
    credit_col = next((i for i, h in enumerate(headers) if "credit" in h or "deposit" in h or "cr" in h), -1)
    amount_col = next((i for i, h in enumerate(headers) if "amount" in h or "txn amt" in h or "inr" in h), -1)
    type_col = next((i for i, h in enumerate(headers) if "type" in h or "dr/cr" in h or "cr/dr" in h), -1)

    parsed_txns = []
    for row in rows[header_idx + 1:]:
        if len(row) <= max(date_col, narr_col):
            continue

        raw_date = row[date_col].strip()
        narration = row[narr_col].strip()
        if not narration or not raw_date:
            continue

        amount = 0.0
        txn_type = "DEBIT"

        # Separate Debit / Credit columns
        if debit_col >= 0 and credit_col >= 0:
            raw_deb = row[debit_col].replace(",", "").strip() if len(row) > debit_col else ""
            raw_cred = row[credit_col].replace(",", "").strip() if len(row) > credit_col else ""
            deb_val = float(re.sub(r'[^0-9.]', '', raw_deb)) if re.search(r'\d', raw_deb) else 0.0
            cred_val = float(re.sub(r'[^0-9.]', '', raw_cred)) if re.search(r'\d', raw_cred) else 0.0

            if cred_val > 0:
                amount = cred_val
                txn_type = "CREDIT"
            elif deb_val > 0:
                amount = deb_val
                txn_type = "DEBIT"
        elif amount_col >= 0:
            raw_amt = row[amount_col].replace(",", "").strip()
            val = float(re.sub(r'[^0-9.]', '', raw_amt)) if re.search(r'\d', raw_amt) else 0.0
            if type_col >= 0 and len(row) > type_col:
                raw_type = row[type_col].upper().strip()
                txn_type = "CREDIT" if "CR" in raw_type or "CREDIT" in raw_type or raw_amt.startswith("+") else "DEBIT"
            else:
                txn_type = "DEBIT" if raw_amt.startswith("-") or "DR" in raw_amt.upper() else "EXPENSE"
            amount = val

        if amount > 0:
            parsed = clean_narration_to_transaction(narration, amount, txn_type, raw_date)
            parsed_txns.append(parsed)

    return parsed_txns, bank


def parse_pdf_statement(file_bytes: bytes, password: Optional[str] = None) -> Tuple[List[Dict[str, Any]], str]:
    """
    Parses official password-protected or unprotected PDF statements using pypdf.
    """
    stream = io.BytesIO(file_bytes)
    reader = PdfReader(stream)

    if reader.is_encrypted:
        if not password:
            raise ValueError("This bank statement PDF is encrypted. Please provide the statement password (e.g. PAN + DOB / Name + DOB).")
        decrypt_success = reader.decrypt(password)
        if not decrypt_success:
            raise ValueError("Incorrect statement password. Bank PDFs usually require PAN uppercase + Date of Birth (e.g. ABCDE1234F01011995).")

    full_text = ""
    for page in reader.pages:
        full_text += (page.extract_text() or "") + "\n"

    bank = "Bank"
    lower_text = full_text[:2000].lower()
    if "hdfc bank" in lower_text:
        bank = "HDFC Bank"
    elif "state bank of india" in lower_text or "sbi" in lower_text:
        bank = "State Bank of India"
    elif "icici bank" in lower_text:
        bank = "ICICI Bank"
    elif "axis bank" in lower_text:
        bank = "Axis Bank"
    elif "kotak" in lower_text:
        bank = "Kotak Mahindra Bank"

    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    parsed_txns = []

    # Regex to identify standard Indian bank transaction lines:
    # Date (DD/MM/YYYY or DD-MM-YYYY) followed by narration and numbers (Amount, Balance)
    txn_regex = re.compile(r'(\d{2}[/-]\d{2}[/-]\d{2,4})\s+(.+?)\s+([0-9,]+\.\d{2})\s*(CR|DR)?\s+([0-9,]+\.\d{2})?', re.IGNORECASE)

    for line in lines:
        match = txn_regex.search(line)
        if match:
            raw_date = match.group(1)
            narration = match.group(2)
            raw_amt = match.group(3).replace(",", "")
            raw_cr_dr = match.group(4) or ""
            
            try:
                amt = float(raw_amt)
            except ValueError:
                continue

            txn_type = "CREDIT" if raw_cr_dr.upper() == "CR" or "CREDIT" in narration.upper() else "DEBIT"
            if amt > 0:
                parsed = clean_narration_to_transaction(narration, amt, txn_type, raw_date)
                parsed_txns.append(parsed)

    return parsed_txns, bank
