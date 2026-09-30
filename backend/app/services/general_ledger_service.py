"""
General Ledger Service — Core calculation engine for account ledgers, running balances, and GL summaries.
Computes balances exclusively from persisted, posted journal entries.
"""

import uuid
import logging
from typing import Optional, List, Dict, Tuple
from decimal import Decimal
from datetime import date
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.models.chart_of_accounts import ChartOfAccounts
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.client import Client
from app.models.user import User
from app.core.exceptions import NotFoundException, ForbiddenException
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.schemas.general_ledger import (
    LedgerTransactionItem,
    AccountLedgerResponse,
    GeneralLedgerAccountSummary,
    GeneralLedgerSummaryResponse,
)

logger = logging.getLogger(__name__)


class GeneralLedgerService:

    @staticmethod
    def verify_client_access(db: Session, client_id: uuid.UUID, user: User) -> Client:
        """Verify client existence and tenant authorization."""
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise NotFoundException(detail=f"Client {client_id} not found")

        if user.role != "admin" and client.user_id is not None and client.user_id != user.id:
            raise ForbiddenException(detail="You do not have permission to access accounting records for this client")

        return client

    @classmethod
    def _is_debit_normal(cls, account_type: str) -> bool:
        """Assets and Expenses normally hold Debit balances."""
        return account_type.lower() in {"asset", "expense"}

    @classmethod
    def _compute_balance_and_side(
        cls,
        account_type: str,
        total_dr: Decimal,
        total_cr: Decimal,
    ) -> Tuple[Decimal, str]:
        """Compute balance magnitude and side (Dr/Cr) based on account normal orientation."""
        if cls._is_debit_normal(account_type):
            net = total_dr - total_cr
            if net >= Decimal("0.00"):
                return net, "Dr"
            else:
                return abs(net), "Cr"
        else:
            net = total_cr - total_dr
            if net >= Decimal("0.00"):
                return net, "Cr"
            else:
                return abs(net), "Dr"

    @classmethod
    def get_account_ledger(
        cls,
        db: Session,
        client_id: uuid.UUID,
        account_id: uuid.UUID,
        user: User,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> AccountLedgerResponse:
        """
        Generate detailed, chronological ledger for a specific account.
        Includes opening balance, running balances after every line item, and closing balance.
        """
        cls.verify_client_access(db, client_id, user)

        account = (
            db.query(ChartOfAccounts)
            .filter(ChartOfAccounts.id == account_id, ChartOfAccounts.client_id == client_id)
            .first()
        )
        if not account:
            raise NotFoundException(detail=f"Account {account_id} not found for this client")

        is_debit_normal = cls._is_debit_normal(account.account_type)

        # 1. Compute Opening Balance (transactions strictly before from_date)
        opening_dr = Decimal("0.00")
        opening_cr = Decimal("0.00")
        if from_date:
            opening_query = (
                db.query(
                    func.coalesce(func.sum(JournalEntryLine.debit_amount), Decimal("0.00")),
                    func.coalesce(func.sum(JournalEntryLine.credit_amount), Decimal("0.00")),
                )
                .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
                .filter(
                    JournalEntry.client_id == client_id,
                    JournalEntry.status == "posted",
                    JournalEntryLine.account_id == account_id,
                    JournalEntry.entry_date < from_date,
                )
                .first()
            )
            if opening_query:
                opening_dr = opening_query[0] or Decimal("0.00")
                opening_cr = opening_query[1] or Decimal("0.00")

        opening_balance, opening_side = cls._compute_balance_and_side(account.account_type, opening_dr, opening_cr)

        # 2. Fetch Period Transactions
        tx_query = (
            db.query(JournalEntryLine, JournalEntry)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .filter(
                JournalEntry.client_id == client_id,
                JournalEntry.status == "posted",
                JournalEntryLine.account_id == account_id,
            )
            .options(
                joinedload(JournalEntryLine.journal_entry),
                joinedload(JournalEntryLine.account),
            )
        )

        if from_date:
            tx_query = tx_query.filter(JournalEntry.entry_date >= from_date)
        if to_date:
            tx_query = tx_query.filter(JournalEntry.entry_date <= to_date)

        results = tx_query.order_by(
            JournalEntry.entry_date.asc(),
            JournalEntry.created_at.asc(),
            JournalEntryLine.line_number.asc(),
        ).all()

        # 3. Calculate Running Balances
        period_dr = Decimal("0.00")
        period_cr = Decimal("0.00")

        # Initialize cumulative signed balance: positive = normal side, negative = opposite side
        if is_debit_normal:
            cum_signed = opening_dr - opening_cr
        else:
            cum_signed = opening_cr - opening_dr

        transactions: List[LedgerTransactionItem] = []
        for line, entry in results:
            dr = line.debit_amount or Decimal("0.00")
            cr = line.credit_amount or Decimal("0.00")
            period_dr += dr
            period_cr += cr

            if is_debit_normal:
                cum_signed += (dr - cr)
                if cum_signed >= Decimal("0.00"):
                    running_bal = cum_signed
                    side = "Dr"
                else:
                    running_bal = abs(cum_signed)
                    side = "Cr"
            else:
                cum_signed += (cr - dr)
                if cum_signed >= Decimal("0.00"):
                    running_bal = cum_signed
                    side = "Cr"
                else:
                    running_bal = abs(cum_signed)
                    side = "Dr"

            transactions.append(
                LedgerTransactionItem(
                    journal_entry_id=entry.id,
                    line_id=line.id,
                    entry_number=entry.entry_number,
                    entry_date=entry.entry_date,
                    entry_type=entry.entry_type,
                    accounting_record_id=entry.accounting_record_id,
                    document_id=entry.document_id,
                    reference_number=entry.reference_number,
                    narration=entry.narration,
                    line_description=line.description,
                    party_name=line.party_name,
                    party_gstin=line.party_gstin,
                    tax_head=line.tax_head,
                    tax_rate=line.tax_rate,
                    debit=dr,
                    credit=cr,
                    running_balance=running_bal,
                    balance_side=side,
                )
            )

        # 4. Closing Balance
        total_dr_cumulative = opening_dr + period_dr
        total_cr_cumulative = opening_cr + period_cr
        closing_balance, closing_side = cls._compute_balance_and_side(
            account.account_type, total_dr_cumulative, total_cr_cumulative
        )

        return AccountLedgerResponse(
            account_id=account.id,
            account_code=account.account_code,
            account_name=account.account_name,
            account_type=account.account_type,
            client_id=client_id,
            from_date=from_date,
            to_date=to_date,
            opening_balance=opening_balance,
            opening_balance_side=opening_side,
            total_debit=period_dr,
            total_credit=period_cr,
            closing_balance=closing_balance,
            closing_balance_side=closing_side,
            transaction_count=len(transactions),
            transactions=transactions,
        )

    @classmethod
    def get_general_ledger_summary(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> GeneralLedgerSummaryResponse:
        """
        Generate comprehensive summary across all Chart of Accounts accounts for a client.
        Provides opening balances, period turnover (Dr/Cr), and closing balances.
        """
        cls.verify_client_access(db, client_id, user)

        # Ensure accounts are initialized
        accounts = (
            db.query(ChartOfAccounts)
            .filter(ChartOfAccounts.client_id == client_id)
            .order_by(ChartOfAccounts.account_code.asc())
            .all()
        )
        if not accounts:
            ChartOfAccountsService.initialize_default_accounts(db, client_id, user)
            accounts = (
                db.query(ChartOfAccounts)
                .filter(ChartOfAccounts.client_id == client_id)
                .order_by(ChartOfAccounts.account_code.asc())
                .all()
            )

        # Opening balances map: account_id -> (opening_dr, opening_cr)
        opening_map: Dict[uuid.UUID, Tuple[Decimal, Decimal]] = {}
        if from_date:
            opening_rows = (
                db.query(
                    JournalEntryLine.account_id,
                    func.coalesce(func.sum(JournalEntryLine.debit_amount), Decimal("0.00")),
                    func.coalesce(func.sum(JournalEntryLine.credit_amount), Decimal("0.00")),
                )
                .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
                .filter(
                    JournalEntry.client_id == client_id,
                    JournalEntry.status == "posted",
                    JournalEntry.entry_date < from_date,
                )
                .group_by(JournalEntryLine.account_id)
                .all()
            )
            for acc_id, dr, cr in opening_rows:
                opening_map[acc_id] = (dr or Decimal("0.00"), cr or Decimal("0.00"))

        # Period turnover map: account_id -> (period_dr, period_cr, count)
        period_query = (
            db.query(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit_amount), Decimal("0.00")),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), Decimal("0.00")),
                func.count(JournalEntryLine.id),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .filter(
                JournalEntry.client_id == client_id,
                JournalEntry.status == "posted",
            )
        )
        if from_date:
            period_query = period_query.filter(JournalEntry.entry_date >= from_date)
        if to_date:
            period_query = period_query.filter(JournalEntry.entry_date <= to_date)

        period_rows = period_query.group_by(JournalEntryLine.account_id).all()
        period_map: Dict[uuid.UUID, Tuple[Decimal, Decimal, int]] = {}
        for acc_id, dr, cr, cnt in period_rows:
            period_map[acc_id] = (dr or Decimal("0.00"), cr or Decimal("0.00"), cnt or 0)

        # Assemble summary items
        summary_accounts: List[GeneralLedgerAccountSummary] = []
        overall_period_dr = Decimal("0.00")
        overall_period_cr = Decimal("0.00")

        for acc in accounts:
            open_dr, open_cr = opening_map.get(acc.id, (Decimal("0.00"), Decimal("0.00")))
            open_bal, open_side = cls._compute_balance_and_side(acc.account_type, open_dr, open_cr)

            p_dr, p_cr, count = period_map.get(acc.id, (Decimal("0.00"), Decimal("0.00"), 0))
            overall_period_dr += p_dr
            overall_period_cr += p_cr

            cum_dr = open_dr + p_dr
            cum_cr = open_cr + p_cr
            close_bal, close_side = cls._compute_balance_and_side(acc.account_type, cum_dr, cum_cr)

            summary_accounts.append(
                GeneralLedgerAccountSummary(
                    account_id=acc.id,
                    account_code=acc.account_code,
                    account_name=acc.account_name,
                    account_type=acc.account_type,
                    account_subgroup=acc.account_subgroup,
                    is_active=acc.is_active,
                    opening_balance=open_bal,
                    opening_balance_side=open_side,
                    total_debit=p_dr,
                    total_credit=p_cr,
                    closing_balance=close_bal,
                    closing_balance_side=close_side,
                    transaction_count=count,
                )
            )

        net_diff = overall_period_dr - overall_period_cr

        return GeneralLedgerSummaryResponse(
            client_id=client_id,
            from_date=from_date,
            to_date=to_date,
            total_debit=overall_period_dr,
            total_credit=overall_period_cr,
            net_difference=net_diff,
            accounts=summary_accounts,
        )
