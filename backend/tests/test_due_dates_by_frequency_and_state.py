"""
Unit test suite for G4: Due-date configuration by frequency, form, and state code.
Validates:
- Monthly GSTR-3B -> 20th of following month
- Monthly GSTR-1 -> 11th of following month
- Quarterly GSTR-1 -> 13th of month following quarter
- Quarterly GSTR-3B Category X states -> 22nd of month following quarter
- Quarterly GSTR-3B Category Y states -> 24th of month following quarter
- All Category X state codes verified
- Year-end boundary rollover (December period due in January)
"""

from datetime import date
import pytest

from app.services.gst_filing_service import (
    calculate_due_date,
    CATEGORY_X_STATES,
    DUE_DATE_RULES,
)


def test_monthly_due_dates():
    # Monthly GSTR-3B Sep 2026 (ends 2026-09-30) -> 2026-10-20
    d_3b_sep = calculate_due_date(date(2026, 9, 30), "GSTR-3B", "monthly")
    assert d_3b_sep == date(2026, 10, 20)

    # Monthly GSTR-1 Sep 2026 (ends 2026-09-30) -> 2026-10-11
    d_1_sep = calculate_due_date(date(2026, 9, 30), "GSTR-1", "monthly")
    assert d_1_sep == date(2026, 10, 11)

    # Monthly GSTR-3B Jul 2026 (ends 2026-07-31) -> 2026-08-20
    d_3b_jul = calculate_due_date(date(2026, 7, 31), "GSTR-3B", "monthly")
    assert d_3b_jul == date(2026, 8, 20)

    # Year-end rollover: Dec 2026 (ends 2026-12-31) -> 2027-01-20
    d_3b_dec = calculate_due_date(date(2026, 12, 31), "GSTR-3B", "monthly")
    assert d_3b_dec == date(2027, 1, 20)


def test_quarterly_due_dates_category_x_and_y():
    # Q2 FY 2026-27 (ends 2026-09-30)
    q2_end = date(2026, 9, 30)

    # Category X state: 27 Maharashtra -> 2026-10-22
    d_cat_x = calculate_due_date(q2_end, "GSTR-3B", "quarterly", state_code="27")
    assert d_cat_x == date(2026, 10, 22)

    # Category Y state: 07 Delhi -> 2026-10-24
    d_cat_y = calculate_due_date(q2_end, "GSTR-3B", "quarterly", state_code="07")
    assert d_cat_y == date(2026, 10, 24)

    # Quarterly GSTR-1 Q2 -> 2026-10-13
    d_gstr1_q2 = calculate_due_date(q2_end, "GSTR-1", "quarterly")
    assert d_gstr1_q2 == date(2026, 10, 13)


def test_all_category_x_states_get_22nd():
    q2_end = date(2026, 9, 30)
    for code in CATEGORY_X_STATES:
        d = calculate_due_date(q2_end, "GSTR-3B", "quarterly", state_code=code)
        assert d == date(2026, 10, 22), f"State code {code} should be Category X (22nd)"


def test_category_y_states_get_24th():
    q2_end = date(2026, 9, 30)
    cat_y_codes = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "19", "20", "21"]
    for code in cat_y_codes:
        d = calculate_due_date(q2_end, "GSTR-3B", "quarterly", state_code=code)
        assert d == date(2026, 10, 24), f"State code {code} should be Category Y (24th)"


def test_quarterly_year_end_rollover():
    # Q3 FY 2026-27 (ends 2026-12-31) -> January 2027
    q3_end = date(2026, 12, 31)
    d_q3_x = calculate_due_date(q3_end, "GSTR-3B", "quarterly", state_code="27")
    assert d_q3_x == date(2027, 1, 22)

    d_q3_y = calculate_due_date(q3_end, "GSTR-3B", "quarterly", state_code="07")
    assert d_q3_y == date(2027, 1, 24)

    d_q3_g1 = calculate_due_date(q3_end, "GSTR-1", "quarterly")
    assert d_q3_g1 == date(2027, 1, 13)
