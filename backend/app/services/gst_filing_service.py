"""
GST Filing Service — Single Source of Truth for Filing Profile, Period Calculations,
and Statutory Due Dates.
"""

import re
import calendar
from typing import Optional, Dict, Any, List, Tuple
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.models.client import Client
from app.models.user import User
from app.models.accounting_record import AccountingRecord
from app.models.gst_record import GSTRecord
from app.schemas.gst_reconciliation import (
    FilingPeriodOption,
    FilingReturnFormOption,
    FilingOptionsResponse,
    FilingBlocker,
    FilingPreviewResponse,
)

CATEGORY_X_STATES = {
    "22", "23", "24", "25", "26", "27", "29", "30",
    "31", "32", "33", "34", "35", "36", "37"
}

GST_STATE_MAP = {
    "01": "JAMMU AND KASHMIR",
    "02": "HIMACHAL PRADESH",
    "03": "PUNJAB",
    "04": "CHANDIGARH",
    "05": "UTTARAKHAND",
    "06": "HARYANA",
    "07": "DELHI",
    "08": "RAJASTHAN",
    "09": "UTTAR PRADESH",
    "10": "BIHAR",
    "11": "SIKKIM",
    "12": "ARUNACHAL PRADESH",
    "13": "NAGALAND",
    "14": "MANIPUR",
    "15": "MIZORAM",
    "16": "TRIPURA",
    "17": "MEGHALAYA",
    "18": "ASSAM",
    "19": "WEST BENGAL",
    "20": "JHARKHAND",
    "21": "ODISHA",
    "22": "CHHATTISGARH",
    "23": "MADHYA PRADESH",
    "24": "GUJARAT",
    "25": "DAMAN AND DIU",
    "26": "DADRA AND NAGAR HAVELI",
    "27": "MAHARASHTRA",
    "29": "KARNATAKA",
    "30": "GOA",
    "31": "LAKSHADWEEP",
    "32": "KERALA",
    "33": "TAMIL NADU",
    "34": "PUDUCHERRY",
    "35": "ANDAMAN AND NICOBAR ISLANDS",
    "36": "TELANGANA",
    "37": "ANDHRA PRADESH",
    "38": "LADAKH",
    "97": "OTHER TERRITORY",
}


def get_filing_profile(client: Any) -> Dict[str, Any]:
    """Single source of truth for client's GST filing profile.

    Normalises return_frequency case-insensitively:
      'Monthly', 'monthly', 'm' -> 'monthly'
      'Quarterly', 'quarterly', 'q' -> 'quarterly'
      Anything else, unrecognized, or null -> None (NEVER defaults silently).

    Returns:
      frequency: 'monthly' | 'quarterly' | None
      state_code: first two digits of client's GSTIN (e.g. '27')
      due_category: 'X' | 'Y' (Category X: 22nd, Category Y: 24th for quarterly)
      state_mismatch: bool (True if GSTIN state contradicts stored state)
      stored_frequency: original raw value
      state_name: official statutory state name
    """
    raw_freq = getattr(client, "return_frequency", None)
    if raw_freq is None and isinstance(client, dict):
        raw_freq = client.get("return_frequency")

    # Case-insensitive normalization
    freq: Optional[str] = None
    if raw_freq is not None:
        norm = str(raw_freq).strip().lower()
        if norm in ("monthly", "m"):
            freq = "monthly"
        elif norm in ("quarterly", "q"):
            freq = "quarterly"
        # Anything else (e.g., 'company', '', None) evaluates strictly to None

    # GSTIN extraction
    gstin = getattr(client, "gst_number", None)
    if gstin is None and isinstance(client, dict):
        gstin = client.get("gst_number") or client.get("gstin")
    gstin_str = str(gstin or "").strip().upper()

    state_code: Optional[str] = None
    if len(gstin_str) >= 2 and gstin_str[:2].isdigit():
        state_code = gstin_str[:2]

    # Due category: X (22nd) or Y (24th)
    due_category = "X" if (state_code and state_code in CATEGORY_X_STATES) else "Y"

    # State mismatch check
    stored_state = getattr(client, "state", None)
    if stored_state is None and isinstance(client, dict):
        stored_state = client.get("state")

    state_mismatch = False
    if state_code and stored_state and state_code in GST_STATE_MAP:
        expected = GST_STATE_MAP[state_code].lower()
        st_clean = re.sub(r"[^a-z0-9]", "", str(stored_state).lower())
        exp_clean = re.sub(r"[^a-z0-9]", "", expected)
        if st_clean not in exp_clean and exp_clean not in st_clean:
            state_mismatch = True

    return {
        "frequency": freq,
        "state_code": state_code,
        "due_category": due_category,
        "state_mismatch": state_mismatch,
        "stored_frequency": raw_freq,
        "state_name": GST_STATE_MAP.get(state_code) if state_code else None,
    }


