"""Entity extraction ("NER") for Indian bank narrations, SMS and statement lines.

Deterministic patterns rather than a statistical NER model: bank narrations
follow a handful of rigid formats (UPI/IMPS/NEFT/POS/ACH…), so explicit rules
are more accurate, explainable and need no training data. The entities feed
the merchant name, payment method and – through the ML model – the category.

Example:
    UPI/DR/425167812345/SWIGGY LIMITED/YESB/swiggy8@ybl/Food order
    → mode=UPI, direction=out, reference=425167812345, payee="Swiggy Limited",
      vpa=swiggy8@ybl, bank=YESB, note="Food order", merchant="Swiggy"
"""

from __future__ import annotations

import re

MODES = [
    ("UPI", r"\bUPI\b|@[a-z]{2,}\b|\bBHIM\b"),
    ("IMPS", r"\bIMPS\b|\bMMT\b"),
    ("NEFT", r"\bNEFT\b"),
    ("RTGS", r"\bRTGS\b"),
    ("Card", r"\bPOS\b|\bECOM\b|\bPCD\b|\bVPS\b|\bCARD\b|\bDEBIT CARD\b|\bCREDIT CARD\b|\bVISA\b|\bMASTERCARD\b|\bRUPAY\b"),
    ("ATM", r"\bATM\b|\bATW\b|\bNWD\b|\bCASH WDL\b|\bCASH WITHDRAWAL\b"),
    ("Auto-debit", r"\bACH\b|\bNACH\b|\bECS\b|\bSI[- ]|\bMANDATE\b|\bAUTOPAY\b|\bAUTO[- ]DEBIT\b"),
    ("Cheque", r"\bCHQ\b|\bCHEQUE\b|\bCLG\b|\bCLEARING\b"),
    ("Interest", r"\bINT\.?\s*(?:PD|CR|CREDIT|PAID)\b|\bINTEREST\b"),
    ("Charges", r"\bCHRG|\bCHARGES?\b|\bGST\b|\bFEE\b|\bAMC\b|\bSMS ALERT"),
    ("Cash deposit", r"\bCASH DEP|\bBY CASH\b|\bCDM\b"),
    ("Transfer", r"\bTRF\b|\bTRANSFER\b|\bFT\b|\bSELF\b"),
]
_MODE_RE = [(name, re.compile(pat, re.I)) for name, pat in MODES]

_VPA = re.compile(r"\b([a-z0-9][a-z0-9._-]{1,60}@[a-z][a-z0-9]{1,20})\b", re.I)
_IFSC = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
_REF12 = re.compile(r"(?<!\d)(\d{12})(?!\d)")
_UTR = re.compile(r"\b([A-Z]{4}[RHN0-9]\d{10,17}|[A-Z]{4}\d{12,18})\b")
_CARD = re.compile(r"(?:card|cc|dc)?\s*(?:no\.?|ending|xx+|\*{2,})\s*(\d{4})\b", re.I)
_CREDIT_WORDS = re.compile(r"\b(CR|CREDIT(?:ED)?|DEPOSIT(?:ED)?|RECEIVED|REFUND|REVERSAL|CASHBACK|SALARY|INT\.?\s*PD|INTEREST)\b|/CR/|\bBY\b", re.I)
_DEBIT_WORDS = re.compile(r"\b(DR|DEBIT(?:ED)?|PAID|PURCHASE|WITHDRAWAL|SPENT|SENT|TO)\b|/DR/", re.I)

_BANK_CODES = {
    "HDFC": "HDFC Bank", "SBIN": "SBI", "ICIC": "ICICI Bank", "UTIB": "Axis Bank", "KKBK": "Kotak", "YESB": "Yes Bank", "PUNB": "PNB",
    "BARB": "Bank of Baroda", "CNRB": "Canara Bank", "IDFB": "IDFC FIRST", "INDB": "IndusInd", "FDRL": "Federal Bank", "PYTM": "Paytm Payments Bank",
    "AIRP": "Airtel Payments Bank", "UBIN": "Union Bank", "IOBA": "Indian Overseas Bank", "BKID": "Bank of India", "CBIN": "Central Bank",
}
_PSP_HANDLES = {"ybl": "PhonePe", "ibl": "PhonePe", "axl": "PhonePe", "okhdfcbank": "Google Pay", "okicici": "Google Pay", "oksbi": "Google Pay",
                "okaxis": "Google Pay", "paytm": "Paytm", "ptyes": "Paytm", "ptaxis": "Paytm", "apl": "Amazon Pay", "yapl": "Amazon Pay",
                "upi": "BHIM", "freecharge": "Freecharge", "jupiteraxis": "Jupiter", "fam": "FamPay", "slc": "Slice", "kotak": "Kotak", "icici": "iMobile",
                "hdfcbank": "HDFC", "sbi": "YONO", "axisbank": "Axis"}

