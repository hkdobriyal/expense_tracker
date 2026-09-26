"""Date-window helpers shared by budgets, analytics, alerts and reports."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def today_for(timezone_name: str) -> date:
    try:
        return datetime.now(ZoneInfo(timezone_name)).date()
    except Exception:  # unknown timezone string
        return date.today()


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def advance(d: date, frequency: str, times: int = 1) -> date:
    if frequency == "weekly":
        return d + timedelta(weeks=times)
    if frequency == "monthly":
        return add_months(d, times)
    if frequency == "quarterly":
        return add_months(d, 3 * times)
    if frequency == "half_yearly":
        return add_months(d, 6 * times)
    if frequency == "yearly":
        return add_months(d, 12 * times)
    return d  # "once"


# How many times per year a frequency occurs, used for monthly/annual equivalents.
OCCURRENCES_PER_YEAR = {"weekly": 52, "monthly": 12, "quarterly": 4, "half_yearly": 2, "yearly": 1, "once": 0}


def month_bounds(d: date) -> tuple[date, date]:
    return d.replace(day=1), d.replace(day=calendar.monthrange(d.year, d.month)[1])


def week_bounds(d: date, week_start: int = 0) -> tuple[date, date]:
    start = d - timedelta(days=(d.weekday() - week_start) % 7)
    return start, start + timedelta(days=6)


def year_bounds(d: date) -> tuple[date, date]:
    return date(d.year, 1, 1), date(d.year, 12, 31)


def period_window(period: str, on: date, week_start: int = 0) -> tuple[date, date]:
    if period == "day":
        return on, on
    if period == "weekly" or period == "week":
        return week_bounds(on, week_start)
    if period == "yearly" or period == "year":
        return year_bounds(on)
    return month_bounds(on)


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date
    label: str

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def previous(self) -> "DateRange":
        # Calendar months compare against the whole previous month; anything else
        # compares against a window of equal length immediately before.
        if self.start.day == 1 and self.end == month_bounds(self.start)[1]:
            prev_start, prev_end = month_bounds(add_months(self.start, -1))
            return DateRange(prev_start, prev_end, "previous month")
        length = self.end - self.start
        prev_end = self.start - timedelta(days=1)
        return DateRange(prev_end - length, prev_end, "previous period")


PRESETS = ("7d", "30d", "3m", "6m", "1y", "this_week", "this_month", "last_month", "this_year", "custom")


def resolve_range(preset: str | None, start: date | None, end: date | None, today: date, week_start: int = 0) -> DateRange:
    preset = preset or ("custom" if start and end else "this_month")
    if preset == "custom":
        if not start or not end:
            raise ValueError("Custom ranges need both 'start' and 'end'")
        if start > end:
            raise ValueError("'start' must be before 'end'")
        return DateRange(start, end, f"{start.isoformat()} – {end.isoformat()}")
    if preset == "7d":
        return DateRange(today - timedelta(days=6), today, "Last 7 days")
    if preset == "30d":
        return DateRange(today - timedelta(days=29), today, "Last 30 days")
    if preset == "3m":
        return DateRange(add_months(today, -3) + timedelta(days=1), today, "Last 3 months")
    if preset == "6m":
        return DateRange(add_months(today, -6) + timedelta(days=1), today, "Last 6 months")
    if preset == "1y":
        return DateRange(add_months(today, -12) + timedelta(days=1), today, "Last 12 months")
    if preset == "this_week":
        s, e = week_bounds(today, week_start)
        return DateRange(s, e, "This week")
    if preset == "last_month":
        s, e = month_bounds(add_months(today, -1))
        return DateRange(s, e, s.strftime("%B %Y"))
    if preset == "this_year":
        s, e = year_bounds(today)
        return DateRange(s, e, str(today.year))
    s, e = month_bounds(today)
    return DateRange(s, e, s.strftime("%B %Y"))
