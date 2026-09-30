"""
Journal Entries API Router — Endpoints for Double-Entry Journal Entry Postings and Inquiries.
Mounted under /api/v1/accounting/entries.
"""

import uuid
from typing import Optional, List
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.journal_entry_service import JournalEntryService
from app.schemas.journal_entry import (
    JournalEntryCreate,
    JournalEntryResponse,
    JournalEntryDetailResponse,
    JournalReversalRequest,
    JournalEntryLineResponse,
)
from app.schemas.common import APIResponse

router = APIRouter()


@router.get(
    "/",
    response_model=APIResponse[List[JournalEntryResponse]],
    summary="List Journal Entries for a Client",
)
def list_journal_entries(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    entry_type: Optional[str] = Query(None, description="Filter by entry type (sales, purchase, etc.)"),
    status: Optional[str] = Query(None, description="Filter by status (posted, reversed, etc.)"),
    from_date: Optional[date] = Query(None, description="Start date filter"),
    to_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve list of double-entry journal entries for a client."""
    entries = JournalEntryService.get_journal_entries(
        db,
        client_id=client_id,
        user=current_user,
        entry_type=entry_type,
        status=status,
        from_date=from_date,
        to_date=to_date,
    )
    return APIResponse(
        success=True,
        message=f"Retrieved {len(entries)} journal entries.",
        data=[JournalEntryResponse.model_validate(e) for e in entries],
    )


@router.get(
    "/{entry_id}",
    response_model=APIResponse[JournalEntryDetailResponse],
    summary="Get Detailed Journal Entry with Lines",
)
def get_journal_entry_detail(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve detailed journal entry including all debit and credit lines."""
    entry = JournalEntryService.get_journal_entry_by_id(db, entry_id, current_user)

    lines_resp: List[JournalEntryLineResponse] = []
    for line in entry.lines:
        line_item = JournalEntryLineResponse(
            id=line.id,
            journal_entry_id=line.journal_entry_id,
            line_number=line.line_number,
            account_id=line.account_id,
            debit_amount=line.debit_amount,
            credit_amount=line.credit_amount,
            description=line.description,
            party_name=line.party_name,
            party_gstin=line.party_gstin,
            tax_head=line.tax_head,
            tax_rate=line.tax_rate,
            created_at=line.created_at,
            account_code=line.account.account_code if line.account else None,
            account_name=line.account.account_name if line.account else None,
        )
        lines_resp.append(line_item)

    data = JournalEntryDetailResponse(
        id=entry.id,
        client_id=entry.client_id,
        accounting_record_id=entry.accounting_record_id,
        document_id=entry.document_id,
        entry_number=entry.entry_number,
        entry_date=entry.entry_date,
        entry_type=entry.entry_type,
        status=entry.status,
        narration=entry.narration,
        reference_number=entry.reference_number,
        total_debit=entry.total_debit,
        total_credit=entry.total_credit,
        is_balanced=entry.is_balanced,
        posted_at=entry.posted_at,
        posted_by_user_id=entry.posted_by_user_id,
        is_reversed=entry.is_reversed,
        reversal_entry_id=entry.reversal_entry_id,
        reversal_reason=entry.reversal_reason,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        lines=lines_resp,
    )

    return APIResponse(
        success=True,
        message="Journal entry retrieved successfully.",
        data=data,
    )


@router.post(
    "/",
    response_model=APIResponse[JournalEntryDetailResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record Manual Journal Entry",
)
def create_manual_journal_entry(
    payload: JournalEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post an authorized, balanced manual journal voucher to the ledger."""
    entry = JournalEntryService.create_journal_entry(
        db,
        client_id=payload.client_id,
        payload=payload,
        user=current_user,
    )
    return APIResponse(
        success=True,
        message=f"Journal entry {entry.entry_number} posted successfully.",
        data=JournalEntryDetailResponse.model_validate(entry),
    )


@router.post(
    "/{entry_id}/reverse",
    response_model=APIResponse[JournalEntryDetailResponse],
    summary="Reverse a Posted Journal Entry",
)
def reverse_journal_entry(
    entry_id: uuid.UUID,
    payload: JournalReversalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a balancing audit reversal entry for an existing posted journal entry."""
    reversal = JournalEntryService.reverse_journal_entry(
        db,
        entry_id=entry_id,
        reason=payload.reversal_reason,
        user=current_user,
    )
    return APIResponse(
        success=True,
        message=f"Journal entry reversed successfully with reversal entry {reversal.entry_number}.",
        data=JournalEntryDetailResponse.model_validate(reversal),
    )
