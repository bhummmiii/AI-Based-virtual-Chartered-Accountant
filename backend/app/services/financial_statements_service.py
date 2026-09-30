"""
Financial Statements Service — Generates Profit & Loss Statements (Income Statement),
Balance Sheets (Statement of Financial Position), and drill-down audit details.
Strictly derives figures from posted journal entries with mathematical double-entry balance.
"""

import uuid
import logging
from typing import Optional, List, Dict, Tuple
from decimal import Decimal
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.client import Client
from app.models.user import User
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.core.exceptions import NotFoundException, ForbiddenException, BadRequestException
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.schemas.financial_reports import (
    ReportLineItem,
    ReportSection,
    ProfitAndLossResponse,
    BalanceSheetResponse,
    DrillDownTransactionItem,
    DrillDownResponse,
)

logger = logging.getLogger(__name__)


class FinancialStatementsService:

    @staticmethod
    def verify_client_access(db: Session, client_id: uuid.UUID, user: User) -> Client:
        """Verify client existence and user permissions."""
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise NotFoundException(detail=f"Client {client_id} not found")

        if user.role != "admin" and client.user_id is not None and client.user_id != user.id:
            raise ForbiddenException(detail="You do not have permission to access financial reports for this client")

        return client

    # ── 1. Profit & Loss Statement (Income Statement) ─────────────────────────

    @classmethod
    def generate_profit_and_loss(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        from_date: date,
        to_date: date,
    ) -> ProfitAndLossResponse:
        """
        Generate Profit & Loss Statement for a specific period.
        Schedule III structure:
        - Revenue from Operations
        - Less: Cost of Goods Sold / Direct Expenses -> Gross Profit
        - Less: Operating / Administrative Expenses -> Net Profit Before Tax
        """
        cls.verify_client_access(db, client_id, user)

        if from_date > to_date:
            raise BadRequestException(detail="Start date cannot be after end date")

        # 1. Fetch all accounts for client
        accounts = (
            db.query(ChartOfAccounts)
            .filter(ChartOfAccounts.client_id == client_id)
            .all()
        )
        if not accounts:
            ChartOfAccountsService.initialize_default_accounts(db, client_id, user)
            accounts = db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id).all()

        acc_by_id = {a.id: a for a in accounts}

        # 2. Query period turnover for Revenue and Expense accounts
        rows = (
            db.query(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit_amount), Decimal("0.00")),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), Decimal("0.00")),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .filter(
                JournalEntry.client_id == client_id,
                JournalEntry.status == "posted",
                JournalEntry.entry_date >= from_date,
                JournalEntry.entry_date <= to_date,
            )
            .group_by(JournalEntryLine.account_id)
            .all()
        )

        turnover: Dict[uuid.UUID, Tuple[Decimal, Decimal]] = {
            r[0]: (r[1] or Decimal("0.00"), r[2] or Decimal("0.00")) for r in rows
        }

        # 3. Categorize into Sections
        revenue_items: List[ReportLineItem] = []
        cogs_items: List[ReportLineItem] = []
        opex_items: List[ReportLineItem] = []

        total_rev = Decimal("0.00")
        total_cogs = Decimal("0.00")
        total_opex = Decimal("0.00")

        for acc in sorted(accounts, key=lambda a: a.account_code):
            dr, cr = turnover.get(acc.id, (Decimal("0.00"), Decimal("0.00")))
            atype = acc.account_type.lower()
            code = acc.account_code

            if atype == "revenue":
                # Net Revenue = Credits - Debits (e.g. Sales less Sales Return)
                net_rev = cr - dr
                total_rev += net_rev
                revenue_items.append(
                    ReportLineItem(
                        account_id=acc.id,
                        account_code=code,
                        name=acc.account_name,
                        amount=net_rev,
                        drill_down_account_id=acc.id,
                    )
                )

            elif atype == "expense":
                # Determine Direct Cost (COGS) vs Operating Expense
                # Standard ICAI: 5010-5090 is Direct Purchase/COGS; 5150 and 6000+ is Operating
                net_exp = dr - cr  # Debits - Credits
                if code.startswith("50"):
                    total_cogs += net_exp
                    cogs_items.append(
                        ReportLineItem(
                            account_id=acc.id,
                            account_code=code,
                            name=acc.account_name,
                            amount=net_exp,
                            drill_down_account_id=acc.id,
                        )
                    )
                else:
                    total_opex += net_exp
                    opex_items.append(
                        ReportLineItem(
                            account_id=acc.id,
                            account_code=code,
                            name=acc.account_name,
                            amount=net_exp,
                            drill_down_account_id=acc.id,
                        )
                    )

        # Calculate percentages if revenue > 0
        def _pct(amt: Decimal) -> Optional[Decimal]:
            if total_rev > Decimal("0.00"):
                return ((amt / total_rev) * Decimal("100.00")).quantize(Decimal("0.01"))
            return None

        for item in revenue_items:
            item.percentage_of_revenue = _pct(item.amount)
        for item in cogs_items:
            item.percentage_of_revenue = _pct(item.amount)
        for item in opex_items:
            item.percentage_of_revenue = _pct(item.amount)

        gross_profit = total_rev - total_cogs
        gross_profit_pct = _pct(gross_profit) or Decimal("0.00")

        net_profit = gross_profit - total_opex
        net_profit_pct = _pct(net_profit) or Decimal("0.00")

        return ProfitAndLossResponse(
            client_id=client_id,
            from_date=from_date,
            to_date=to_date,
            revenue_section=ReportSection(title="Revenue from Operations", total=total_rev, items=revenue_items),
            cost_of_sales_section=ReportSection(title="Cost of Goods Sold (Direct Expenses)", total=total_cogs, items=cogs_items),
            gross_profit=gross_profit,
            gross_profit_margin_pct=gross_profit_pct,
            operating_expenses_section=ReportSection(title="Operating & Administrative Expenses", total=total_opex, items=opex_items),
            total_operating_expenses=total_opex,
            net_profit_before_tax=net_profit,
            net_profit_margin_pct=net_profit_pct,
        )

    # ── 2. Balance Sheet (Statement of Financial Position) ─────────────────────

    @classmethod
    def generate_balance_sheet(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        as_of_date: Optional[date] = None,
    ) -> BalanceSheetResponse:
        """
        Generate full Balance Sheet as of a specific date.
        Guarantees mathematical equality:
        Total Assets == Total Liabilities + (Beginning Equity + Current Net Profit)
        """
        cls.verify_client_access(db, client_id, user)
        effective_date = as_of_date or date.today()

        accounts = (
            db.query(ChartOfAccounts)
            .filter(ChartOfAccounts.client_id == client_id)
            .all()
        )
        if not accounts:
            ChartOfAccountsService.initialize_default_accounts(db, client_id, user)
            accounts = db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id).all()

        # Cumulative turnover up to as_of_date
        rows = (
            db.query(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit_amount), Decimal("0.00")),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), Decimal("0.00")),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .filter(
                JournalEntry.client_id == client_id,
                JournalEntry.status == "posted",
                JournalEntry.entry_date <= effective_date,
            )
            .group_by(JournalEntryLine.account_id)
            .all()
        )

        turnover: Dict[uuid.UUID, Tuple[Decimal, Decimal]] = {
            r[0]: (r[1] or Decimal("0.00"), r[2] or Decimal("0.00")) for r in rows
        }

        # Categorize
        cur_assets: List[ReportLineItem] = []
        non_cur_assets: List[ReportLineItem] = []
        cur_liab: List[ReportLineItem] = []
        non_cur_liab: List[ReportLineItem] = []
        equity_items: List[ReportLineItem] = []

        tot_cur_assets = Decimal("0.00")
        tot_non_cur_assets = Decimal("0.00")
        tot_cur_liab = Decimal("0.00")
        tot_non_cur_liab = Decimal("0.00")
        tot_stated_equity = Decimal("0.00")

        # Dynamic net profit tracker (Revenue Credits - Debits) - (Expense Debits - Credits)
        cum_revenue = Decimal("0.00")
        cum_expenses = Decimal("0.00")

        for acc in sorted(accounts, key=lambda a: a.account_code):
            dr, cr = turnover.get(acc.id, (Decimal("0.00"), Decimal("0.00")))
            atype = acc.account_type.lower()
            code = acc.account_code
            subgroup = (acc.account_subgroup or "").lower()

            if atype == "asset":
                # Asset balance = Debits - Credits
                bal = dr - cr
                item = ReportLineItem(
                    account_id=acc.id,
                    account_code=code,
                    name=acc.account_name,
                    amount=bal,
                    drill_down_account_id=acc.id,
                )
                if code.startswith("13") or "fixed" in subgroup or "non_current" in subgroup:
                    tot_non_cur_assets += bal
                    non_cur_assets.append(item)
                else:
                    tot_cur_assets += bal
                    cur_assets.append(item)

            elif atype == "liability":
                # Liability balance = Credits - Debits
                bal = cr - dr
                item = ReportLineItem(
                    account_id=acc.id,
                    account_code=code,
                    name=acc.account_name,
                    amount=bal,
                    drill_down_account_id=acc.id,
                )
                if code.startswith("22") or "long_term" in subgroup or "non_current" in subgroup:
                    tot_non_cur_liab += bal
                    non_cur_liab.append(item)
                else:
                    tot_cur_liab += bal
                    cur_liab.append(item)

            elif atype == "equity":
                # Stated equity (Capital, reserves) = Credits - Debits
                bal = cr - dr
                tot_stated_equity += bal
                equity_items.append(
                    ReportLineItem(
                        account_id=acc.id,
                        account_code=code,
                        name=acc.account_name,
                        amount=bal,
                        drill_down_account_id=acc.id,
                    )
                )

            elif atype == "revenue":
                cum_revenue += (cr - dr)

            elif atype == "expense":
                cum_expenses += (dr - cr)

        current_period_net_profit = cum_revenue - cum_expenses

        # Append current period profit line item to equity
        equity_items.append(
            ReportLineItem(
                account_id=None,
                account_code="PROFIT",
                name="Current Period Net Profit / (Loss)",
                amount=current_period_net_profit,
            )
        )

        total_assets = tot_cur_assets + tot_non_cur_assets
        total_equity = tot_stated_equity + current_period_net_profit
        total_liabilities = tot_cur_liab + tot_non_cur_liab
        total_eq_liab = total_equity + total_liabilities

        difference = total_assets - total_eq_liab
        is_balanced = abs(difference) < Decimal("0.01")

        return BalanceSheetResponse(
            client_id=client_id,
            as_of_date=effective_date,
            current_assets_section=ReportSection(title="Current Assets", total=tot_cur_assets, items=cur_assets),
            non_current_assets_section=ReportSection(title="Non-Current / Fixed Assets", total=tot_non_cur_assets, items=non_cur_assets),
            total_assets=total_assets,
            current_liabilities_section=ReportSection(title="Current Liabilities", total=tot_cur_liab, items=cur_liab),
            non_current_liabilities_section=ReportSection(title="Non-Current Liabilities", total=tot_non_cur_liab, items=non_cur_liab),
            equity_section=ReportSection(title="Owner's Equity & Reserves", total=total_equity, items=equity_items),
            current_period_net_profit=current_period_net_profit,
            total_equity=total_equity,
            total_liabilities=total_liabilities,
            total_equity_and_liabilities=total_eq_liab,
            is_balanced=is_balanced,
            difference=difference,
        )

    # ── 3. Audit Drill-Down ───────────────────────────────────────────────────

    @classmethod
    def get_report_drilldown(
        cls,
        db: Session,
        client_id: uuid.UUID,
        account_id: uuid.UUID,
        user: User,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> DrillDownResponse:
        """
        Drill down from any financial statement line item directly into underlying
        transactions, vouchers, references, and source documents.
        """
        cls.verify_client_access(db, client_id, user)

        account = (
            db.query(ChartOfAccounts)
            .filter(ChartOfAccounts.id == account_id, ChartOfAccounts.client_id == client_id)
            .first()
        )
        if not account:
            raise NotFoundException(detail=f"Account {account_id} not found")

        query = (
            db.query(JournalEntryLine, JournalEntry)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .filter(
                JournalEntry.client_id == client_id,
                JournalEntry.status == "posted",
                JournalEntryLine.account_id == account_id,
            )
        )

        if from_date:
            query = query.filter(JournalEntry.entry_date >= from_date)
        if to_date:
            query = query.filter(JournalEntry.entry_date <= to_date)

        rows = query.order_by(JournalEntry.entry_date.asc(), JournalEntry.created_at.asc()).all()

        tot_dr = Decimal("0.00")
        tot_cr = Decimal("0.00")
        items: List[DrillDownTransactionItem] = []

        is_debit_normal = account.account_type.lower() in {"asset", "expense"}

        for line, entry in rows:
            dr = line.debit_amount or Decimal("0.00")
            cr = line.credit_amount or Decimal("0.00")
            tot_dr += dr
            tot_cr += cr

            net = (dr - cr) if is_debit_normal else (cr - dr)

            items.append(
                DrillDownTransactionItem(
                    journal_entry_id=entry.id,
                    line_id=line.id,
                    entry_number=entry.entry_number,
                    entry_date=entry.entry_date,
                    entry_type=entry.entry_type,
                    voucher_id=entry.accounting_record_id,
                    document_id=entry.document_id,
                    reference_number=entry.reference_number,
                    narration=entry.narration or line.description,
                    party_name=line.party_name,
                    party_gstin=line.party_gstin,
                    tax_head=line.tax_head,
                    debit=dr,
                    credit=cr,
                    net_effect=net,
                )
            )

        net_bal = (tot_dr - tot_cr) if is_debit_normal else (tot_cr - tot_dr)

        return DrillDownResponse(
            client_id=client_id,
            account_id=account.id,
            account_code=account.account_code,
            account_name=account.account_name,
            account_type=account.account_type,
            from_date=from_date,
            to_date=to_date,
            total_debit=tot_dr,
            total_credit=tot_cr,
            net_balance=net_bal,
            transaction_count=len(items),
            transactions=items,
        )
