"""
Voucher Service — Handles customer receipts, supplier payments, contra transfers,
and outstanding balance tracking (Accounts Receivable & Accounts Payable aging).
Maintains dual-layer synchronization across AccountingRecord and JournalEntry.
"""

import uuid
import logging
from typing import Optional, List, Dict, Tuple
from decimal import Decimal
from datetime import date, datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.client import Client
from app.models.user import User
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.accounting_record import AccountingRecord
from app.models.uploaded_document import UploadedDocument
from app.core.exceptions import NotFoundException, ForbiddenException, BadRequestException
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.journal_entry_service import JournalEntryService
from app.services.trial_balance_service import TrialBalanceService
from app.schemas.journal_entry import JournalEntryCreate, JournalEntryLineCreate
from app.schemas.voucher_management import (
    CustomerReceiptCreate,
    SupplierPaymentCreate,
    ContraVoucherCreate,
    OutstandingInvoiceDoc,
    OutstandingPartyItem,
    OutstandingReportResponse,
)

logger = logging.getLogger(__name__)


class VoucherService:

    @staticmethod
    def verify_client_access(db: Session, client_id: uuid.UUID, user: User) -> Client:
        """Verify client existence and user permissions."""
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise NotFoundException(detail=f"Client {client_id} not found")

        if user.role != "admin" and client.user_id is not None and client.user_id != user.id:
            raise ForbiddenException(detail="You do not have permission to access records for this client")

        return client

    @classmethod
    def _get_accounts_by_code(cls, db: Session, client_id: uuid.UUID, user: User) -> Dict[str, ChartOfAccounts]:
        """Fetch client Chart of Accounts mapped by account_code (auto-initializing if empty)."""
        accounts = db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id).all()
        if not accounts:
            ChartOfAccountsService.initialize_default_accounts(db, client_id, user)
            accounts = db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id).all()
        return {a.account_code: a for a in accounts}

    # ── 1. Customer Receipts (Dr Bank/Cash, Cr Debtors) ───────────────────────

    @classmethod
    def record_customer_receipt(
        cls,
        db: Session,
        payload: CustomerReceiptCreate,
        user: User,
    ) -> JournalEntry:
        """Record customer payment receipt against outstanding receivables."""
        cls.verify_client_access(db, payload.client_id, user)

        # Period lockout check
        is_closed, period_name = TrialBalanceService.is_period_closed_for_date(
            db, payload.client_id, payload.receipt_date
        )
        if is_closed:
            raise BadRequestException(
                detail=f"Accounting period '{period_name}' is closed. Receipts cannot be recorded for {payload.receipt_date}."
            )

        acc_map = cls._get_accounts_by_code(db, payload.client_id, user)

        bank_acc = acc_map.get(payload.bank_or_cash_account_code) or acc_map.get("1020") or acc_map.get("1010")
        debtor_acc = acc_map.get("1100") or acc_map.get("1010")

        if not bank_acc or not debtor_acc:
            raise BadRequestException(detail="Essential Bank or Debtors account not found in Chart of Accounts")

        amt = Decimal(str(payload.amount)).quantize(Decimal("0.01"))
        ref_no = payload.reference_number or f"REC-{date.today().strftime('%Y%m%d')}"
        narration = payload.narration or f"Customer Receipt from {payload.customer_name} (Ref: {ref_no})"

        # 1. Create AccountingRecord (flat layer)
        record = AccountingRecord(
            id=uuid.uuid4(),
            client_id=payload.client_id,
            document_id=payload.allocated_document_id,
            transaction_date=payload.receipt_date,
            voucher_type="receipt",
            category="customer_receipt",
            description=narration,
            debit=amt,
            credit=Decimal("0.00"),
            reference_number=ref_no,
            status="posted",
        )
        db.add(record)
        db.flush()

        # 2. Create Journal Entry (persistent double-entry layer)
        lines = [
            JournalEntryLineCreate(
                account_id=bank_acc.id,
                debit_amount=amt,
                credit_amount=Decimal("0.00"),
                description=f"Received into {bank_acc.account_name} from {payload.customer_name}",
                party_name=payload.customer_name,
                party_gstin=payload.customer_gstin,
            ),
            JournalEntryLineCreate(
                account_id=debtor_acc.id,
                debit_amount=Decimal("0.00"),
                credit_amount=amt,
                description=f"Receivable settlement by {payload.customer_name}",
                party_name=payload.customer_name,
                party_gstin=payload.customer_gstin,
            ),
        ]

        je_payload = JournalEntryCreate(
            client_id=payload.client_id,
            accounting_record_id=record.id,
            document_id=payload.allocated_document_id,
            entry_date=payload.receipt_date,
            entry_type="receipt",
            narration=narration,
            reference_number=ref_no,
            lines=lines,
        )

        je = JournalEntryService.create_journal_entry(
            db=db,
            client_id=payload.client_id,
            payload=je_payload,
            user=user,
            auto_commit=True,
        )

        logger.info("Recorded Customer Receipt %s (₹%s) from %s", je.entry_number, amt, payload.customer_name)
        return je

    # ── 2. Supplier Payments (Dr Creditors, Cr Bank/Cash) ─────────────────────

    @classmethod
    def record_supplier_payment(
        cls,
        db: Session,
        payload: SupplierPaymentCreate,
        user: User,
    ) -> JournalEntry:
        """Record payment disbursement to vendor against purchase payables."""
        cls.verify_client_access(db, payload.client_id, user)

        # Period lockout check
        is_closed, period_name = TrialBalanceService.is_period_closed_for_date(
            db, payload.client_id, payload.payment_date
        )
        if is_closed:
            raise BadRequestException(
                detail=f"Accounting period '{period_name}' is closed. Payments cannot be recorded for {payload.payment_date}."
            )

        acc_map = cls._get_accounts_by_code(db, payload.client_id, user)

        creditor_acc = acc_map.get("2010") or acc_map.get("1010")
        bank_acc = acc_map.get(payload.bank_or_cash_account_code) or acc_map.get("1020") or acc_map.get("1010")

        if not creditor_acc or not bank_acc:
            raise BadRequestException(detail="Essential Creditors or Bank account not found in Chart of Accounts")

        amt = Decimal(str(payload.amount)).quantize(Decimal("0.01"))
        ref_no = payload.reference_number or f"PAY-{date.today().strftime('%Y%m%d')}"
        narration = payload.narration or f"Supplier Payment to {payload.vendor_name} (Ref: {ref_no})"

        # 1. Create AccountingRecord (flat layer)
        record = AccountingRecord(
            id=uuid.uuid4(),
            client_id=payload.client_id,
            document_id=payload.allocated_document_id,
            transaction_date=payload.payment_date,
            voucher_type="payment",
            category="supplier_payment",
            description=narration,
            debit=Decimal("0.00"),
            credit=amt,
            reference_number=ref_no,
            status="posted",
        )
        db.add(record)
        db.flush()

        # 2. Create Journal Entry (persistent double-entry layer)
        lines = [
            JournalEntryLineCreate(
                account_id=creditor_acc.id,
                debit_amount=amt,
                credit_amount=Decimal("0.00"),
                description=f"Payable settlement to {payload.vendor_name}",
                party_name=payload.vendor_name,
                party_gstin=payload.vendor_gstin,
            ),
            JournalEntryLineCreate(
                account_id=bank_acc.id,
                debit_amount=Decimal("0.00"),
                credit_amount=amt,
                description=f"Disbursed from {bank_acc.account_name} to {payload.vendor_name}",
                party_name=payload.vendor_name,
                party_gstin=payload.vendor_gstin,
            ),
        ]

        je_payload = JournalEntryCreate(
            client_id=payload.client_id,
            accounting_record_id=record.id,
            document_id=payload.allocated_document_id,
            entry_date=payload.payment_date,
            entry_type="payment",
            narration=narration,
            reference_number=ref_no,
            lines=lines,
        )

        je = JournalEntryService.create_journal_entry(
            db=db,
            client_id=payload.client_id,
            payload=je_payload,
            user=user,
            auto_commit=True,
        )

        logger.info("Recorded Supplier Payment %s (₹%s) to %s", je.entry_number, amt, payload.vendor_name)
        return je

    # ── 3. Contra Vouchers (Bank to Cash / Cash to Bank / Inter-Bank) ──────────

    @classmethod
    def record_contra_voucher(
        cls,
        db: Session,
        payload: ContraVoucherCreate,
        user: User,
    ) -> JournalEntry:
        """Record contra cash/bank liquidity transfer."""
        cls.verify_client_access(db, payload.client_id, user)

        if payload.from_account_code == payload.to_account_code:
            raise BadRequestException(detail="Contra voucher source and destination accounts must be different")

        # Period lockout check
        is_closed, period_name = TrialBalanceService.is_period_closed_for_date(
            db, payload.client_id, payload.voucher_date
        )
        if is_closed:
            raise BadRequestException(
                detail=f"Accounting period '{period_name}' is closed. Contra vouchers cannot be posted for {payload.voucher_date}."
            )

        acc_map = cls._get_accounts_by_code(db, payload.client_id, user)
        from_acc = acc_map.get(payload.from_account_code)
        to_acc = acc_map.get(payload.to_account_code)

        if not from_acc or not to_acc:
            raise BadRequestException(detail="Source or destination account code not found in Chart of Accounts")

        amt = Decimal(str(payload.amount)).quantize(Decimal("0.01"))
        ref_no = payload.reference_number or f"CON-{date.today().strftime('%Y%m%d')}"
        narration = payload.narration or f"Contra transfer from {from_acc.account_name} to {to_acc.account_name}"

        # 1. Create AccountingRecord (flat layer)
        record = AccountingRecord(
            id=uuid.uuid4(),
            client_id=payload.client_id,
            transaction_date=payload.voucher_date,
            voucher_type="contra",
            category="bank_transfer",
            description=narration,
            debit=amt,
            credit=amt,
            reference_number=ref_no,
            status="posted",
        )
        db.add(record)
        db.flush()

        # 2. Create Journal Entry (persistent double-entry layer)
        lines = [
            JournalEntryLineCreate(
                account_id=to_acc.id,
                debit_amount=amt,
                credit_amount=Decimal("0.00"),
                description=f"Received into {to_acc.account_name}",
            ),
            JournalEntryLineCreate(
                account_id=from_acc.id,
                debit_amount=Decimal("0.00"),
                credit_amount=amt,
                description=f"Transferred out from {from_acc.account_name}",
            ),
        ]

        je_payload = JournalEntryCreate(
            client_id=payload.client_id,
            accounting_record_id=record.id,
            entry_date=payload.voucher_date,
            entry_type="contra",
            narration=narration,
            reference_number=ref_no,
            lines=lines,
        )

        je = JournalEntryService.create_journal_entry(
            db=db,
            client_id=payload.client_id,
            payload=je_payload,
            user=user,
            auto_commit=True,
        )

        logger.info("Recorded Contra Voucher %s (₹%s) from %s to %s", je.entry_number, amt, from_acc.account_code, to_acc.account_code)
        return je

    # ── 4. Outstanding Balances & Aging (AR / AP) ─────────────────────────────

    @classmethod
    def get_outstanding_receivables(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        as_of_date: Optional[date] = None,
    ) -> OutstandingReportResponse:
        """
        Calculate customer-wise accounts receivable outstanding balances and aging buckets.
        Aging buckets: 0–30 days, 31–60 days, 61–90 days, 90+ days.
        """
        cls.verify_client_access(db, client_id, user)
        effective_date = as_of_date or date.today()

        acc_map = cls._get_accounts_by_code(db, client_id, user)
        debtor_acc = acc_map.get("1100")

        parties_data: Dict[str, Dict] = {}

        if debtor_acc:
            # 1. Fetch debtor ledger lines (Debits = Invoiced, Credits = Receipts)
            lines = (
                db.query(JournalEntryLine, JournalEntry)
                .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
                .filter(
                    JournalEntry.client_id == client_id,
                    JournalEntry.status == "posted",
                    JournalEntryLine.account_id == debtor_acc.id,
                    JournalEntry.entry_date <= effective_date,
                )
                .all()
            )

            for line, entry in lines:
                party = line.party_name or "Commercial Customer"
                if party not in parties_data:
                    parties_data[party] = {
                        "party_name": party,
                        "party_gstin": line.party_gstin,
                        "total_invoiced": Decimal("0.00"),
                        "total_settled": Decimal("0.00"),
                        "invoices": [],
                    }

                dr = line.debit_amount or Decimal("0.00")
                cr = line.credit_amount or Decimal("0.00")

                if dr > Decimal("0.00"):
                    # Sales invoice leg
                    parties_data[party]["total_invoiced"] += dr
                    days = (effective_date - entry.entry_date).days
                    parties_data[party]["invoices"].append({
                        "document_id": entry.document_id,
                        "voucher_id": entry.accounting_record_id,
                        "invoice_number": entry.reference_number or entry.entry_number,
                        "invoice_date": entry.entry_date,
                        "gross_amount": dr,
                        "days_overdue": max(0, days),
                    })
                elif cr > Decimal("0.00"):
                    # Receipt / credit leg
                    parties_data[party]["total_settled"] += cr

        # Assemble party items with FIFO settlement against invoices
        party_items: List[OutstandingPartyItem] = []
        tot_inv = Decimal("0.00")
        tot_set = Decimal("0.00")
        tot_out = Decimal("0.00")
        tot_0_30 = Decimal("0.00")
        tot_31_60 = Decimal("0.00")
        tot_61_90 = Decimal("0.00")
        tot_90_plus = Decimal("0.00")

        for party, pdata in sorted(parties_data.items()):
            inv_sum = pdata["total_invoiced"]
            set_sum = pdata["total_settled"]
            net_out = max(Decimal("0.00"), inv_sum - set_sum)

            tot_inv += inv_sum
            tot_set += set_sum
            tot_out += net_out

            # Distribute remaining outstanding across invoices starting from oldest or newest
            rem_credit = set_sum
            p_invoices: List[OutstandingInvoiceDoc] = []
            a_0_30 = Decimal("0.00")
            a_31_60 = Decimal("0.00")
            a_61_90 = Decimal("0.00")
            a_90_plus = Decimal("0.00")

            # Sort invoices by date asc for FIFO allocation
            sorted_invs = sorted(pdata["invoices"], key=lambda x: x["invoice_date"])
            for inv_info in sorted_invs:
                gross = inv_info["gross_amount"]
                alloc = min(rem_credit, gross)
                rem_credit -= alloc
                unpaid = gross - alloc

                if unpaid > Decimal("0.00"):
                    days = inv_info["days_overdue"]
                    if days <= 30:
                        a_0_30 += unpaid
                    elif days <= 60:
                        a_31_60 += unpaid
                    elif days <= 90:
                        a_61_90 += unpaid
                    else:
                        a_90_plus += unpaid

                p_invoices.append(
                    OutstandingInvoiceDoc(
                        document_id=inv_info["document_id"],
                        voucher_id=inv_info["voucher_id"],
                        invoice_number=inv_info["invoice_number"],
                        invoice_date=inv_info["invoice_date"],
                        gross_amount=gross,
                        settled_amount=alloc,
                        outstanding_amount=unpaid,
                        days_overdue=inv_info["days_overdue"],
                    )
                )

            tot_0_30 += a_0_30
            tot_31_60 += a_31_60
            tot_61_90 += a_61_90
            tot_90_plus += a_90_plus

            party_items.append(
                OutstandingPartyItem(
                    party_name=party,
                    party_gstin=pdata["party_gstin"],
                    total_invoiced=inv_sum,
                    total_settled=set_sum,
                    net_outstanding=net_out,
                    aging_0_30=a_0_30,
                    aging_31_60=a_31_60,
                    aging_61_90=a_61_90,
                    aging_90_plus=a_90_plus,
                    invoices=p_invoices,
                )
            )

        return OutstandingReportResponse(
            client_id=client_id,
            as_of_date=effective_date,
            report_type="receivables",
            total_invoiced=tot_inv,
            total_settled=tot_set,
            total_outstanding=tot_out,
            aging_0_30_total=tot_0_30,
            aging_31_60_total=tot_31_60,
            aging_61_90_total=tot_61_90,
            aging_90_plus_total=tot_90_plus,
            parties=party_items,
        )

    @classmethod
    def get_outstanding_payables(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        as_of_date: Optional[date] = None,
    ) -> OutstandingReportResponse:
        """
        Calculate vendor-wise accounts payable outstanding balances and aging buckets.
        Aging buckets: 0–30 days, 31–60 days, 61–90 days, 90+ days.
        """
        cls.verify_client_access(db, client_id, user)
        effective_date = as_of_date or date.today()

        acc_map = cls._get_accounts_by_code(db, client_id, user)
        creditor_acc = acc_map.get("2010")

        parties_data: Dict[str, Dict] = {}

        if creditor_acc:
            # Creditor lines: Credits = Billed, Debits = Payments
            lines = (
                db.query(JournalEntryLine, JournalEntry)
                .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
                .filter(
                    JournalEntry.client_id == client_id,
                    JournalEntry.status == "posted",
                    JournalEntryLine.account_id == creditor_acc.id,
                    JournalEntry.entry_date <= effective_date,
                )
                .all()
            )

            for line, entry in lines:
                party = line.party_name or "Commercial Vendor"
                if party not in parties_data:
                    parties_data[party] = {
                        "party_name": party,
                        "party_gstin": line.party_gstin,
                        "total_invoiced": Decimal("0.00"),
                        "total_settled": Decimal("0.00"),
                        "invoices": [],
                    }

                cr = line.credit_amount or Decimal("0.00")
                dr = line.debit_amount or Decimal("0.00")

                if cr > Decimal("0.00"):
                    # Purchase bill leg
                    parties_data[party]["total_invoiced"] += cr
                    days = (effective_date - entry.entry_date).days
                    parties_data[party]["invoices"].append({
                        "document_id": entry.document_id,
                        "voucher_id": entry.accounting_record_id,
                        "invoice_number": entry.reference_number or entry.entry_number,
                        "invoice_date": entry.entry_date,
                        "gross_amount": cr,
                        "days_overdue": max(0, days),
                    })
                elif dr > Decimal("0.00"):
                    # Payment leg
                    parties_data[party]["total_settled"] += dr

        # Assemble party items
        party_items: List[OutstandingPartyItem] = []
        tot_inv = Decimal("0.00")
        tot_set = Decimal("0.00")
        tot_out = Decimal("0.00")
        tot_0_30 = Decimal("0.00")
        tot_31_60 = Decimal("0.00")
        tot_61_90 = Decimal("0.00")
        tot_90_plus = Decimal("0.00")

        for party, pdata in sorted(parties_data.items()):
            inv_sum = pdata["total_invoiced"]
            set_sum = pdata["total_settled"]
            net_out = max(Decimal("0.00"), inv_sum - set_sum)

            tot_inv += inv_sum
            tot_set += set_sum
            tot_out += net_out

            rem_debit = set_sum
            p_bills: List[OutstandingInvoiceDoc] = []
            a_0_30 = Decimal("0.00")
            a_31_60 = Decimal("0.00")
            a_61_90 = Decimal("0.00")
            a_90_plus = Decimal("0.00")

            sorted_bills = sorted(pdata["invoices"], key=lambda x: x["invoice_date"])
            for b_info in sorted_bills:
                gross = b_info["gross_amount"]
                alloc = min(rem_debit, gross)
                rem_debit -= alloc
                unpaid = gross - alloc

                if unpaid > Decimal("0.00"):
                    days = b_info["days_overdue"]
                    if days <= 30:
                        a_0_30 += unpaid
                    elif days <= 60:
                        a_31_60 += unpaid
                    elif days <= 90:
                        a_61_90 += unpaid
                    else:
                        a_90_plus += unpaid

                p_bills.append(
                    OutstandingInvoiceDoc(
                        document_id=b_info["document_id"],
                        voucher_id=b_info["voucher_id"],
                        invoice_number=b_info["invoice_number"],
                        invoice_date=b_info["invoice_date"],
                        gross_amount=gross,
                        settled_amount=alloc,
                        outstanding_amount=unpaid,
                        days_overdue=b_info["days_overdue"],
                    )
                )

            tot_0_30 += a_0_30
            tot_31_60 += a_31_60
            tot_61_90 += a_61_90
            tot_90_plus += a_90_plus

            party_items.append(
                OutstandingPartyItem(
                    party_name=party,
                    party_gstin=pdata["party_gstin"],
                    total_invoiced=inv_sum,
                    total_settled=set_sum,
                    net_outstanding=net_out,
                    aging_0_30=a_0_30,
                    aging_31_60=a_31_60,
                    aging_61_90=a_61_90,
                    aging_90_plus=a_90_plus,
                    invoices=p_bills,
                )
            )

        return OutstandingReportResponse(
            client_id=client_id,
            as_of_date=effective_date,
            report_type="payables",
            total_invoiced=tot_inv,
            total_settled=tot_set,
            total_outstanding=tot_out,
            aging_0_30_total=tot_0_30,
            aging_31_60_total=tot_31_60,
            aging_61_90_total=tot_61_90,
            aging_90_plus_total=tot_90_plus,
            parties=party_items,
        )
