# ============================================================
# Accounting API Router — Verified Document to Draft Bridge
# ============================================================

import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.accounting_draft_service import AccountingDraftService
from app.schemas.accounting import (
    AccountingRecordResponse,
    DraftGenerateResponse,
    DraftPostResponse,
    DraftBulkPostRequest,
    DraftBulkPostResponse,
)
from app.schemas.common import APIResponse
from app.api.routers.accounting.coa_router import router as coa_router
from app.api.routers.accounting.journal_router import router as journal_router
from app.api.routers.accounting.ledger_router import router as ledger_router
from app.api.routers.accounting.trial_balance_router import router as trial_balance_router
from app.api.routers.accounting.voucher_router import router as voucher_router
from app.models.journal_entry import JournalEntry
from app.services.journal_entry_service import JournalEntryService
from app.schemas.journal_entry import JournalEntryDetailResponse, JournalEntryLineResponse

router = APIRouter()

router.include_router(coa_router, prefix="/coa", tags=["Chart of Accounts"])
router.include_router(journal_router, prefix="/entries", tags=["Journal Entries"])
router.include_router(ledger_router, prefix="/ledger", tags=["General Ledger"])
router.include_router(trial_balance_router, prefix="/trial-balance", tags=["Trial Balance & Period Controls"])
router.include_router(voucher_router, prefix="/vouchers", tags=["Vouchers & Outstanding"])



@router.get("/", summary="Accounting Module Status")
async def get_accounting():
    """Module status endpoint for accounting."""
    return {"module": "accounting", "status": "active", "bridge": "document_to_draft"}


# ── Draft Lifecycle Endpoints ─────────────────────────────────────────────

@router.post(
    "/drafts/generate/{document_id}",
    response_model=APIResponse[DraftGenerateResponse],
    summary="Generate or update accounting draft from verified document",
)
def generate_draft_from_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate or update a reviewable accounting draft from a verified document.
    - Idempotent: Updates existing unposted draft in place.
    - Rejects if already posted to ledger.
    - Skips non-financial / informational documents safely.
    """
    result = AccountingDraftService.generate_or_update_draft(db, document_id)
    if result.status == "error":
        if result.validation and result.validation.status == "already_posted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=result.message,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    return APIResponse(
        success=True,
        message=result.message,
        data=result,
    )


@router.get(
    "/drafts",
    response_model=APIResponse[List[AccountingRecordResponse]],
    summary="List accounting records or drafts",
)
def list_drafts(
    client_id: Optional[uuid.UUID] = Query(None, description="Filter by client ID"),
    document_id: Optional[uuid.UUID] = Query(None, description="Filter by source document ID"),
    status: Optional[str] = Query("draft", description="Filter by status: 'draft' | 'posted' | null for all"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve reviewable accounting drafts or posted ledger entries."""
    records = AccountingDraftService.get_drafts(
        db,
        client_id=client_id,
        document_id=document_id,
        status=status,
    )
    return APIResponse(
        success=True,
        message=f"Found {len(records)} accounting record(s).",
        data=[AccountingRecordResponse.model_validate(r) for r in records],
    )


@router.get(
    "/drafts/{draft_id}",
    response_model=APIResponse[AccountingRecordResponse],
    summary="Get single draft or accounting record",
)
def get_draft_by_id(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a specific draft or posted record by its ID."""
    record = AccountingDraftService.get_draft_by_id(db, draft_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Accounting record {draft_id} not found.",
        )
    return APIResponse(
        success=True,
        message="Record retrieved successfully.",
        data=AccountingRecordResponse.model_validate(record),
    )


@router.post(
    "/drafts/{draft_id}/post",
    response_model=APIResponse[DraftPostResponse],
    summary="Explicitly post draft to accounting ledger",
)
def post_draft_to_ledger(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Explicitly commit an accounting draft into the permanent financial ledger.
    Changes status from 'draft' to 'posted' with timestamp audit note.
    """
    result = AccountingDraftService.post_draft_to_ledger(db, draft_id, user=current_user)
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )
    return APIResponse(
        success=True,
        message=result.message,
        data=result,
    )


@router.post(
    "/drafts/bulk-post",
    response_model=APIResponse[DraftBulkPostResponse],
    summary="Bulk post multiple drafts to ledger",
)
def bulk_post_drafts(
    payload: DraftBulkPostRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post multiple approved drafts to the financial ledger in one transaction."""
    result = AccountingDraftService.bulk_post_drafts(db, payload.draft_ids, user=current_user)
    return APIResponse(
        success=True,
        message=f"Bulk posting complete: {result.posted_count} posted, {result.failed_count} failed.",
        data=result,
    )


@router.get(
    "/drafts/{draft_id}/journal",
    response_model=APIResponse[Optional[JournalEntryDetailResponse]],
    summary="Get persistent journal entry linked to a draft or voucher",
)
def get_draft_journal_entry(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve detailed journal entry and lines linked to an accounting record."""
    record = AccountingDraftService.get_draft_by_id(db, draft_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    je = db.query(JournalEntry).filter(JournalEntry.accounting_record_id == draft_id).first()
    if not je:
        return APIResponse(
            success=True,
            message="No persistent journal entry found (legacy or unposted voucher).",
            data=None,
        )

    detail = JournalEntryService.get_journal_entry_by_id(db, je.id, current_user)
    lines_resp = [
        JournalEntryLineResponse(
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
        for line in detail.lines
    ]
    data = JournalEntryDetailResponse(
        id=detail.id,
        client_id=detail.client_id,
        accounting_record_id=detail.accounting_record_id,
        document_id=detail.document_id,
        entry_number=detail.entry_number,
        entry_date=detail.entry_date,
        entry_type=detail.entry_type,
        status=detail.status,
        narration=detail.narration,
        reference_number=detail.reference_number,
        total_debit=detail.total_debit,
        total_credit=detail.total_credit,
        is_balanced=detail.is_balanced,
        posted_at=detail.posted_at,
        posted_by_user_id=detail.posted_by_user_id,
        is_reversed=detail.is_reversed,
        reversal_entry_id=detail.reversal_entry_id,
        reversal_reason=detail.reversal_reason,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
        lines=lines_resp,
    )
    return APIResponse(
        success=True,
        message="Journal entry retrieved successfully.",
        data=data,
    )



@router.delete(
    "/drafts/{draft_id}",
    response_model=APIResponse[dict],
    summary="Delete an unposted draft",
)
def delete_draft(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an unposted draft. Refuses deletion if record has already been posted."""
    success, message = AccountingDraftService.delete_draft(db, draft_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )
    return APIResponse(
        success=True,
        message=message,
        data={"draft_id": str(draft_id), "deleted": True},
    )
