"""
Voucher Management API Router — Customer receipts, supplier payments, contra transfers,
and Accounts Receivable (AR) / Accounts Payable (AP) outstanding aging reports.
Mounted under /api/v1/accounting/vouchers.
"""

import uuid
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.voucher_service import VoucherService
from app.schemas.voucher_management import (
    CustomerReceiptCreate,
    SupplierPaymentCreate,
    ContraVoucherCreate,
    OutstandingReportResponse,
)
from app.schemas.journal_entry import JournalEntryDetailResponse, JournalEntryLineResponse
from app.schemas.common import APIResponse

router = APIRouter()


def _format_journal_detail(entry) -> JournalEntryDetailResponse:
    """Helper to convert JournalEntry model to JournalEntryDetailResponse."""
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
        for line in entry.lines
    ]
    return JournalEntryDetailResponse(
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


@router.post(
    "/receipt",
    response_model=APIResponse[JournalEntryDetailResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record Customer Receipt (Bank/Cash Dr, Debtor Cr)",
)
def record_customer_receipt(
    payload: CustomerReceiptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record money received from customer into liquid accounts with automatic double-entry journal."""
    je = VoucherService.record_customer_receipt(db, payload, current_user)
    return APIResponse(
        success=True,
        message=f"Receipt {je.entry_number} recorded successfully.",
        data=_format_journal_detail(je),
    )


@router.post(
    "/payment",
    response_model=APIResponse[JournalEntryDetailResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record Supplier Payment (Creditor Dr, Bank/Cash Cr)",
)
def record_supplier_payment(
    payload: SupplierPaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record money paid to vendor from liquid accounts with automatic double-entry journal."""
    je = VoucherService.record_supplier_payment(db, payload, current_user)
    return APIResponse(
        success=True,
        message=f"Payment {je.entry_number} recorded successfully.",
        data=_format_journal_detail(je),
    )


@router.post(
    "/contra",
    response_model=APIResponse[JournalEntryDetailResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record Contra Transfer (Cash/Bank Liquidity Move)",
)
def record_contra_voucher(
    payload: ContraVoucherCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record bank-to-cash, cash-to-bank, or inter-bank liquidity transfer."""
    je = VoucherService.record_contra_voucher(db, payload, current_user)
    return APIResponse(
        success=True,
        message=f"Contra voucher {je.entry_number} recorded successfully.",
        data=_format_journal_detail(je),
    )


@router.get(
    "/outstanding/receivables",
    response_model=APIResponse[OutstandingReportResponse],
    summary="Get Accounts Receivable (Customer Aging & Outstanding)",
)
def get_outstanding_receivables(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    as_of_date: Optional[date] = Query(None, description="As of date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve customer-wise unpaid sales invoices and aging analysis (0-30, 31-60, 61-90, 90+ days)."""
    report = VoucherService.get_outstanding_receivables(db, client_id, current_user, as_of_date)
    return APIResponse(
        success=True,
        message="Receivables aging report generated successfully.",
        data=report,
    )


@router.get(
    "/outstanding/payables",
    response_model=APIResponse[OutstandingReportResponse],
    summary="Get Accounts Payable (Supplier Aging & Outstanding)",
)
def get_outstanding_payables(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    as_of_date: Optional[date] = Query(None, description="As of date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve vendor-wise unpaid purchase bills and aging analysis (0-30, 31-60, 61-90, 90+ days)."""
    report = VoucherService.get_outstanding_payables(db, client_id, current_user, as_of_date)
    return APIResponse(
        success=True,
        message="Payables aging report generated successfully.",
        data=report,
    )
