"""
Trial Balance & Period Control API Router — Endpoints for Trial Balance generation,
financial health checks, duplicate reference detection, and accounting period lockout.
Mounted under /api/v1/accounting/trial-balance.
"""

import uuid
from typing import Optional, List
from datetime import date
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.trial_balance_service import TrialBalanceService
from app.schemas.trial_balance import (
    TrialBalanceResponse,
    AccountingPeriodCreate,
    AccountingPeriodResponse,
)
from app.schemas.common import APIResponse

router = APIRouter()


class ClosePeriodRequest(BaseModel):
    notes: Optional[str] = None


@router.get(
    "/",
    response_model=APIResponse[TrialBalanceResponse],
    summary="Generate Trial Balance and Financial Health Check",
)
def get_trial_balance(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    as_of_date: Optional[date] = Query(None, description="As of date (YYYY-MM-DD)"),
    from_date: Optional[date] = Query(None, description="Start date of period (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date of period (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate complete, double-entry Trial Balance with classified groups and health audit checks."""
    tb = TrialBalanceService.generate_trial_balance(
        db=db,
        client_id=client_id,
        user=current_user,
        as_of_date=as_of_date,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message="Trial Balance generated successfully.",
        data=tb,
    )


@router.get(
    "/periods",
    response_model=APIResponse[List[AccountingPeriodResponse]],
    summary="List Accounting Periods for Client",
)
def list_accounting_periods(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all defined accounting periods and their open/closed status."""
    periods = TrialBalanceService.list_periods(db, client_id, current_user)
    return APIResponse(
        success=True,
        message=f"Retrieved {len(periods)} accounting periods.",
        data=[AccountingPeriodResponse.model_validate(p) for p in periods],
    )


@router.post(
    "/periods",
    response_model=APIResponse[AccountingPeriodResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create Accounting Period",
)
def create_accounting_period(
    payload: AccountingPeriodCreate,
    client_id: uuid.UUID = Query(..., description="Client ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Define a fiscal accounting period (e.g. FY 2025-26, Q1, Month)."""
    period = TrialBalanceService.create_period(db, client_id, current_user, payload)
    return APIResponse(
        success=True,
        message=f"Accounting period '{period.period_name}' created successfully.",
        data=AccountingPeriodResponse.model_validate(period),
    )


@router.post(
    "/periods/{period_id}/close",
    response_model=APIResponse[AccountingPeriodResponse],
    summary="Close and Lock Accounting Period",
)
def close_accounting_period(
    period_id: uuid.UUID,
    payload: Optional[ClosePeriodRequest] = None,
    client_id: uuid.UUID = Query(..., description="Client ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lock an accounting period to prevent retroactive changes and new postings."""
    notes = payload.notes if payload else None
    period = TrialBalanceService.close_period(db, client_id, period_id, current_user, notes)
    return APIResponse(
        success=True,
        message=f"Accounting period '{period.period_name}' locked and closed.",
        data=AccountingPeriodResponse.model_validate(period),
    )


@router.post(
    "/periods/{period_id}/reopen",
    response_model=APIResponse[AccountingPeriodResponse],
    summary="Reopen a Closed Accounting Period",
)
def reopen_accounting_period(
    period_id: uuid.UUID,
    client_id: uuid.UUID = Query(..., description="Client ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reopen a previously closed accounting period (authorized CA/Admin only)."""
    period = TrialBalanceService.reopen_period(db, client_id, period_id, current_user)
    return APIResponse(
        success=True,
        message=f"Accounting period '{period.period_name}' reopened successfully.",
        data=AccountingPeriodResponse.model_validate(period),
    )