# Prefixes added by payment gateways/aggregators in front of the real merchant.
_GATEWAYS = re.compile(r"^(?:RAZORPAY|RZP|PAYU|PAYUBIZ|BILLDESK|CCAVENUE|CCAV|CASHFREE|PAYTM|PHONEPE|JUSPAY|EASEBUZZ|INSTAMOJO|PG|PAY)\s*[*\-_/ ]\s*", re.I)
_NOISE = re.compile(
    r"\b(PVT|PRIVATE|LTD|LIMITED|LLP|INDIA|IND|INTERNET|SERVICES?|TECHNOLOGIES|TECH|COMMERCE|RETAIL|ONLINE|PAYMENTS?|DIGITAL|ENTERPRISES?|CO|CORP|CORPORATION|"
    r"STORES?|MERCHANT|UPI|IMPS|NEFT|POS|ECOM|TXN|REF|PAYMENT FROM PHONE|PAYMENT FROM PH|SENT USING PAYTM|PAY TO)\b",
    re.I,
)
# Well-known brands whose VPA/payee names are messy – normalised to one merchant name.
_BRANDS = [
    "swiggy", "zomato", "zepto", "blinkit", "bigbasket", "instamart", "dmart", "amazon", "flipkart", "myntra", "ajio", "nykaa", "uber", "ola", "rapido",
    "irctc", "makemytrip", "goibibo", "indigo", "netflix", "spotify", "hotstar", "youtube", "apple", "google", "airtel", "jio", "vodafone", "bescom",
    "tata power", "adani", "zerodha", "groww", "upstox", "kuvera", "lic", "hdfc life", "icici pru", "apollo", "pharmeasy", "1mg", "netmeds", "cult",
    "bookmyshow", "pvr", "inox", "starbucks", "mcdonald", "dominos", "kfc", "burger king", "croma", "reliance", "jiomart", "tata cliq", "decathlon",
    "ikea", "urban company", "dunzo", "porter", "cred", "paytm", "phonepe", "hpcl", "bpcl", "iocl", "shell", "fastag", "act fibernet", "tata play",
]


def _title(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" .-_/*")
    return " ".join(w if w.isupper() and len(w) <= 3 else w.capitalize() for w in value.split())