# ── Statutory Due Date Configuration (G4) ──────────────────────────────
# NOTE: Editable configuration table — verify with CA / notified extensions.
# No holiday adjustments applied automatically.
DUE_DATE_RULES = {
    "monthly": {
        "GSTR-3B": 20,  # 20th of the following month
        "GSTR-1": 11,   # 11th of the following month
        "GSTR-9": (12, 31),
    },
    "quarterly": {
        "GSTR-1": 13,   # 13th of the month following the quarter
        # GSTR-3B under QRMP scheme:
        # Category X states (22, 23, 24, 25, 26, 27, 29, 30, 31, 32, 33, 34, 35, 36, 37): 22nd
        # Category Y states (all other states/UTs): 24th
        "GSTR-3B_category_X": 22,
        "GSTR-3B_category_Y": 24,
        "GSTR-9": (12, 31),
    },
}


def calculate_due_date(
    period_end: date,
    form: str,
    frequency: str,
    state_code: Optional[str] = None,
) -> date:
    """Calculate statutory due date for a GST return form.

    Expected rules:
      - Monthly GSTR-3B Sep 2026 -> 2026-10-20
      - Monthly GSTR-1 Sep 2026 -> 2026-10-11
      - Quarterly Q2 FY 2026-27 GSTR-3B for state 27 -> 2026-10-22
      - Quarterly Q2 FY 2026-27 GSTR-3B for state 07 -> 2026-10-24
      - Quarterly GSTR-1 Q2 -> 2026-10-13
      - Monthly GSTR-3B Jul 2026 -> 2026-08-20
    """
    freq_norm = (frequency or "monthly").strip().lower()
    form_clean = (form or "GSTR-3B").strip().upper()

    if form_clean == "GSTR-9":
        due_year = period_end.year if period_end.month >= 4 else period_end.year
        return date(due_year, 12, 31)

    if period_end.month == 12:
        due_year = period_end.year + 1
        due_month = 1
    else:
        due_year = period_end.year
        due_month = period_end.month + 1

    if freq_norm == "quarterly":
        if "1" in form_clean:
            due_day = DUE_DATE_RULES["quarterly"]["GSTR-1"]
        else:
            is_cat_x = (state_code in CATEGORY_X_STATES) if state_code else True
            due_day = (
                DUE_DATE_RULES["quarterly"]["GSTR-3B_category_X"]
                if is_cat_x
                else DUE_DATE_RULES["quarterly"]["GSTR-3B_category_Y"]
            )
    else:
        # Monthly
        if "1" in form_clean:
            due_day = DUE_DATE_RULES["monthly"]["GSTR-1"]
        else:
            due_day = DUE_DATE_RULES["monthly"]["GSTR-3B"]

    return date(due_year, due_month, due_day)


