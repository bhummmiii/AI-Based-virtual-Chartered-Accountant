"""
Chart of Accounts API Router — Endpoints for managing client-specific accounts.
Full JWT authentication and client authorization enforced.
"""

import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.schemas.chart_of_accounts import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountTreeNodeResponse,
    DefaultCoaInitResponse,
)
from app.schemas.common import APIResponse

router = APIRouter()


@router.post(
    "/initialize/{client_id}",
    response_model=APIResponse[DefaultCoaInitResponse],
    summary="Idempotently initialize default ICAI Chart of Accounts",
)
def initialize_default_accounts(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Idempotently seeds standard ICAI accounts (Assets, Liabilities, Equity, Revenue, Expenses)
    for the specified client. Existing customized accounts are never overwritten.
    """
    res = ChartOfAccountsService.initialize_default_accounts(db, client_id, current_user)
    return APIResponse(
        success=True,
        message=res.message,
        data=res,
    )


@router.get(
    "",
    response_model=APIResponse[List[AccountResponse]],
    summary="List Chart of Accounts for a client",
)
def list_accounts(
    client_id: uuid.UUID = Query(..., description="Target client ID"),
    account_type: Optional[str] = Query(None, description="Filter by type: asset | liability | equity | revenue | expense"),
    include_inactive: bool = Query(False, description="Include deactivated accounts"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all accounts for a client as a flat list ordered by account code."""
    accounts = ChartOfAccountsService.get_accounts(
        db,
        client_id=client_id,
        user=current_user,
        account_type=account_type,
        include_inactive=include_inactive,
    )
    return APIResponse(
        success=True,
        message=f"Retrieved {len(accounts)} account(s).",
        data=[AccountResponse.model_validate(a) for a in accounts],
    )


@router.get(
    "/tree",
    response_model=APIResponse[List[AccountTreeNodeResponse]],
    summary="Get hierarchical account tree for a client",
)
def get_account_tree(
    client_id: uuid.UUID = Query(..., description="Target client ID"),
    include_inactive: bool = Query(False, description="Include deactivated accounts"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve client accounts structured as a nested parent-subaccount tree."""
    tree = ChartOfAccountsService.get_account_tree(
        db,
        client_id=client_id,
        user=current_user,
        include_inactive=include_inactive,
    )
    return APIResponse(
        success=True,
        message=f"Retrieved {len(tree)} root account group(s).",
        data=tree,
    )


@router.post(
    "",
    response_model=APIResponse[AccountResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create custom account",
)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new custom account with code/name uniqueness and parent validation."""
    account = ChartOfAccountsService.create_account(db, payload, current_user)
    return APIResponse(
        success=True,
        message=f"Account '{account.account_name}' ({account.account_code}) created successfully.",
        data=AccountResponse.model_validate(account),
    )


@router.get(
    "/{account_id}",
    response_model=APIResponse[AccountResponse],
    summary="Get single account details",
)
def get_account(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve details of a single account by ID."""
    account = ChartOfAccountsService.get_account_by_id(db, account_id, current_user)
    return APIResponse(
        success=True,
        message="Account retrieved successfully.",
        data=AccountResponse.model_validate(account),
    )


@router.patch(
    "/{account_id}",
    response_model=APIResponse[AccountResponse],
    summary="Update account",
)
def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update account details, parent hierarchy, or active status."""
    account = ChartOfAccountsService.update_account(db, account_id, payload, current_user)
    return APIResponse(
        success=True,
        message=f"Account '{account.account_name}' updated successfully.",
        data=AccountResponse.model_validate(account),
    )


@router.delete(
    "/{account_id}",
    response_model=APIResponse[dict],
    summary="Delete custom account",
)
def delete_account(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a custom account (system accounts and parent accounts with children are protected)."""
    ChartOfAccountsService.delete_account(db, account_id, current_user)
    return APIResponse(
        success=True,
        message="Account deleted successfully.",
        data={"account_id": str(account_id), "deleted": True},
    )
