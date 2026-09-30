"""
General Ledger API Router — Account ledgers, running balance calculation, and GL summary.
Mounted under /api/v1/accounting/ledger.
"""

import uuid
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.general_ledger_service import GeneralLedgerService
from app.schemas.general_ledger import (
    AccountLedgerResponse,
    GeneralLedgerSummaryResponse,
)
from app.schemas.common import APIResponse

router = APIRouter()


@router.get(
    "/summary",
    response_model=APIResponse[GeneralLedgerSummaryResponse],
    summary="Get General Ledger Summary for all accounts",
)
def get_general_ledger_summary(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    from_date: Optional[date] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date filter (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve turnover and closing balances across all accounts for a client."""
    summary = GeneralLedgerService.get_general_ledger_summary(
        db=db,
        client_id=client_id,
        user=current_user,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message="General ledger summary calculated successfully.",
        data=summary,
    )


@router.get(
    "/account/{account_id}",
    response_model=APIResponse[AccountLedgerResponse],
    summary="Get Detailed Ledger and Running Balance for a Specific Account",
)
def get_account_ledger(
    account_id: uuid.UUID,
    client_id: uuid.UUID = Query(..., description="Client ID"),
    from_date: Optional[date] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date filter (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve detailed transaction ledger with sequential running balance for an account."""
    ledger = GeneralLedgerService.get_account_ledger(
        db=db,
        client_id=client_id,
        account_id=account_id,
        user=current_user,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message=f"Ledger for account {ledger.account_code} ({ledger.account_name}) retrieved successfully.",
        data=ledger,
    )
