"""
GST API Router
Phase 7 — GST Reconciliation (GSTR-1, GSTR-2B, GSTR-3B),
Discrepancy Detection Engine, CA Financial Insights, and GST return record tracking.
Mounted under /api/v1/gst.
"""

import uuid
from typing import Optional, List
from datetime import date, datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.gst_record import GSTRecord
from app.models.accounting_period import AccountingPeriod
from app.core.exceptions import NotFoundException, BadRequestException
from app.schemas.common import APIResponse
from app.schemas.gst import GSTRecordResponse, GSTRecordCreate
from app.schemas.gst_reconciliation import (
    Gstr1ReconciliationResponse,
    Gstr1HsnSummaryResponse,
    Gstr2bReconciliationResponse,
    Gstr3bResponse,
    GstDiscrepancyReportResponse,
    GstFinancialInsightsResponse,
)
from app.services.gst_reconciliation_service import GstReconciliationService

router = APIRouter()


@router.get("", summary="GST Module Status")
@router.get("/", summary="GST Module Status")
def get_gst_module_info():
    return {
        "module": "gst",
        "status": "active",
        "features": [
            "gstr1_reconciliation",
            "table12_hsn_summary",
            "gstr2b_itc_reconciliation",
            "gstr3b_summary",
            "discrepancy_detection",
            "financial_insights",
            "gst_records_tracking",
        ],
    }


# ── 1. GSTR-1 Outward Supplies Reconciliation ─────────────────────────

