"""
Reports API Router — Statutory and Management Financial Reports:
- Profit & Loss Statement (Income Statement)
- Balance Sheet (Financial Position)
- Audit Drill-Down to Vouchers and Source Documents
Mounted under /api/v1/reports.
"""

import uuid
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.financial_statements_service import FinancialStatementsService
from app.services.report_service import ReportService
from app.schemas.financial_reports import (
    ProfitAndLossResponse,
    BalanceSheetResponse,
    DrillDownResponse,
    CashFlowResponse,
    GstSummaryReportResponse,
    IntegrityAuditReportResponse,
    ClientReportsSummaryResponse,
)
from app.schemas.common import APIResponse

router = APIRouter()


@router.get("/", summary="Reports Module Health & Status")
async def get_reports_status():
    """Reports module health check."""
    return {
        "module": "reports",
        "status": "active",
        "supported": [
            "profit-and-loss",
            "balance-sheet",
            "cash-flow",
            "gst-summary",
            "integrity-audit",
            "client-summary",
            "drilldown",
        ],
    }


@router.get(
    "/profit-and-loss",
    response_model=APIResponse[ProfitAndLossResponse],
    summary="Generate Profit & Loss Statement (Income Statement)",
)
def get_profit_and_loss(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate Profit & Loss Statement with Gross Profit and Net Profit margins."""
    start = from_date or date(date.today().year, 4, 1)  # Default Indian FY start (April 1)
    end = to_date or date.today()

    pnl = FinancialStatementsService.generate_profit_and_loss(
        db=db,
        client_id=client_id,
        user=current_user,
        from_date=start,
        to_date=end,
    )
    return APIResponse(
        success=True,
        message="Profit & Loss Statement generated successfully.",
        data=pnl,
    )


@router.get(
    "/balance-sheet",
    response_model=APIResponse[BalanceSheetResponse],
    summary="Generate Balance Sheet (Statement of Financial Position)",
)
def get_balance_sheet(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    as_of_date: Optional[date] = Query(None, description="As of date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate balanced Balance Sheet with dynamic Net Profit equity transfer."""
    bs = FinancialStatementsService.generate_balance_sheet(
        db=db,
        client_id=client_id,
        user=current_user,
        as_of_date=as_of_date,
    )
    return APIResponse(
        success=True,
        message="Balance Sheet generated successfully.",
        data=bs,
    )


@router.get(
    "/drilldown/{account_id}",
    response_model=APIResponse[DrillDownResponse],
    summary="Audit Drill-Down from Financial Report Line Item to Vouchers",
)
def get_report_drilldown(
    account_id: uuid.UUID,
    client_id: uuid.UUID = Query(..., description="Client ID"),
    from_date: Optional[date] = Query(None, description="Start date filter"),
    to_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Drill down into underlying transactions, journal entries, vouchers, and source documents."""
    drill = FinancialStatementsService.get_report_drilldown(
        db=db,
        client_id=client_id,
        account_id=account_id,
        user=current_user,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message=f"Drill-down for account {drill.account_code} ({drill.account_name}) retrieved successfully.",
        data=drill,
    )


@router.get(
    "/cash-flow",
    response_model=APIResponse[CashFlowResponse],
    summary="Generate Cash Flow Statement (ICAI AS-3)",
)
def get_cash_flow(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate reconciled Cash Flow Statement covering Operating, Investing, and Financing activities."""
    cf = ReportService.generate_cash_flow(
        db=db,
        client_id=client_id,
        user=current_user,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message="Cash Flow Statement generated successfully.",
        data=cf,
    )


@router.get(
    "/gst-summary",
    response_model=APIResponse[GstSummaryReportResponse],
    summary="Generate Comprehensive GST Summary Report",
)
def get_gst_summary(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate statutory GST Summary Report integrating GSTR-1, GSTR-2B, and GSTR-3B with filing tracking."""
    gst_rep = ReportService.generate_gst_summary(
        db=db,
        client_id=client_id,
        user=current_user,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message="GST Summary Report generated successfully.",
        data=gst_rep,
    )


@router.get(
    "/integrity-audit",
    response_model=APIResponse[IntegrityAuditReportResponse],
    summary="Run Statutory Data Integrity, Anti-Fraud & Cross-Module Parity Audit",
)
def get_integrity_audit(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    as_of_date: Optional[date] = Query(None, description="Audit date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Multi-point audit checking double-entry balance, duplicates, math errors, and unposted vouchers."""
    audit_rep = ReportService.generate_integrity_audit(
        db=db,
        client_id=client_id,
        user=current_user,
        as_of_date=as_of_date,
    )
    return APIResponse(
        success=True,
        message="Data Integrity and Anti-Fraud Audit completed successfully.",
        data=audit_rep,
    )


@router.get(
    "/client-summary",
    response_model=APIResponse[ClientReportsSummaryResponse],
    summary="Client Workspace Unified Reports Summary",
)
def get_client_reports_summary(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unified master headline summary for all client reports and integrity status."""
    summary_rep = ReportService.generate_client_reports_summary(
        db=db,
        client_id=client_id,
        user=current_user,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message="Client reports summary generated successfully.",
        data=summary_rep,
    )

