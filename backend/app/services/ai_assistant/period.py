"""
Period parsing for the AI assistant.

Turns phrases such as "July 2026", "2026-07", "Q2 FY 2026-27", "FY26",
"last month" or "this quarter" into a concrete (from_date, to_date) range.

Indian financial-year conventions are used:
  * FY 2025-26  = 1 Apr 2025 .. 31 Mar 2026
  * "FY26"      = FY 2025-26 (the year in which the FY *ends*)
  * Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar (of the next calendar year)
No period mentioned -> PeriodSpec(None, None, None) meaning "all recorded periods".
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))


@dataclass(frozen=True)
class PeriodSpec:
    label: Optional[str] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None

    @property
    def is_set(self) -> bool:
        return self.from_date is not None and self.to_date is not None

    @property
    def display(self) -> str:
        return self.label if self.is_set and self.label else "all recorded periods"


NO_PERIOD = PeriodSpec()


# ── helpers ───────────────────────────────────────────────────────────────────

def _month_range(year: int, month: int) -> PeriodSpec:
    last = calendar.monthrange(year, month)[1]
    label = f"{calendar.month_name[month]} {year}"
    return PeriodSpec(label, date(year, month, 1), date(year, month, last))


def fy_start_year(d: date) -> int:
    return d.year if d.month >= 4 else d.year - 1


def _fy_range(start_year: int) -> PeriodSpec:
    return PeriodSpec(
        f"FY {start_year}-{str(start_year + 1)[-2:]}",
        date(start_year, 4, 1),
        date(start_year + 1, 3, 31),
    )


def _quarter_range(fy_start: int, q: int) -> PeriodSpec:
    spans = {
        1: (date(fy_start, 4, 1), date(fy_start, 6, 30)),
        2: (date(fy_start, 7, 1), date(fy_start, 9, 30)),
        3: (date(fy_start, 10, 1), date(fy_start, 12, 31)),
        4: (date(fy_start + 1, 1, 1), date(fy_start + 1, 3, 31)),
    }
    start, end = spans[q]
    return PeriodSpec(f"Q{q} FY {fy_start}-{str(fy_start + 1)[-2:]}", start, end)


def _quarter_of(d: date) -> int:
    return {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3, 1: 4, 2: 4, 3: 4}[d.month]


def _two_digit_year(yy: int) -> int:
    return 2000 + yy


# ── public API ────────────────────────────────────────────────────────────────

def parse_period(text: Optional[str], today: Optional[date] = None) -> PeriodSpec:
    """Best-effort period extraction. Returns NO_PERIOD when nothing is recognised."""
    if not text:
        return NO_PERIOD
    today = today or date.today()
    t = text.lower()

    # ---- 1. Explicit financial year: "FY 2026-27", "FY2025-26", "FY26", "FY 2026"
    m = re.search(r"\bfy\s*[:\-]?\s*(20\d{2})\s*[-/]\s*(\d{2,4})\b", t)
    fy_start: Optional[int] = int(m.group(1)) if m else None
    if fy_start is None:
        m = re.search(r"\bfy\s*[:\-]?\s*(\d{2})\b(?!\d)", t)
        if m:
            fy_start = _two_digit_year(int(m.group(1))) - 1
    if fy_start is None:
        m = re.search(r"\bfy\s*[:\-]?\s*(20\d{2})\b", t)
        if m:
            fy_start = int(m.group(1)) - 1
    if fy_start is None:
        m = re.search(r"\b(20\d{2})\s*[-/]\s*(\d{2})\b", t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b > 12 and b == (a + 1) % 100:
                fy_start = a

    # ---- 2. Quarter: "Q2", "Q2 2026", "Q2 FY26"
    qm = re.search(r"\bq([1-4])\b", t)
    if qm:
        q = int(qm.group(1))
        if fy_start is None:
            ym = re.search(r"\b(20\d{2})\b", t)
            fy_start = int(ym.group(1)) if ym else fy_start_year(today)
        return _quarter_range(fy_start, q)

    if fy_start is not None:
        return _fy_range(fy_start)

    # ---- 3. ISO month: "2026-07"
    m = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", t)
    if m:
        return _month_range(int(m.group(1)), int(m.group(2)))

    # ---- 4. Month name with year: "July 2026", "jul-26"
    m = re.search(rf"\b({_MONTH_RE})\b(?:[\s,]*(20\d{{2}})\b|[\-/']\s*(\d{{2}})\b)", t)
    if m:
        year = int(m.group(2)) if m.group(2) else _two_digit_year(int(m.group(3)))
        return _month_range(year, _MONTHS[m.group(1)])

    # ---- 5. Month name preceded by a preposition: "for July", "in august", "month of may"
    m = re.search(rf"\b(?:in|for|of|during|month of)\s+({_MONTH_RE})\b", t)
    if m:
        month = _MONTHS[m.group(1)]
        year = today.year if month <= today.month else today.year - 1
        return _month_range(year, month)

    # ---- 6. Relative phrases
    if re.search(r"\b(this|current)\s+month\b", t):
        return _month_range(today.year, today.month)
    if re.search(r"\b(last|previous|prior)\s+month\b", t):
        y, mth = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        return _month_range(y, mth)
    if re.search(r"\b(this|current)\s+quarter\b", t):
        return _quarter_range(fy_start_year(today), _quarter_of(today))
    if re.search(r"\b(last|previous)\s+quarter\b", t):
        q = _quarter_of(today)
        fy = fy_start_year(today)
        if q == 1:
            return _quarter_range(fy - 1, 4)
        return _quarter_range(fy, q - 1)
    if re.search(r"\b(this|current)\s+(financial\s+year|fy|year)\b", t):
        return _fy_range(fy_start_year(today))
    if re.search(r"\b(last|previous)\s+(financial\s+year|fy|year)\b", t):
        return _fy_range(fy_start_year(today) - 1)

    return NO_PERIOD
