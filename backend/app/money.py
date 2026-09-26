"""Money helpers.

Every monetary value is stored as an integer number of *minor units*
(paise for INR, cents for EUR/USD). Arithmetic happens on integers or
``Decimal`` – never on binary floats – so ₹0.10 + ₹0.20 is exactly ₹0.30.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ISO 4217 exponents that differ from the default of 2.
_EXPONENTS = {"JPY": 0, "KRW": 0, "VND": 0, "CLP": 0, "ISK": 0, "BHD": 3, "KWD": 3, "OMR": 3, "JOD": 3, "TND": 3}

SUPPORTED_CURRENCIES = (
    "INR", "EUR", "USD", "GBP", "AED", "SGD", "AUD", "CAD", "CHF", "JPY", "SAR", "QAR", "NZD", "HKD", "SEK", "NOK", "DKK",
)


class MoneyError(ValueError):
    pass


def exponent(currency: str) -> int:
    return _EXPONENTS.get(currency.upper(), 2)


def normalize_currency(currency: str | None) -> str:
    code = (currency or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise MoneyError(f"Invalid currency code: {currency!r}")
    return code


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        value = repr(value)
    try:
        text = str(value).strip().replace(",", "").replace("₹", "").replace(" ", "")
        return Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise MoneyError(f"Invalid amount: {value!r}") from exc


def to_minor(value, currency: str) -> int:
    """Convert a major-unit amount (``"1,234.50"``, ``Decimal``, ``int``) to integer minor units.

    Rejects amounts with more decimal places than the currency supports rather
    than silently rounding them.
    """
    amount = to_decimal(value)
    if not amount.is_finite():
        raise MoneyError("Amount must be a finite number")
    exp = exponent(currency)
    scaled = amount.scaleb(exp)
    if scaled != scaled.to_integral_value():
        raise MoneyError(f"{currency} amounts support at most {exp} decimal places")
    return int(scaled)


def from_minor(minor: int, currency: str) -> Decimal:
    return Decimal(int(minor)).scaleb(-exponent(currency))


def format_decimal(minor: int, currency: str) -> str:
    exp = exponent(currency)
    return f"{from_minor(minor, currency):.{exp}f}"


def format_display(minor: int, currency: str) -> str:
    """Human readable amount for notifications/emails, e.g. ``₹1,23,456.50``."""
    value = from_minor(minor, currency)
    symbol = {"INR": "₹", "EUR": "€", "USD": "$", "GBP": "£", "JPY": "¥"}.get(currency, f"{currency} ")
    sign = "-" if value < 0 else ""
    value = abs(value)
    exp = exponent(currency)
    whole, _, frac = f"{value:.{exp}f}".partition(".")
    if currency == "INR" and len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    else:
        whole = f"{int(whole):,}"
    text = f"{whole}.{frac}" if frac and frac.strip("0") else whole
    return f"{sign}{symbol}{text}"


def convert_minor(minor: int, rate: Decimal, from_currency: str, to_currency: str) -> int:
    """Convert minor units between currencies using ``rate`` (1 from = rate to)."""
    if from_currency == to_currency:
        return int(minor)
    major = from_minor(minor, from_currency) * Decimal(rate)
    return int(major.scaleb(exponent(to_currency)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def percent(part: int, whole: int) -> float:
    """Percentage for display. Returns 0 when the denominator is zero."""
    if not whole:
        return 0.0
    return float((Decimal(part) / Decimal(whole) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