def get_period_date_range(period_key: str) -> Tuple[Optional[date], Optional[date]]:
    """Parse a period key into (start_date, end_date).
    Supports:
      Quarterly: 'YYYY-Qn' (e.g., '2026-Q1', '2026-Q2', '2026-Q3', '2026-Q4')
      Monthly: 'YYYY-MM' (e.g., '2026-07', '2026-09')
    """
    if not period_key or period_key.lower() in ("all", "all available", "all_available"):
        return None, None

    p_clean = period_key.strip().upper()

    # Quarterly format: YYYY-Qn (Indian FY quarters: Q1 Apr-Jun, Q2 Jul-Sep, Q3 Oct-Dec, Q4 Jan-Mar)
    m_q = re.match(r"^(\d{4})-Q([1-4])$", p_clean)
    if m_q:
        fy = int(m_q.group(1))
        q = int(m_q.group(2))
        if q == 1:
            return date(fy, 4, 1), date(fy, 6, 30)
        elif q == 2:
            return date(fy, 7, 1), date(fy, 9, 30)
        elif q == 3:
            return date(fy, 10, 1), date(fy, 12, 31)
        elif q == 4:
            return date(fy + 1, 1, 1), date(fy + 1, 3, 31)

    # Monthly format: YYYY-MM
    m_m = re.match(r"^(\d{4})-(\d{2})$", p_clean)
    if m_m:
        year = int(m_m.group(1))
        month = int(m_m.group(2))
        if 1 <= month <= 12:
            _, last_day = calendar.monthrange(year, month)
            return date(year, month, 1), date(year, month, last_day)

    return None, None