def clean_merchant(value: str | None) -> str | None:
    if not value:
        return None
    v = _GATEWAYS.sub("", value.strip())
    lower = v.lower()
    for brand in sorted(_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(brand)}", lower):
            return _title(brand)
    v = _NOISE.sub(" ", v)
    v = re.sub(r"[\d]{4,}", " ", v)            # long numbers / refs
    v = re.sub(r"[^A-Za-z0-9&' ]+", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    if len(v) < 2 or v.isdigit():
        return None
    return _title(v)[:80]


def _vpa_merchant(vpa: str) -> str | None:
    local = vpa.split("@", 1)[0]
    local = re.sub(r"[._-]", " ", local)
    local = re.sub(r"\d+", " ", local).strip()
    if not local or re.fullmatch(r"[6-9]\d{9}", vpa.split("@")[0]):  # phone-number VPA → person
        return None
    return clean_merchant(local)


def extract(narration: str) -> dict:
    """Return the entities found in a narration. Keys are only present when found."""
    text = re.sub(r"\s+", " ", narration or "").strip()
    upper = text.upper()
    out: dict = {}
    for name, pattern in _MODE_RE:
        if pattern.search(text):
            out["mode"] = name
            break

    if re.search(r"/CR/|\bCR\b|-CR-|\bCREDIT\b|\bCREDITED\b|\bRECEIVED\b|\bREFUND\b|\bREVERSAL\b|\bSALARY\b|\bINT\.?\s*PD\b|\bCASHBACK\b", upper):
        out["direction"] = "in"
    elif re.search(r"/DR/|\bDR\b|-DR-|\bDEBIT\b|\bDEBITED\b|\bPAID\b|\bPURCHASE\b|\bWITHDRAWAL\b|\bSPENT\b", upper):
        out["direction"] = "out"

    dash_format = upper.startswith("UPI-") or (text.count("-") >= 3 and "/" not in text)
    if dash_format:
        # HDFC style: UPI-<payee>-<vpa>-<ifsc>-<ref>-<note>; dashes separate fields, so find the VPA per field.
        vpa = next((m for m in (_VPA.fullmatch(p.strip()) for p in text.split("-")) if m), None)
    else:
        vpa = _VPA.search(text)
    if vpa:
        out["vpa"] = vpa.group(1).lower()
        handle = out["vpa"].split("@")[1]
        if handle in _PSP_HANDLES:
            out["app"] = _PSP_HANDLES[handle]
    ifsc = _IFSC.search(upper)
    if ifsc:
        out["ifsc"] = ifsc.group(1)
        out["bank"] = _BANK_CODES.get(ifsc.group(1)[:4], ifsc.group(1)[:4])
    ref = _REF12.search(text)
    if ref:
        out["reference"] = ref.group(1)
    else:
        utr = _UTR.search(upper)
        if utr:
            out["reference"] = utr.group(1)
    card = _CARD.search(text)
    if card and out.get("mode") in ("Card", "ATM", None):
        out["card_last4"] = card.group(1)

    payee = None
    parts = [p.strip() for p in re.split(r"[/|]", text) if p.strip()]
    if out.get("mode") == "UPI":
        # Formats: UPI/DR/<ref>/<payee>/<bank>/<vpa>/<note> · UPI/<ref>/<note>/<vpa>/<bank> · UPI-<payee>-<vpa>-<ifsc>-<ref>-<note>
        if len(parts) <= 2 and "-" in text:
            parts = [p.strip() for p in text.split("-") if p.strip()]
        candidates = [p for p in parts[1:] if not re.fullmatch(r"(?:CR|DR|P2A|P2M|P2P|UPI|\d{6,}|[A-Z]{4}\w*BANK\w*|[A-Z]{4}0?\w{0,6})", p.upper())
                      and "@" not in p and not _IFSC.fullmatch(p.upper())
                      and not re.match(r"(?:payment (?:from|to)|sent using|pay to|collect request)\b", p, re.I)
                      and not re.search(r"\bBANK\b", p, re.I)]
        if candidates:
            payee = candidates[0]
            if len(candidates) > 1:
                out["note"] = candidates[-1][:80]
        if out.get("vpa") and (not payee or payee.lower().startswith("payment") or len(payee) < 3):
            payee = _vpa_merchant(out["vpa"]) or payee
        out["counterparty"] = "person" if re.search(r"\bP2A\b|\bP2P\b", upper) or (out.get("vpa") and re.match(r"[6-9]\d{9}@", out["vpa"])) else "merchant"
    elif out.get("mode") in ("IMPS", "NEFT", "RTGS"):
        segs = [p for p in re.split(r"[/\-]", text) if p.strip()]
        names = [s.strip() for s in segs if re.search(r"[A-Za-z]{3,}", s) and not re.fullmatch(r"(?:IMPS|NEFT|RTGS|CR|DR|P2A|MMT|INB|MOB)", s.strip().upper())
                 and not _IFSC.fullmatch(s.strip().upper()) and not _UTR.fullmatch(s.strip().upper())
                 and not re.fullmatch(r"(?:NEFT|IMPS|RTGS)\s*(?:CR|DR|IN|OUT)?", s.strip().upper())]
        if names:
            payee = names[0]
            if len(names) > 1:
                out["note"] = names[-1][:80]
    elif out.get("mode") == "Card":
        m = re.search(r"(?:POS|ECOM|PCD|VPS)\s*(?:[\dX*]{8,}\s*)?([A-Za-z][A-Za-z0-9 &.'*_-]{2,40})", text, re.I)
        if m:
            payee = re.split(r"\s{2,}|\s+(?:ON|AT)\s+\d", m.group(1))[0]
            city = re.search(r"\b(MUMBAI|BANGALORE|BENGALURU|BLR|DELHI|NEW DELHI|GURGAON|GURUGRAM|NOIDA|HYDERABAD|HYD|CHENNAI|PUNE|KOLKATA|AHMEDABAD|JAIPUR)\b", upper)
            if city:
                out["city"] = city.group(1).title()
                payee = re.sub(city.group(1), "", payee, flags=re.I)
    elif out.get("mode") == "Auto-debit":
        m = re.search(r"(?:ACH|NACH|ECS|SI)\s*[-/ ]?\s*(?:D|DR|DEBIT)?\s*[-/ ]?\s*([A-Za-z][A-Za-z0-9 &.]{2,40})", text, re.I)
        if m:
            payee = m.group(1)

    if payee is None and "mode" not in out and len(text) <= 60:
        payee = text  # e.g. "RAZORPAY*URBANCLAP TECHNOLOGIES" – the whole line is the merchant
    merchant = clean_merchant(payee) if payee else None
    if not merchant:
        lower = text.lower()
        for brand in sorted(_BRANDS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(brand)}", lower):
                merchant = _title(brand)
                break
    if payee:
        out["payee"] = _title(payee)[:80]
    if merchant:
        out["merchant"] = merchant
    if out.get("mode") == "Interest":
        out["merchant"] = out.get("merchant") or "Bank interest"
    return out


def payment_method(entities: dict) -> str:
    return {"UPI": "UPI", "IMPS": "Net banking", "NEFT": "Net banking", "RTGS": "Net banking", "Card": "Card", "ATM": "Cash",
            "Auto-debit": "Auto-debit", "Cheque": "Cheque", "Cash deposit": "Cash"}.get(entities.get("mode", ""), "")


def summary(entities: dict) -> str:
    """Short human-readable line, e.g. 'UPI · swiggy8@ybl · Ref 425167812345'."""
    bits = [entities.get("mode"), entities.get("app"), entities.get("vpa"), entities.get("bank"),
            f"card ••{entities['card_last4']}" if entities.get("card_last4") else None,
            f"Ref {entities['reference']}" if entities.get("reference") else None, entities.get("note")]
    return " · ".join(b for b in bits if b)
