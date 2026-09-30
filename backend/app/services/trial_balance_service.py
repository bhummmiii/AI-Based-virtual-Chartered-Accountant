"""
Trial Balance & Period Control Service — Generates balanced Trial Balance reports,
audits double-entry equality, performs health checks (unbalanced entries, duplicate references,
unposted drafts), and enforces accounting period closures.
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
from app.models.accounting_period import AccountingPeriod
from app.core.exceptions import NotFoundException, ForbiddenException, BadRequestException
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.schemas.trial_balance import (
    TrialBalanceAccountRow,
    TrialBalanceGroup,
    TrialBalanceHealthCheck,
    TrialBalanceResponse,
    AccountingPeriodCreate,
    AccountingPeriodResponse,
)

logger = logging.getLogger(__name__)


class TrialBalanceService:

    @staticmethod
    def verify_client_access(db: Session, client_id: uuid.UUID, user: User) -> Client:
        """Verify client existence and CA tenant permission."""
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise NotFoundException(detail=f"Client {client_id} not found")

        if user.role != "admin" and client.user_id is not None and client.user_id != user.id:
            raise ForbiddenException(detail="You do not have permission to access records for this client")

        return client

    # ── 1. Trial Balance Generation & Integrity Engine ───────────────────────

    @classmethod
    def generate_trial_balance(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        as_of_date: Optional[date] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> TrialBalanceResponse:
        """
        Generate strict, double-entry Trial Balance for a client.
        Extracts posted debits and credits, nets each account to its prevailing Dr or Cr balance,
        groups by accounting classification, and runs comprehensive audit health checks.
        """
        cls.verify_client_access(db, client_id, user)
        effective_as_of = to_date or as_of_date or date.today()

        # 1. Ensure Chart of Accounts is initialized
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

        # 2. Query posted transactions
        line_query = (
            db.query(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit_amount), Decimal("0.00")),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), Decimal("0.00")),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .filter(
                JournalEntry.client_id == client_id,
                JournalEntry.status == "posted",
            )
        )

        if from_date and to_date:
            line_query = line_query.filter(
                JournalEntry.entry_date >= from_date,
                JournalEntry.entry_date <= to_date,
            )
        else:
            line_query = line_query.filter(JournalEntry.entry_date <= effective_as_of)

        turnover_rows = line_query.group_by(JournalEntryLine.account_id).all()
        turnover_map: Dict[uuid.UUID, Tuple[Decimal, Decimal]] = {
            acc_id: (dr or Decimal("0.00"), cr or Decimal("0.00"))
            for acc_id, dr, cr in turnover_rows
        }

        # 3. Categorize into Groups (Assets, Liabilities, Equity, Revenue, Expenses)
        group_order = ["asset", "liability", "equity", "revenue", "expense"]
        group_display = {
            "asset": "Assets",
            "liability": "Liabilities",
            "equity": "Equity & Capital",
            "revenue": "Revenue & Income",
            "expense": "Expenses & Outflows",
        }
        groups_dict: Dict[str, List[TrialBalanceAccountRow]] = {g: [] for g in group_order}

        total_tb_debit = Decimal("0.00")
        total_tb_credit = Decimal("0.00")

        for acc in accounts:
            dr_sum, cr_sum = turnover_map.get(acc.id, (Decimal("0.00"), Decimal("0.00")))
            net = dr_sum - cr_sum

            if net > Decimal("0.00"):
                dr_bal = net
                cr_bal = Decimal("0.00")
            elif net < Decimal("0.00"):
                dr_bal = Decimal("0.00")
                cr_bal = abs(net)
            else:
                dr_bal = Decimal("0.00")
                cr_bal = Decimal("0.00")

            total_tb_debit += dr_bal
            total_tb_credit += cr_bal

            row = TrialBalanceAccountRow(
                account_id=acc.id,
                account_code=acc.account_code,
                account_name=acc.account_name,
                account_type=acc.account_type,
                account_subgroup=acc.account_subgroup,
                debit_balance=dr_bal,
                credit_balance=cr_bal,
            )

            acc_type_key = acc.account_type.lower()
            if acc_type_key in groups_dict:
                groups_dict[acc_type_key].append(row)
            else:
                groups_dict.setdefault("asset", []).append(row)

        groups: List[TrialBalanceGroup] = []
        for g_key in group_order:
            row_list = groups_dict.get(g_key, [])
            g_dr = sum((r.debit_balance for r in row_list), Decimal("0.00"))
            g_cr = sum((r.credit_balance for r in row_list), Decimal("0.00"))
            groups.append(
                TrialBalanceGroup(
                    account_type=group_display.get(g_key, g_key.capitalize()),
                    total_debit=g_dr,
                    total_credit=g_cr,
                    net_balance=abs(g_dr - g_cr),
                    accounts=row_list,
                )
            )

        # 4. Audit Health Checks
        tb_difference = total_tb_debit - total_tb_credit
        is_tb_balanced = abs(tb_difference) < Decimal("0.01")

        health_check = cls.run_health_checks(db, client_id, total_tb_debit, total_tb_credit)

        return TrialBalanceResponse(
            client_id=client_id,
            as_of_date=effective_as_of,
            from_date=from_date,
            to_date=to_date,
            total_debit=total_tb_debit,
            total_credit=total_tb_credit,
            is_balanced=is_tb_balanced,
            groups=groups,
            health_check=health_check,
        )

    @classmethod
    def run_health_checks(
        cls,
        db: Session,
        client_id: uuid.UUID,
        total_debit: Decimal,
        total_credit: Decimal,
    ) -> TrialBalanceHealthCheck:
        """Run statutory sanity and financial control checks."""
        diff = total_debit - total_credit
        is_balanced = abs(diff) < Decimal("0.01")

        # 1. Check for unbalanced journal entries
        unbalanced_count = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.client_id == client_id,
                JournalEntry.total_debit != JournalEntry.total_credit,
            )
            .count()
        )

        # 2. Check for duplicate references
        dup_refs_query = (
            db.query(JournalEntry.reference_number, func.count(JournalEntry.id))
            .filter(
                JournalEntry.client_id == client_id,
                JournalEntry.reference_number.isnot(None),
                JournalEntry.reference_number != "",
            )
            .group_by(JournalEntry.reference_number)
            .having(func.count(JournalEntry.id) > 1)
            .all()
        )
        duplicate_references = [f"{ref} ({cnt} occurrences)" for ref, cnt in dup_refs_query]

        # 3. Check for unposted drafts awaiting review
        unposted_count = (
            db.query(AccountingRecord)
            .filter(
                AccountingRecord.client_id == client_id,
                AccountingRecord.status == "draft",
            )
            .count()
        )

        # 4. Closed period warnings
        closed_warnings: List[str] = []
        closed_periods = (
            db.query(AccountingPeriod)
            .filter(
                AccountingPeriod.client_id == client_id,
                AccountingPeriod.is_closed.is_(True),
            )
            .all()
        )
        for cp in closed_periods:
            closed_warnings.append(
                f"Period '{cp.period_name}' ({cp.start_date} to {cp.end_date}) is closed."
            )

        # Overall Status determination
        if not is_balanced or unbalanced_count > 0:
            status = "FAIL"
        elif duplicate_references or unposted_count > 0:
            status = "WARNING"
        else:
            status = "PASS"

        return TrialBalanceHealthCheck(
            is_balanced=is_balanced,
            total_debit=total_debit,
            total_credit=total_credit,
            difference=diff,
            unbalanced_entries_count=unbalanced_count,
            duplicate_references=duplicate_references,
            unposted_drafts_count=unposted_count,
            closed_period_warnings=closed_warnings,
            status=status,
        )

    # ── 2. Period Controls & Fiscal Lockout ───────────────────────────────────

    @classmethod
    def is_period_closed_for_date(
        cls,
        db: Session,
        client_id: uuid.UUID,
        tx_date: date,
    ) -> Tuple[bool, Optional[str]]:
        """Check if a date falls within any closed accounting period for a client."""
        try:
            closed_period = (
                db.query(AccountingPeriod)
                .filter(
                    AccountingPeriod.client_id == client_id,
                    AccountingPeriod.is_closed.is_(True),
                    AccountingPeriod.start_date <= tx_date,
                    AccountingPeriod.end_date >= tx_date,
                )
                .first()
            )
            if closed_period and isinstance(closed_period, AccountingPeriod) and closed_period.is_closed:
                return True, getattr(closed_period, "period_name", "Closed Period")
            return False, None
        except Exception:
            return False, None

    @classmethod
    def list_periods(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
    ) -> List[AccountingPeriod]:
        """List all defined accounting periods for a client."""
        cls.verify_client_access(db, client_id, user)
        return (
            db.query(AccountingPeriod)
            .filter(AccountingPeriod.client_id == client_id)
            .order_by(AccountingPeriod.start_date.desc())
            .all()
        )

    @classmethod
    def create_period(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        payload: AccountingPeriodCreate,
    ) -> AccountingPeriod:
        """Create a new accounting period."""
        cls.verify_client_access(db, client_id, user)

        if payload.start_date > payload.end_date:
            raise BadRequestException(detail="Period start date cannot be after end date")

        # Check name uniqueness
        existing = (
            db.query(AccountingPeriod)
            .filter(
                AccountingPeriod.client_id == client_id,
                AccountingPeriod.period_name == payload.period_name,
            )
            .first()
        )
        if existing:
            raise BadRequestException(detail=f"Period '{payload.period_name}' already exists for this client")

        period = AccountingPeriod(
            client_id=client_id,
            period_name=payload.period_name,
            start_date=payload.start_date,
            end_date=payload.end_date,
            status="open",
            is_closed=False,
            closing_notes=payload.closing_notes,
        )
        db.add(period)
        db.commit()
        db.refresh(period)
        return period

    @classmethod
    def close_period(
        cls,
        db: Session,
        client_id: uuid.UUID,
        period_id: uuid.UUID,
        user: User,
        notes: Optional[str] = None,
    ) -> AccountingPeriod:
        """Lock and close an accounting period to prevent retroactive tampering."""
        cls.verify_client_access(db, client_id, user)

        period = (
            db.query(AccountingPeriod)
            .filter(AccountingPeriod.id == period_id, AccountingPeriod.client_id == client_id)
            .first()
        )
        if not period:
            raise NotFoundException(detail=f"Accounting period {period_id} not found")

        period.is_closed = True
        period.status = "closed"
        period.closed_at = datetime.now(timezone.utc)
        period.closed_by_user_id = user.id
        if notes:
            period.closing_notes = notes

        db.commit()
        db.refresh(period)
        logger.info("Closed accounting period %s for client %s by user %s", period.period_name, client_id, user.id)
        return period

    @classmethod
    def reopen_period(
        cls,
        db: Session,
        client_id: uuid.UUID,
        period_id: uuid.UUID,
        user: User,
    ) -> AccountingPeriod:
        """Reopen a closed accounting period (admin or authorized CA only)."""
        cls.verify_client_access(db, client_id, user)

        period = (
            db.query(AccountingPeriod)
            .filter(AccountingPeriod.id == period_id, AccountingPeriod.client_id == client_id)
            .first()
        )
        if not period:
            raise NotFoundException(detail=f"Accounting period {period_id} not found")

        period.is_closed = False
        period.status = "open"
        period.closed_at = None
        period.closed_by_user_id = None

        db.commit()
        db.refresh(period)
        logger.info("Reopened accounting period %s for client %s", period.period_name, client_id)
        return period