def get_filing_options(
    db: Session,
    client: Client,
    today: Optional[date] = None,
) -> FilingOptionsResponse:
    """Retrieve eligible statutory filing periods and forms for a client based on filing profile."""
    if today is None:
        today = date.today()

    profile = get_filing_profile(client)
    freq = profile.get("frequency")

    if not freq:
        return FilingOptionsResponse(
            client_id=client.id,
            frequency=None,
            filing_profile=profile,
            periods=[],
            default_period=None,
            return_forms=[],
            reason="Set the return frequency in the client profile",
        )

    # Query earliest posted voucher date for client
    earliest_date = (
        db.query(func.min(AccountingRecord.transaction_date))
        .filter(
            AccountingRecord.client_id == client.id,
            AccountingRecord.status == "posted",
        )
        .scalar()
    )

    periods: List[FilingPeriodOption] = []

    if freq == "monthly":
        return_forms = [
            FilingReturnFormOption(code="GSTR-3B", label="GSTR-3B (Monthly)"),
            FilingReturnFormOption(code="GSTR-1", label="GSTR-1 (Monthly)"),
        ]

        # Latest completed month before today
        if today.month == 1:
            last_comp_year = today.year - 1
            last_comp_month = 12
        else:
            last_comp_year = today.year
            last_comp_month = today.month - 1

        if earliest_date:
            cur_year = earliest_date.year
            cur_month = earliest_date.month
        else:
            fy_start_year = today.year if today.month >= 4 else today.year - 1
            cur_year = fy_start_year
            cur_month = 4

        while (cur_year < last_comp_year) or (cur_year == last_comp_year and cur_month <= last_comp_month):
            m_start, m_end = get_period_date_range(f"{cur_year:04d}-{cur_month:02d}")
            if m_end and m_end < today:
                key = f"{cur_year:04d}-{cur_month:02d}"
                month_name = calendar.month_abbr[cur_month]
                label = f"{month_name} {cur_year}"

                v_count = (
                    db.query(func.count(AccountingRecord.id))
                    .filter(
                        AccountingRecord.client_id == client.id,
                        AccountingRecord.status == "posted",
                        AccountingRecord.transaction_date >= m_start,
                        AccountingRecord.transaction_date <= m_end,
                    )
                    .scalar()
                    or 0
                )
                is_nil = (v_count == 0)

                filings = (
                    db.query(GSTRecord)
                    .filter(
                        GSTRecord.client_id == client.id,
                        GSTRecord.gst_period == key,
                    )
                    .all()
                )
                is_filed = any(
                    (r.filing_status == "filed" or getattr(r, "status", None) == "filed")
                    and r.filing_status != "voided"
                    and not r.void_reason
                    for r in filings
                )
                is_voided = any(
                    r.filing_status == "voided" or r.void_reason
                    for r in filings
                )

                if is_filed:
                    status = "filed"
                    is_selectable = False
                    reason = "Already filed"
                elif is_voided:
                    status = "voided-refileable"
                    is_selectable = True
                    reason = "Previously voided - eligible to refile"
                else:
                    status = "open"
                    is_selectable = True
                    reason = None

                periods.append(
                    FilingPeriodOption(
                        key=key,
                        label=label,
                        start_date=m_start,
                        end_date=m_end,
                        status=status,
                        is_selectable=is_selectable,
                        reason=reason,
                        is_nil=is_nil,
                    )
                )

            if cur_month == 12:
                cur_year += 1
                cur_month = 1
            else:
                cur_month += 1

    else:
        # Quarterly
        return_forms = [
            FilingReturnFormOption(code="GSTR-3B", label="GSTR-3B (Quarterly)"),
            FilingReturnFormOption(code="GSTR-1", label="GSTR-1 (Quarterly)"),
        ]

        today_fy = today.year if today.month >= 4 else today.year - 1
        if earliest_date:
            start_fy = earliest_date.year if earliest_date.month >= 4 else earliest_date.year - 1
        else:
            start_fy = today_fy

        for fy in range(start_fy, today_fy + 1):
            for q in (1, 2, 3, 4):
                key = f"{fy}-Q{q}"
                q_start, q_end = get_period_date_range(key)
                if not q_end or q_end >= today:
                    continue

                q_names = {1: "Apr-Jun", 2: "Jul-Sep", 3: "Oct-Dec", 4: "Jan-Mar"}
                fy_next_short = (fy + 1) % 100
                label = f"Q{q} FY {fy}-{fy_next_short:02d} ({q_names[q]})"

                v_count = (
                    db.query(func.count(AccountingRecord.id))
                    .filter(
                        AccountingRecord.client_id == client.id,
                        AccountingRecord.status == "posted",
                        AccountingRecord.transaction_date >= q_start,
                        AccountingRecord.transaction_date <= q_end,
                    )
                    .scalar()
                    or 0
                )
                is_nil = (v_count == 0)

                filings = (
                    db.query(GSTRecord)
                    .filter(
                        GSTRecord.client_id == client.id,
                        GSTRecord.gst_period == key,
                    )
                    .all()
                )
                is_filed = any(
                    (r.filing_status == "filed" or getattr(r, "status", None) == "filed")
                    and r.filing_status != "voided"
                    and not r.void_reason
                    for r in filings
                )
                is_voided = any(
                    r.filing_status == "voided" or r.void_reason
                    for r in filings
                )

                if is_filed:
                    status = "filed"
                    is_selectable = False
                    reason = "Already filed"
                elif is_voided:
                    status = "voided-refileable"
                    is_selectable = True
                    reason = "Previously voided - eligible to refile"
                else:
                    status = "open"
                    is_selectable = True
                    reason = None

                periods.append(
                    FilingPeriodOption(
                        key=key,
                        label=label,
                        start_date=q_start,
                        end_date=q_end,
                        status=status,
                        is_selectable=is_selectable,
                        reason=reason,
                        is_nil=is_nil,
                    )
                )

    unfiled = [p for p in periods if p.status != "filed"]
    default_period = unfiled[-1].key if unfiled else (periods[-1].key if periods else None)

    return FilingOptionsResponse(
        client_id=client.id,
        frequency=freq,
        filing_profile=profile,
        periods=periods,
        default_period=default_period,
        return_forms=return_forms,
        reason=None,
    )