@router.get(
    "/reconciliation/gstr1",
    response_model=APIResponse[Gstr1ReconciliationResponse],
    summary="Reconcile Outward Supplies with General Ledger (GSTR-1)",
)
def reconcile_gstr1(
    client_id: uuid.UUID = Query(..., description="Target Client UUID"),
    period: Optional[str] = Query(None, description="Filing Period (e.g. 2026-07)"),
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = GstReconciliationService.reconcile_gstr1(
        db=db,
        client_id=client_id,
        user=current_user,
        period=period,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message="GSTR-1 reconciliation generated successfully",
        data=result,
    )


# ── 1b. GSTR-1 Table 12 HSN/SAC Summary ───────────────────────────────

@router.get(
    "/reconciliation/table12-hsn",
    response_model=APIResponse[Gstr1HsnSummaryResponse],
    summary="Get GSTR-1 Table 12 HSN/SAC Summary dynamically aggregated from posted outward ledgers",
)
def get_table12_hsn_summary(
    client_id: uuid.UUID = Query(..., description="Target Client UUID"),
    period: Optional[str] = Query(None, description="Filing Period (e.g. 2026-07)"),
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = GstReconciliationService.get_gstr1_table_12_hsn_summary(
        db=db,
        client_id=client_id,
        user=current_user,
        period=period,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message="GSTR-1 Table 12 HSN/SAC summary generated successfully",
        data=result,
    )


# ── 2. GSTR-2B Inward & ITC Reconciliation ────────────────────────────

@router.get(
    "/reconciliation/gstr2b",
    response_model=APIResponse[Gstr2bReconciliationResponse],
    summary="Reconcile Inward Invoices and Input Tax Credit (GSTR-2B)",
)
def reconcile_gstr2b(
    client_id: uuid.UUID = Query(..., description="Target Client UUID"),
    period: Optional[str] = Query(None, description="Filing Period (e.g. 2026-07)"),
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = GstReconciliationService.reconcile_gstr2b(
        db=db,
        client_id=client_id,
        user=current_user,
        period=period,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message="GSTR-2B ITC reconciliation generated successfully",
        data=result,
    )


# ── 3. GSTR-3B Monthly Return Summary ─────────────────────────────────

@router.get(
    "/reconciliation/gstr3b",
    response_model=APIResponse[Gstr3bResponse],
    summary="Generate Consolidated GSTR-3B Return Summary",
)
def generate_gstr3b(
    client_id: uuid.UUID = Query(..., description="Target Client UUID"),
    period: Optional[str] = Query(None, description="Filing Period (e.g. 2026-07)"),
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = GstReconciliationService.generate_gstr3b(
        db=db,
        client_id=client_id,
        user=current_user,
        period=period,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message="GSTR-3B statement computed successfully",
        data=result,
    )


# ── 4. Discrepancy Detection Engine ──────────────────────────────────

@router.get(
    "/reconciliation/discrepancies",
    response_model=APIResponse[GstDiscrepancyReportResponse],
    summary="Detect Invoice and Ledger Discrepancies for CA Review",
)
def detect_discrepancies(
    client_id: uuid.UUID = Query(..., description="Target Client UUID"),
    period: Optional[str] = Query(None, description="Filing Period (e.g. 2026-07)"),
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = GstReconciliationService.detect_discrepancies(
        db=db,
        client_id=client_id,
        user=current_user,
        period=period,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message="GST discrepancy detection completed",
        data=result,
    )


# ── 5. Financial Insights & CA Review ─────────────────────────────────

@router.get(
    "/reconciliation/insights",
    response_model=APIResponse[GstFinancialInsightsResponse],
    summary="Generate Explainable CA Review Insights and Compliance Score",
)
def get_financial_insights(
    client_id: uuid.UUID = Query(..., description="Target Client UUID"),
    period: Optional[str] = Query(None, description="Filing Period (e.g. 2026-07)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = GstReconciliationService.get_financial_insights(
        db=db,
        client_id=client_id,
        user=current_user,
        period=period,
    )
    return APIResponse(
        success=True,
        message="GST financial insights and CA observations generated",
        data=result,
    )


# ── 6. GST Filing Records Management ──────────────────────────────────

@router.get(
    "/records/{client_id}",
    response_model=APIResponse[List[GSTRecordResponse]],
    summary="List GST Filing Records for Client",
)
def list_gst_records(
    client_id: uuid.UUID,
    period: Optional[str] = Query(None, description="Filter by period"),
    gst_type: Optional[str] = Query(None, description="Filter by GST type (GSTR-1, GSTR-3B)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    GstReconciliationService.verify_client_access(db, client_id, current_user)
    query = db.query(GSTRecord).filter(GSTRecord.client_id == client_id)
    if period:
        query = query.filter(GSTRecord.gst_period == period)
    if gst_type:
        query = query.filter(GSTRecord.gst_type == gst_type)

    records = query.order_by(GSTRecord.created_at.desc()).all()
    return APIResponse(
        success=True,
        message="GST records retrieved successfully",
        data=records,
    )


@router.post(
    "/records",
    response_model=APIResponse[GSTRecordResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record or Update GST Filing Record",
)
def create_gst_record(
    payload: GSTRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    GstReconciliationService.verify_client_access(db, payload.client_id, current_user)

    # 1. Reject duplicate filing for same client, period, and return type
    existing = (
        db.query(GSTRecord)
        .filter(
            GSTRecord.client_id == payload.client_id,
            GSTRecord.gst_period == payload.gst_period,
            GSTRecord.gst_type == payload.gst_type,
            GSTRecord.filing_status != "voided",
        )
        .first()
    )
    if existing:
        raise BadRequestException(
            detail=f"Filing record already exists for {payload.gst_type} period {payload.gst_period} (Status: {existing.filing_status}). Duplicate filing rejected."
        )

    # 2. Derive figures from ledger if not provided or 0
    start_d, end_d = GstReconciliationService._parse_period_dates(payload.gst_period, None, None)
    taxable_amount = payload.taxable_amount
    cgst = payload.cgst
    sgst = payload.sgst
    igst = payload.igst
    total_tax = payload.total_tax

    if taxable_amount is None or taxable_amount == Decimal("0.00"):
        if payload.gst_type == "GSTR-1":
            recon = GstReconciliationService.reconcile_gstr1(
                db, payload.client_id, current_user, period=payload.gst_period
            )
            taxable_amount = recon.total_outward_taxable
            cgst = recon.total_outward_cgst
            sgst = recon.total_outward_sgst
            igst = recon.total_outward_igst
            total_tax = recon.total_outward_tax
        elif payload.gst_type == "GSTR-3B":
            g3b = GstReconciliationService.generate_gstr3b(
                db, payload.client_id, current_user, period=payload.gst_period
            )
            taxable_amount = g3b.table_3_1_outward.taxable_value
            cgst = g3b.table_3_1_outward.cgst
            sgst = g3b.table_3_1_outward.sgst
            igst = g3b.table_3_1_outward.igst
            total_tax = g3b.tax_payable_in_cash

    if total_tax is None:
        total_tax = cgst + sgst + igst

    record = GSTRecord(
        id=uuid.uuid4(),
        client_id=payload.client_id,
        gst_period=payload.gst_period,
        gst_type=payload.gst_type,
        taxable_amount=taxable_amount,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        total_tax=total_tax,
        filing_status=payload.filing_status,
        due_date=payload.due_date,
    )
    db.add(record)

    # 3. Lock period if filing status is filed
    if payload.filing_status.lower() in ("filed", "completed") and start_d and end_d:
        acc_period = (
            db.query(AccountingPeriod)
            .filter(
                AccountingPeriod.client_id == payload.client_id,
                AccountingPeriod.start_date == start_d,
                AccountingPeriod.end_date == end_d,
            )
            .first()
        )
        if not acc_period:
            acc_period = AccountingPeriod(
                id=uuid.uuid4(),
                client_id=payload.client_id,
                period_name=f"Period {payload.gst_period}",
                start_date=start_d,
                end_date=end_d,
                status="locked",
                is_closed=True,
                closed_at=datetime.now(timezone.utc),
                closed_by_user_id=current_user.id,
                closing_notes=f"Auto-locked upon filing {payload.gst_type} for period {payload.gst_period}",
            )
            db.add(acc_period)
        else:
            acc_period.status = "locked"
            acc_period.is_closed = True
            acc_period.closing_notes = f"Locked upon filing {payload.gst_type} for period {payload.gst_period}"

    db.commit()
    db.refresh(record)

    return APIResponse(
        success=True,
        message="GST record created successfully",
        data=record,
    )
