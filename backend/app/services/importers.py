"""Statement file parsers: CSV, XLSX, OFX/QFX and (text-based) PDF.

Every parser produces the same shape – ``headers`` + ``rows`` of strings – so
one column-mapping step handles all formats. Mapping turns rows into
normalised transactions (date, description, signed amount, …).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ..money import MoneyError, to_decimal

MAX_ROWS = 5000

DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d-%b-%Y", "%d-%b-%y",
    "%d %b %y", "%d/%b/%Y", "%b %d, %Y", "%m/%d/%Y", "%Y/%m/%d", "%Y%m%d", "%d %B %Y",
)

BANK_MARKERS = [
    ("hdfc", "HDFC Bank"), ("state bank of india", "State Bank of India"), ("sbi", "State Bank of India"), ("icici", "ICICI Bank"),
    ("axis", "Axis Bank"), ("kotak", "Kotak Mahindra Bank"), ("yes bank", "Yes Bank"), ("indusind", "IndusInd Bank"),
    ("punjab national", "Punjab National Bank"), ("bank of baroda", "Bank of Baroda"), ("canara", "Canara Bank"),
    ("idfc", "IDFC FIRST Bank"), ("federal bank", "Federal Bank"), ("au small finance", "AU Small Finance Bank"),
]


class ImportParseError(ValueError):
    pass


@dataclass
class ParsedFile:
    file_format: str
    headers: list[str]
    rows: list[list[str]]
    bank_detected: str = ""
    preset_mapping: dict | None = None  # formats with a fixed layout (OFX/PDF) need no user mapping


def detect_format(filename: str, content: bytes) -> str:
    name = filename.lower()
    head = content[:512].lstrip()
    if name.endswith((".ofx", ".qfx")) or b"<OFX>" in content[:4096].upper() or head.startswith(b"OFXHEADER"):
        return "qfx" if name.endswith(".qfx") else "ofx"
    if name.endswith(".pdf") or head.startswith(b"%PDF"):
        return "pdf"
    if name.endswith((".xlsx", ".xlsm")) or head.startswith(b"PK\x03\x04"):
        return "xlsx"
    if name.endswith((".csv", ".txt", ".tsv")):
        return "csv"
    raise ImportParseError("Unsupported file type. Upload a CSV, XLSX, OFX/QFX or PDF statement.")


def detect_bank(text: str) -> str:
    lower = text.lower()
    return next((label for marker, label in BANK_MARKERS if marker in lower), "")


def _is_header_row(cells: list[str]) -> bool:
    joined = " ".join(c.lower() for c in cells)
    has_date = "date" in joined
    has_text = any(k in joined for k in ("narration", "particular", "description", "remark", "details", "transaction"))
    has_amount = any(k in joined for k in ("amount", "debit", "credit", "withdrawal", "deposit", "dr", "cr"))
    return has_date and (has_text or has_amount)


def _tabulate(rows: list[list[str]], file_format: str, bank: str) -> ParsedFile:
    rows = [[(c if c is not None else "").strip() for c in r] for r in rows]
    header_idx = next((i for i, r in enumerate(rows[:40]) if _is_header_row(r)), None)
    if header_idx is None:
        raise ImportParseError("Could not find a header row with a date and an amount/description column.")
    headers = [h or f"Column {i + 1}" for i, h in enumerate(rows[header_idx])]
    width = len(headers)
    body = []
    for r in rows[header_idx + 1:]:
        if not any(r):
            continue
        body.append((r + [""] * width)[:width])
        if len(body) > MAX_ROWS:
            raise ImportParseError(f"Files are limited to {MAX_ROWS} rows. Split the statement and import it in parts.")
    return ParsedFile(file_format, headers, body, bank)


def parse_csv(content: bytes) -> ParsedFile:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:5000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    return _tabulate(rows, "csv", detect_bank(sample))


def parse_xlsx(content: bytes) -> ParsedFile:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # corrupt / not an xlsx
        raise ImportParseError(f"Could not open the spreadsheet: {exc}") from exc
    ws = wb.worksheets[0]
    rows = []
    for row in ws.iter_rows(values_only=True):
        cells = []
        for v in row:
            if isinstance(v, datetime):
                cells.append(v.date().isoformat())
            elif isinstance(v, date):
                cells.append(v.isoformat())
            elif isinstance(v, float):
                cells.append(format(Decimal(repr(v)), "f"))
            else:
                cells.append("" if v is None else str(v))
        rows.append(cells)
        if len(rows) > MAX_ROWS + 50:
            break
    wb.close()
    return _tabulate(rows, "xlsx", detect_bank(" ".join(" ".join(r) for r in rows[:15])))


_OFX_TXN = re.compile(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", re.S | re.I)


def _ofx_field(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}>([^<\r\n]*)", block, re.I)
    return m.group(1).strip() if m else ""


def parse_ofx(content: bytes, file_format: str = "ofx") -> ParsedFile:
    text = content.decode("utf-8", errors="replace")
    rows = []
    for block in _OFX_TXN.findall(text):
        posted = _ofx_field(block, "DTPOSTED")[:8]
        rows.append([
            f"{posted[:4]}-{posted[4:6]}-{posted[6:8]}" if len(posted) == 8 else posted,
            _ofx_field(block, "NAME") or _ofx_field(block, "MEMO"),
            _ofx_field(block, "TRNAMT"),
            _ofx_field(block, "FITID"),
            _ofx_field(block, "MEMO"),
            _ofx_field(block, "TRNTYPE"),
        ])
    if not rows:
        raise ImportParseError("No transactions (<STMTTRN>) found in the OFX file.")
    org = _ofx_field(text, "ORG")
    headers = ["Date", "Description", "Amount", "FITID", "Memo", "Type"]
    mapping = {"date": 0, "description": 1, "amount": 2, "external_id": 3, "notes": 4, "date_format": "%Y-%m-%d", "sign": "signed"}
    return ParsedFile(file_format, headers, rows[:MAX_ROWS], org or detect_bank(text[:3000]), mapping)


_PDF_LINE = re.compile(
    r"^(\d{1,2}[/\-.](?:\d{1,2}|[A-Za-z]{3})[/\-.]\d{2,4})\s+(.+?)\s+(-?[\d,]+\.\d{2})\s*(CR|DR|Cr|Dr)?(?:\s+(-?[\d,]+\.\d{2})\s*(?:CR|DR|Cr|Dr)?)?\s*$"
)


def parse_pdf(content: bytes, password: str | None = None) -> ParsedFile:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(content))
    except PdfReadError as exc:
        raise ImportParseError(f"Could not read the PDF: {exc}") from exc
    if reader.is_encrypted:
        if not password:
            raise ImportParseError("This PDF is password protected. Enter the statement password (often PAN in capitals + date of birth).")
        if not reader.decrypt(password):
            raise ImportParseError("Incorrect statement password.")
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if not text.strip():
        raise ImportParseError("No text found in this PDF (it may be a scanned image). Download a CSV/XLSX statement instead.")
    rows = []
    for line in (l.strip() for l in text.splitlines()):
        m = _PDF_LINE.match(line)
        if not m:
            continue
        rows.append([m.group(1), m.group(2), m.group(3), (m.group(4) or "").upper(), m.group(5) or ""])
    if not rows:
        raise ImportParseError("No transaction lines recognised in this PDF. Bank PDF layouts vary – a CSV/XLSX export imports more reliably.")
    headers = ["Date", "Narration", "Amount", "Dr/Cr", "Balance"]
    mapping = {"date": 0, "description": 1, "amount": 2, "direction": 3, "balance": 4, "sign": "direction_column"}
    return ParsedFile("pdf", headers, rows[:MAX_ROWS], detect_bank(text[:3000]), mapping)


def parse_file(filename: str, content: bytes, password: str | None = None) -> ParsedFile:
    fmt = detect_format(filename, content)
    if fmt == "csv":
        return parse_csv(content)
    if fmt == "xlsx":
        return parse_xlsx(content)
    if fmt in ("ofx", "qfx"):
        return parse_ofx(content, fmt)
    return parse_pdf(content, password)


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------

def suggest_mapping(headers: list[str]) -> dict:
    lower = [h.lower() for h in headers]

    def find(*keys, exclude=()):
        for i, h in enumerate(lower):
            if any(k in h for k in keys) and not any(x in h for x in exclude):
                return i
        return None

    mapping = {
        "date": find("txn date", "transaction date", "value date", "date", exclude=("chq",)),
        "description": find("narration", "particular", "description", "remark", "details"),
        "debit": find("withdrawal", "debit", exclude=("credit",)),
        "credit": find("deposit", "credit", exclude=("debit",)),
        "amount": find("amount", "amt", exclude=("balance",)),
        "direction": find("dr/cr", "cr/dr", "type"),
        "balance": find("balance"),
        "external_id": find("ref no", "reference", "chq", "utr", "transaction id"),
    }
    if mapping["debit"] is not None and mapping["credit"] is not None:
        mapping["sign"] = "debit_credit"
    elif mapping["direction"] is not None:
        mapping["sign"] = "direction_column"
    else:
        mapping["sign"] = "signed"
    mapping["date_format"] = None  # auto-detect
    return mapping


def detect_date_format(values: list[str]) -> str | None:
    samples = [v.strip().split(" ")[0] if re.match(r"^\d", v.strip()) and ":" in v else v.strip() for v in values if v and v.strip()][:200]
    if not samples:
        return None
    best, best_hits = None, 0
    for fmt in DATE_FORMATS:  # day-first formats come first: Indian statements are DD/MM
        hits = 0
        for s in samples:
            try:
                datetime.strptime(s, fmt)
                hits += 1
            except ValueError:
                pass
        if hits > best_hits:
            best, best_hits = fmt, hits
        if hits == len(samples):
            return fmt
    return best


def parse_date(value: str, fmt: str | None) -> date:
    raw = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]", raw):
        raw = raw[:10]
    elif ":" in raw and " " in raw:
        raw = raw.split(" ")[0]
    formats = [fmt] if fmt else list(DATE_FORMATS)
    for f in formats:
        try:
            return datetime.strptime(raw, f).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date '{value}'")


def parse_amount(value: str) -> Decimal | None:
    raw = (value or "").strip()
    if not raw or raw in ("-", "--"):
        return None
    negative = raw.startswith("(") and raw.endswith(")") or raw.startswith("-") or raw.endswith("-")
    cleaned = re.sub(r"(?i)(inr|rs\.?|₹|cr|dr|[()\s+-])", "", raw)
    if not cleaned:
        return None
    try:
        amount = to_decimal(cleaned)
    except MoneyError:
        raise ValueError(f"Unrecognised amount '{value}'")
    return -amount if negative else amount


_UPI = re.compile(r"UPI[/-](?:(?:CR|DR|P2A|P2M)[/-])?(?:\d{6,}[/-])?([^/@-][^/@]*?)(?:[/@]|$)", re.I)
_POS = re.compile(r"(?:POS|ECOM|PCD)\s*(?:\d{4,}\s*)?([A-Za-z][A-Za-z0-9 &.'-]{2,40})", re.I)
_NEFT = re.compile(r"(?:NEFT|IMPS|RTGS)[/-](?:(?:CR|DR)[/-])?[A-Z0-9]*[/-]([^/]+)", re.I)


def guess_merchant(narration: str) -> str | None:
    for pattern in (_UPI, _POS, _NEFT):
        m = pattern.search(narration)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip(" .-")
            if len(name) >= 2 and not name.isdigit():
                return name.title()[:80]
    return None


def guess_payment_method(narration: str) -> str:
    upper = narration.upper()
    if "UPI" in upper:
        return "UPI"
    if any(k in upper for k in ("POS", "ECOM", "PCD", "CARD")):
        return "Card"
    if any(k in upper for k in ("NEFT", "IMPS", "RTGS")):
        return "Net banking"
    if any(k in upper for k in ("ACH", "NACH", "ECS", "SI-", "MANDATE")):
        return "Auto-debit"
    if "ATM" in upper or "CASH WDL" in upper:
        return "Cash"
    return ""


def guess_type(narration: str, direction: str) -> str:
    upper = narration.upper()
    if direction == "in":
        if "REFUND" in upper or "REVERSAL" in upper or "RETURN" in upper:
            return "refund"
        return "income"
    if any(k in upper for k in ("SIP", "MUTUAL FUND", "ZERODHA", "GROWW", "KFINTECH", "CAMS", "INDMONEY", "UPSTOX")):
        return "investment"
    return "expense"


def normalize_rows(headers: list[str], rows: list[list[str]], mapping: dict) -> list[dict]:
    """Apply a column mapping. Each output row has either the fields or an ``error``."""

    def col(row: list[str], key: str) -> str:
        idx = mapping.get(key)
        if idx is None or idx == "" or int(idx) >= len(row):
            return ""
        return row[int(idx)]

    date_fmt = mapping.get("date_format") or detect_date_format([col(r, "date") for r in rows])
    sign_mode = mapping.get("sign", "signed")
    invert = bool(mapping.get("invert"))
    out = []
    for index, row in enumerate(rows):
        item: dict = {"row": index, "raw": row}
        try:
            if mapping.get("date") is None:
                raise ValueError("Map the date column")
            day = parse_date(col(row, "date"), date_fmt)
            description = re.sub(r"\s+", " ", col(row, "description")).strip()
            if not description:
                raise ValueError("Empty description")
            if sign_mode == "debit_credit":
                debit, credit = parse_amount(col(row, "debit")), parse_amount(col(row, "credit"))
                if credit and credit != 0:
                    signed = abs(credit)
                elif debit and debit != 0:
                    signed = -abs(debit)
                else:
                    raise ValueError("No debit or credit amount")
            else:
                amount = parse_amount(col(row, "amount"))
                if amount is None or amount == 0:
                    raise ValueError("No amount")
                if sign_mode == "direction_column":
                    d = col(row, "direction").strip().upper()
                    is_credit = d.startswith("CR") or d.startswith("C") or d in ("DEPOSIT", "CREDIT", "IN")
                    signed = abs(amount) if is_credit else -abs(amount)
                else:
                    signed = amount
            if invert:
                signed = -signed
            direction = "in" if signed > 0 else "out"
            item.update({
                "date": day.isoformat(),
                "description": description[:255],
                "amount": format(abs(signed), "f"),
                "direction": direction,
                "type": guess_type(description, direction),
                "merchant": guess_merchant(description),
                "payment_method": guess_payment_method(description),
                "external_id": col(row, "external_id").strip() or None,
                "notes": col(row, "notes").strip(),
                "balance": col(row, "balance").strip(),
                "status": "ok",
            })
        except (ValueError, TypeError) as exc:
            item.update({"status": "error", "error": str(exc)})
        out.append(item)
    return out
