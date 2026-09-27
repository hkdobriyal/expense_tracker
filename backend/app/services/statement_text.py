"""Transactions from unstructured statement text (PDF text, DOCX paragraphs, OCR output).

Bank statements printed as text lose their column boundaries, so we work per line:

1. A transaction line *starts with a date* (13/09/2026, 13-Sep-26, 13 Sep 2026, 2026-09-13…).
2. Money values have exactly two decimals ("1,12,400.00"), optionally followed by Cr/Dr.
   The last one is usually the running balance, the one before it the amount.
3. Lines without a date continue the previous narration (multi-line descriptions).
4. Direction comes from an explicit Cr/Dr marker, else from the change in running
   balance (the most reliable signal), else from wording ("credited", "salary"…).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from ..money import to_decimal
from .extraction import extract

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
DATE_AT_START = re.compile(
    rf"^\s*(\d{{1,2}}[/\-.]\d{{1,2}}[/\-.]\d{{2,4}}|\d{{1,2}}[\s\-/]?(?:{_MONTHS})[a-z]*[\s\-/,]*\d{{2,4}}|\d{{4}}-\d{{2}}-\d{{2}})\b",
    re.I,
)
SECOND_DATE = re.compile(rf"^\s*(\d{{1,2}}[/\-.]\d{{1,2}}[/\-.]\d{{2,4}}|\d{{1,2}}[\s\-/]?(?:{_MONTHS})[a-z]*[\s\-/,]*\d{{2,4}})\b", re.I)
AMOUNT = re.compile(r"(?<![\w.])(-?\(?\d{1,3}(?:,\d{2,3})*(?:\.\d{2})\)?|-?\d+\.\d{2})(\s*(?:Cr|Dr|CR|DR|cr|dr)\b\.?)?")
SKIP = re.compile(
    r"^(?:page \d+|statement of account|opening balance|closing balance|total|grand total|balance b/?f|balance c/?f|brought forward|carried forward|"
    r"date\s+(?:narration|particulars|description)|txn date|value date|this is a (?:computer|system) generated|\*+|-{5,})", re.I,
)
OPENING = re.compile(r"(?:opening|previous|b/?f)\s*balance[^\d-]*(-?[\d,]+\.\d{2})\s*(cr|dr)?", re.I)
CREDIT_WORDS = re.compile(r"\b(credit(?:ed)?|deposit|received|salary|refund|reversal|cashback|interest|int\.?\s*pd|neft cr|imps cr|by transfer|/cr/)\b", re.I)


def _amount(token: str) -> Decimal:
    negative = token.startswith("-") or (token.startswith("(") and token.endswith(")"))
    value = to_decimal(token.strip("()-"))
    return -value if negative else value


def parse_lines(lines: list[str]) -> tuple[list[list[str]], list[str]]:
    """Return rows as [date, description, amount, Dr/Cr, balance] plus notes about the parse."""
    notes: list[str] = []
    opening: Decimal | None = None
    entries: list[dict] = []
    for raw in lines:
        line = re.sub(r"\s+", " ", raw.replace(" ", " ")).strip()
        if not line:
            continue
        m_open = OPENING.search(line)
        if m_open and opening is None:
            opening = _amount(m_open.group(1))
            if (m_open.group(2) or "").lower() == "dr":
                opening = -opening
            continue
        if SKIP.match(line):
            continue
        m = DATE_AT_START.match(line)
        if not m:
            # Continuation of the previous narration (only text, no money values).
            if entries and not AMOUNT.search(line) and len(line) < 120 and len(entries[-1]["desc"]) < 300:
                entries[-1]["desc"] += " " + line
            continue
        day = m.group(1)
        rest = line[m.end():]
        second = SECOND_DATE.match(rest)  # value date column
        if second:
            rest = rest[second.end():]
        amounts = list(AMOUNT.finditer(rest))
        if not amounts:
            entries.append({"date": day, "desc": rest.strip(), "amounts": [], "pending": True})
            continue
        desc = rest[: amounts[0].start()].strip(" -|:")
        tail = rest[amounts[-1].end():].strip()
        if tail and not re.fullmatch(r"[\d\s.,:/-]*", tail):
            desc = f"{desc} {tail}".strip()
        entries.append({"date": day, "desc": desc, "amounts": [(_amount(a.group(1)), (a.group(2) or "").strip().upper().rstrip(".")) for a in amounts]})

    # A date line without amounts may have its amounts on the following line (wrapped layouts).
    rows: list[list[str]] = []
    previous_balance = opening
    inferred_by_balance = 0
    for e in entries:
        if not e["amounts"]:
            continue
        values = e["amounts"]
        if len(values) >= 2:
            amount, marker = values[-2]
            balance, balance_marker = values[-1]
            if balance_marker == "DR":
                balance = -balance
        else:
            amount, marker = values[0]
            balance = None
        if amount == 0 and len(values) >= 3:  # "0.00" in an empty debit/credit column
            amount, marker = values[-3]
        direction = ""
        if marker in ("CR", "DR"):
            direction = marker
        elif previous_balance is not None and balance is not None:
            delta = balance - previous_balance
            if abs(abs(delta) - abs(amount)) <= Decimal("0.01"):
                direction = "CR" if delta > 0 else "DR"
                inferred_by_balance += 1
        if not direction:
            if amount < 0:
                direction = "DR"
            else:
                entities = extract(e["desc"])
                direction = "CR" if entities.get("direction") == "in" or CREDIT_WORDS.search(e["desc"]) else "DR"
        if balance is not None:
            previous_balance = balance
        rows.append([e["date"], e["desc"] or "Transaction", format(abs(amount), "f"), direction, format(balance, "f") if balance is not None else ""])
    if rows and inferred_by_balance:
        notes.append(f"Debit/credit for {inferred_by_balance} of {len(rows)} rows was inferred from the running balance.")
    return rows, notes


# ---------------------------------------------------------------------------
# OCR (scanned PDFs and photos of statements/receipts) – RapidOCR, fully local
# ---------------------------------------------------------------------------

_ocr_engine = None


def _engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def ocr_image_lines(image) -> list[str]:
    """OCR a PIL image and rebuild text lines by grouping boxes on the same row."""
    import numpy as np

    result, _ = _engine()(np.array(image.convert("RGB")))
    if not result:
        return []
    boxes = []
    for points, text, _score in result:
        ys = [p[1] for p in points]
        xs = [p[0] for p in points]
        boxes.append(((min(ys) + max(ys)) / 2, min(xs), max(ys) - min(ys), text))
    boxes.sort()
    lines: list[list] = []
    for yc, x, h, text in boxes:
        if lines and abs(lines[-1][0] - yc) <= max(h, 8) * 0.6:
            lines[-1][1].append((x, text))
        else:
            lines.append([yc, [(x, text)]])
    return ["  ".join(t for _, t in sorted(parts)) for _, parts in lines]