def get_filing_preview(
    db: Session,
    client: Client,
    period: str,
    form: str,
    user: User,
    today: Optional[date] = None,
) -> FilingPreviewResponse:
    """Compute statutory preview figures and blockers for a selected period and form.
    Reuses the exact same calculation services as the GST tab.
    """
    if today is None:
        today = date.today()

    profile = get_filing_profile(client)
    freq = profile.get("frequency")
    state_code = profile.get("state_code")

    p_clean = (period or "").strip()
    f_clean = (form or "GSTR-3B").strip().upper()
    if f_clean not in ("GSTR-3B", "GSTR-1"):
        f_clean = "GSTR-3B"

    start_d, end_d = get_period_date_range(p_clean)
    is_quarter = "Q" in p_clean.upper()
    period_type = "quarterly" if is_quarter else "monthly"

    blockers: List[FilingBlocker] = []

    # 1. Frequency not set
    if not freq:
        blockers.append(
            FilingBlocker(code="FREQUENCY_NOT_SET", message="Set the return frequency in the client profile")
        )
    # 2. Frequency mismatch
    elif freq == "quarterly" and not is_quarter:
        blockers.append(
            FilingBlocker(code="FREQUENCY_MISMATCH", message=f"Period '{p_clean}' does not match client's Quarterly return frequency.")
        )
    elif freq == "monthly" and is_quarter:
        blockers.append(
            FilingBlocker(code="FREQUENCY_MISMATCH", message=f"Period '{p_clean}' does not match client's Monthly return frequency.")
        )

    # 3. Period not ended
    if not end_d or end_d >= today:
        blockers.append(
            FilingBlocker(
                code="PERIOD_NOT_ENDED",
                message=f"Period '{p_clean}' has not ended yet (period ends on {end_d}, today is {today}). Filings can only be recorded after the period has closed.",
            )
        )

    # 4. Already filed
    filing = (
        db.query(GSTRecord)
        .filter(
            GSTRecord.client_id == client.id,
            GSTRecord.gst_period == p_clean,
            GSTRecord.gst_type == f_clean,
            GSTRecord.filing_status == "filed",
        )
        .first()
    )
    if filing and filing.filing_status != "voided" and not filing.void_reason:
        blockers.append(
            FilingBlocker(
                code="ALREADY_FILED",
                message=f"Filing record already exists for {f_clean} period {p_clean} (Status: {filing.filing_status}). Duplicate filing rejected.",
            )
        )

    # Use the SAME service as the GST tab for exact mathematical parity
    from app.services.gst_reconciliation_service import GstReconciliationService

    g3b = GstReconciliationService.generate_gstr3b(
        db=db,
        client_id=client.id,
        user=user,
        period=p_clean,
    )

    if f_clean == "GSTR-3B":
        taxable_value = g3b.table_3_1_outward.taxable_value
        liability_igst = g3b.table_3_1_outward.igst + g3b.itc_reversal_payable_igst
        liability_cgst = g3b.table_3_1_outward.cgst + g3b.itc_reversal_payable_cgst
        liability_sgst = g3b.table_3_1_outward.sgst + g3b.itc_reversal_payable_sgst
        liability_cess = g3b.table_3_1_outward.cess
        total_liability = liability_igst + liability_cgst + liability_sgst + liability_cess

        credit_igst = g3b.table_4_itc_available.igst
        credit_cgst = g3b.table_4_itc_available.cgst
        credit_sgst = g3b.table_4_itc_available.sgst
        credit_cess = g3b.table_4_itc_available.cess
        total_credit = credit_igst + credit_cgst + credit_sgst + credit_cess

        cash_payable_igst = g3b.cash_payable_igst
        cash_payable_cgst = g3b.cash_payable_cgst
        cash_payable_sgst = g3b.cash_payable_sgst
        total_cash_payable = g3b.tax_payable_in_cash

        itc_reversal_payable_igst = g3b.itc_reversal_payable_igst
        itc_reversal_payable_cgst = g3b.itc_reversal_payable_cgst
        itc_reversal_payable_sgst = g3b.itc_reversal_payable_sgst
        itc_reversal_payable_total = g3b.itc_reversal_payable_total

        excess_credit_carried_forward = g3b.excess_credit_carried_forward
        itc_carried_forward_igst = g3b.itc_carried_forward_igst
        itc_carried_forward_cgst = g3b.itc_carried_forward_cgst
        itc_carried_forward_sgst = g3b.itc_carried_forward_sgst

        # Outward negative liability check
        if (
            g3b.table_3_1_outward.taxable_value < 0
            or g3b.table_3_1_outward.igst < 0
            or g3b.table_3_1_outward.cgst < 0
            or g3b.table_3_1_outward.sgst < 0
        ):
            blockers.append(
                FilingBlocker(
                    code="NEGATIVE_OUTWARD_LIABILITY",
                    message="Outward tax liability or taxable turnover is negative. Under statutory rules, return filings cannot be submitted with negative liability.",
                )
            )

    else:
        # GSTR-1
        g1 = GstReconciliationService.reconcile_gstr1(
            db=db,
            client_id=client.id,
            user=user,
            period=p_clean,
        )
        taxable_value = g1.total_outward_taxable
        liability_igst = g1.total_outward_igst
        liability_cgst = g1.total_outward_cgst
        liability_sgst = g1.total_outward_sgst
        liability_cess = getattr(g1, "total_outward_cess", Decimal("0.00"))
        total_liability = g1.total_outward_tax

        credit_igst = Decimal("0.00")
        credit_cgst = Decimal("0.00")
        credit_sgst = Decimal("0.00")
        credit_cess = Decimal("0.00")
        total_credit = Decimal("0.00")

        cash_payable_igst = Decimal("0.00")
        cash_payable_cgst = Decimal("0.00")
        cash_payable_sgst = Decimal("0.00")
        total_cash_payable = g1.total_outward_tax

        itc_reversal_payable_igst = Decimal("0.00")
        itc_reversal_payable_cgst = Decimal("0.00")
        itc_reversal_payable_sgst = Decimal("0.00")
        itc_reversal_payable_total = Decimal("0.00")

        excess_credit_carried_forward = Decimal("0.00")
        itc_carried_forward_igst = Decimal("0.00")
        itc_carried_forward_cgst = Decimal("0.00")
        itc_carried_forward_sgst = Decimal("0.00")

        if g1.total_outward_taxable < 0 or g1.total_outward_tax < 0:
            blockers.append(
                FilingBlocker(
                    code="NEGATIVE_OUTWARD_LIABILITY",
                    message="Outward tax liability or taxable turnover is negative. Under statutory rules, return filings cannot be submitted with negative liability.",
                )
            )

    # Discrepancy checks (active HIGH discrepancies only)
    disc_rep = GstReconciliationService.detect_discrepancies(
        db=db,
        client_id=client.id,
        user=user,
        period=p_clean,
    )
    active_high = [
        d for d in disc_rep.discrepancies
        if d.severity == "HIGH" and d.rule_code != "DUPLICATE_REJECTED"
    ]
    if len(active_high) > 0:
        blockers.append(
            FilingBlocker(
                code="HIGH_DISCREPANCY",
                message=f"{len(active_high)} unresolved high-risk discrepancy(ies) detected for this period. Resolve all discrepancies in the Discrepancies tab before recording statutory return filing.",
            )
        )

    due_d_date = calculate_due_date(
        period_end=end_d if end_d else today,
        form=f_clean,
        frequency=freq or "monthly",
        state_code=state_code,
    )

    is_nil_return = (taxable_value == Decimal("0.00") and total_liability == Decimal("0.00") and total_credit == Decimal("0.00"))

    return FilingPreviewResponse(
        client_id=client.id,
        period=p_clean,
        form=f_clean,
        period_type=period_type,
        period_start=start_d or today,
        period_end=end_d or today,
        taxable_value=taxable_value,
        liability_igst=liability_igst,
        liability_cgst=liability_cgst,
        liability_sgst=liability_sgst,
        liability_cess=liability_cess,
        total_liability=total_liability,
        credit_igst=credit_igst,
        credit_cgst=credit_cgst,
        credit_sgst=credit_sgst,
        credit_cess=credit_cess,
        total_credit=total_credit,
        cash_payable_igst=cash_payable_igst,
        cash_payable_cgst=cash_payable_cgst,
        cash_payable_sgst=cash_payable_sgst,
        total_cash_payable=total_cash_payable,
        itc_reversal_payable_igst=itc_reversal_payable_igst,
        itc_reversal_payable_cgst=itc_reversal_payable_cgst,
        itc_reversal_payable_sgst=itc_reversal_payable_sgst,
        itc_reversal_payable_total=itc_reversal_payable_total,
        excess_credit_carried_forward=excess_credit_carried_forward,
        itc_carried_forward_igst=itc_carried_forward_igst,
        itc_carried_forward_cgst=itc_carried_forward_cgst,
        itc_carried_forward_sgst=itc_carried_forward_sgst,
        due_date=due_d_date.isoformat(),
        is_nil_return=is_nil_return,
        blockers=blockers,
    )

