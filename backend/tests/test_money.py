from decimal import Decimal

import pytest

from app.money import MoneyError, convert_minor, format_display, percent, to_minor


def test_to_minor_is_exact():
    assert to_minor("0.10", "INR") + to_minor("0.20", "INR") == to_minor("0.30", "INR") == 30
    assert to_minor("1,12,400.50", "INR") == 11240050
    assert to_minor(0.1, "INR") == 10  # floats go through repr, not binary expansion
    assert to_minor("1500", "JPY") == 1500


def test_rejects_sub_paise_precision():
    with pytest.raises(MoneyError):
        to_minor("10.005", "INR")
    with pytest.raises(MoneyError):
        to_minor("abc", "INR")


def test_indian_grouping():
    assert format_display(1234567850, "INR") == "₹1,23,45,678.50"
    assert format_display(-50000, "INR") == "-₹500"
    assert format_display(129900, "EUR") == "€1,299"


def test_convert_and_percent():
    assert convert_minor(1000, Decimal("83.25"), "USD", "INR") == 83250  # $10 → ₹832.50
    assert convert_minor(999, Decimal("1"), "INR", "INR") == 999
    assert percent(41000, 50000) == 82.0
    assert percent(1, 0) == 0.0
