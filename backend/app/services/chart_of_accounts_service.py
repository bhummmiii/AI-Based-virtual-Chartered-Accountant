"""
Chart of Accounts Service — Manages persistent client-specific accounts.
Adheres to ICAI accounting standards.
Features:
- Idempotent default account initialization
- Client data isolation
- Cross-client parent rejection
- Hierarchy cycle prevention
- System account protection
"""

import uuid
import logging
from typing import Optional, List, Dict, Any, Set
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.chart_of_accounts import ChartOfAccounts
from app.models.client import Client
from app.models.user import User
from app.schemas.chart_of_accounts import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountTreeNodeResponse,
    DefaultCoaInitResponse,
)
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ForbiddenException,
    BadRequestException,
)

logger = logging.getLogger(__name__)


def determine_account_role(
    code: Optional[str],
    name: Optional[str],
    account_type: Optional[str] = None,
) -> Optional[str]:
    """
    Derive the functional accounting/tax role for an account.
    Resolves legacy vs new charts and resolves the 4020 collision:
      - 4020 "Sales Return Account" -> "SALES_RETURN"
      - 4020 "Inter-State Sales" -> "SALES"
    """
    c = (code or "").strip()
    n = (name or "").strip().lower()

    # 1. Output GST
    if "output" in n and "cgst" in n:
        return "OUTPUT_CGST"
    if "output" in n and "sgst" in n:
        return "OUTPUT_SGST"
    if "output" in n and "igst" in n:
        return "OUTPUT_IGST"
    if "output" in n and "cess" in n:
        return "OUTPUT_CESS"

    # 2. Input GST (ITC)
    if "input" in n and "cgst" in n:
        return "INPUT_CGST"
    if "input" in n and "sgst" in n:
        return "INPUT_SGST"
    if "input" in n and "igst" in n:
        return "INPUT_IGST"
    if "input" in n and "cess" in n:
        return "INPUT_CESS"

    # Code fallbacks for tax accounts
    if c in ("2110", "2020") and "cgst" in n:
        return "OUTPUT_CGST"
    if c in ("2120", "2030") and "sgst" in n:
        return "OUTPUT_SGST"
    if c in ("2130", "2040") and "igst" in n:
        return "OUTPUT_IGST"
    if c in ("1210", "1060") and "cgst" in n:
        return "INPUT_CGST"
    if c in ("1220", "1070") and "sgst" in n:
        return "INPUT_SGST"
    if c in ("1230", "1080") and "igst" in n:
        return "INPUT_IGST"

    # 3. Sales Returns vs Sales (Handles 4020 collision by name+role)
    if "sales return" in n or "sale return" in n or (c == "4030" and "return" in n):
        return "SALES_RETURN"
    if "purchase return" in n or c == "5020":
        return "PURCHASE_RETURN"

    if "inter-state sale" in n or "interstate sale" in n or "inter state sale" in n:
        return "SALES"
    if "sales" in n or "sale revenue" in n or c == "4010":
        return "SALES"
    if (c == "4020" and "inter" in n) or (c == "4020" and "return" not in n and "sale" in n):
        return "SALES"
    if c == "4020" and "return" in n:
        return "SALES_RETURN"

    # 4. Purchases
    if "purchase" in n or c == "5010":
        return "PURCHASE"

    # 5. Debtors & Creditors
    if ("debtor" in n or "receivable" in n or (c in ("1100", "1010") and "debtor" in n)) and "cash" not in n:
        return "DEBTORS"
    if ("creditor" in n or "trade payable" in n or c == "2010") and "tds" not in n:
        return "CREDITORS"

    # 6. Other Operating Income
    if "other income" in n or "operating income" in n or c == "4030":
        return "OTHER_INCOME"

    return None


# Standard Indian ICAI Chart of Accounts Template
ICAI_DEFAULT_ACCOUNTS: List[Dict[str, Any]] = [
    # ── 1. ASSETS (1000s) ───────────────────────────────────
    {
        "account_code": "1010",
        "account_name": "Cash in Hand",
        "account_type": "asset",
        "account_subgroup": "cash_and_bank",
        "description": "Physical cash vault and petty cash balance",
        "is_system": True,
        "role": None,
    },
    {
        "account_code": "1020",
        "account_name": "Main Bank Current Account",
        "account_type": "asset",
        "account_subgroup": "cash_and_bank",
        "description": "Primary commercial operating bank account",
        "is_system": True,
        "role": None,
    },
    {
        "account_code": "1100",
        "account_name": "Sundry Debtors (Trade Receivables)",
        "account_type": "asset",
        "account_subgroup": "sundry_debtors",
        "description": "Gross commercial receivables from customers",
        "is_system": True,
        "role": "DEBTORS",
    },
    {
        "account_code": "1210",
        "account_name": "Input CGST Account (ITC)",
        "account_type": "asset",
        "account_subgroup": "duties_and_taxes",
        "description": "Central GST Input Tax Credit claimable",
        "is_system": True,
        "role": "INPUT_CGST",
    },
    {
        "account_code": "1220",
        "account_name": "Input SGST Account (ITC)",
        "account_type": "asset",
        "account_subgroup": "duties_and_taxes",
        "description": "State GST Input Tax Credit claimable",
        "is_system": True,
        "role": "INPUT_SGST",
    },
    {
        "account_code": "1230",
        "account_name": "Input IGST Account (ITC)",
        "account_type": "asset",
        "account_subgroup": "duties_and_taxes",
        "description": "Integrated GST Input Tax Credit claimable",
        "is_system": True,
        "role": "INPUT_IGST",
    },
    {
        "account_code": "1240",
        "account_name": "Input Cess Account (ITC)",
        "account_type": "asset",
        "account_subgroup": "duties_and_taxes",
        "description": "Compensation Cess Input Tax Credit claimable",
        "is_system": True,
        "role": "INPUT_CESS",
    },

    # ── 2. LIABILITIES (2000s) ───────────────────────────────
    {
        "account_code": "2010",
        "account_name": "Sundry Creditors (Trade Payables)",
        "account_type": "liability",
        "account_subgroup": "sundry_creditors",
        "description": "Gross commercial payables to vendors and suppliers",
        "is_system": True,
        "role": "CREDITORS",
    },
    {
        "account_code": "2110",
        "account_name": "Output CGST Account",
        "account_type": "liability",
        "account_subgroup": "duties_and_taxes",
        "description": "Central GST statutory tax collected on sales",
        "is_system": True,
        "role": "OUTPUT_CGST",
    },
    {
        "account_code": "2120",
        "account_name": "Output SGST Account",
        "account_type": "liability",
        "account_subgroup": "duties_and_taxes",
        "description": "State GST statutory tax collected on sales",
        "is_system": True,
        "role": "OUTPUT_SGST",
    },
    {
        "account_code": "2130",
        "account_name": "Output IGST Account",
        "account_type": "liability",
        "account_subgroup": "duties_and_taxes",
        "description": "Integrated GST statutory tax collected on sales",
        "is_system": True,
        "role": "OUTPUT_IGST",
    },
    {
        "account_code": "2140",
        "account_name": "Output Cess Account",
        "account_type": "liability",
        "account_subgroup": "duties_and_taxes",
        "description": "Compensation Cess collected on sales",
        "is_system": True,
        "role": "OUTPUT_CESS",
    },
    {
        "account_code": "2150",
        "account_name": "GST Tax Payment Clearing Account",
        "account_type": "liability",
        "account_subgroup": "duties_and_taxes",
        "description": "Clearing account for statutory GST challan payments",
        "is_system": True,
        "role": None,
    },
    {
        "account_code": "2200",
        "account_name": "TDS Payable Account",
        "account_type": "liability",
        "account_subgroup": "statutory_liabilities",
        "description": "Tax Deducted at Source statutory liability",
        "is_system": True,
        "role": None,
    },

    # ── 3. EQUITY (3000s) ────────────────────────────────────
    {
        "account_code": "3010",
        "account_name": "Owner's Capital / Partner Capital",
        "account_type": "equity",
        "account_subgroup": "capital_account",
        "description": "Owner / Partner capital contributions",
        "is_system": True,
        "role": None,
    },
    {
        "account_code": "3020",
        "account_name": "Retained Earnings / Reserves & Surplus",
        "account_type": "equity",
        "account_subgroup": "reserves_and_surplus",
        "description": "Cumulative retained earnings from previous financial years",
        "is_system": True,
        "role": None,
    },

    # ── 4. REVENUE (4000s) ───────────────────────────────────
    {
        "account_code": "4010",
        "account_name": "Sales Revenue Account",
        "account_type": "revenue",
        "account_subgroup": "operating_revenue",
        "description": "Taxable outward supply and sales consideration",
        "is_system": True,
        "role": "SALES",
    },
    {
        "account_code": "4020",
        "account_name": "Sales Return Account",
        "account_type": "revenue",
        "account_subgroup": "operating_revenue",
        "description": "Credit note sales returns contra revenue",
        "is_system": True,
        "role": "SALES_RETURN",
    },
    {
        "account_code": "4030",
        "account_name": "Other Operating Income",
        "account_type": "revenue",
        "account_subgroup": "other_income",
        "description": "Discounts received, commission, and miscellaneous operating income",
        "is_system": False,
        "role": "OTHER_INCOME",
    },

    # ── 5. EXPENSES (5000s) ──────────────────────────────────
    {
        "account_code": "5010",
        "account_name": "Purchase Expense Account",
        "account_type": "expense",
        "account_subgroup": "cost_of_goods_sold",
        "description": "Cost of materials, goods, and direct trading purchases",
        "is_system": True,
        "role": "PURCHASE",
    },
    {
        "account_code": "5020",
        "account_name": "Purchase Return Account",
        "account_type": "expense",
        "account_subgroup": "cost_of_goods_sold",
        "description": "Debit note purchase returns contra expense",
        "is_system": True,
        "role": "PURCHASE_RETURN",
    },
    {
        "account_code": "5110",
        "account_name": "Rent Expense",
        "account_type": "expense",
        "account_subgroup": "indirect_expenses",
        "description": "Office and commercial premises rent consideration",
        "is_system": False,
    },
    {
        "account_code": "5120",
        "account_name": "Salaries and Wages",
        "account_type": "expense",
        "account_subgroup": "indirect_expenses",
        "description": "Employee compensation, wages, and staff welfare",
        "is_system": False,
    },
    {
        "account_code": "5130",
        "account_name": "Professional & Legal Charges",
        "account_type": "expense",
        "account_subgroup": "indirect_expenses",
        "description": "Audit, legal, consultancy, and compliance professional fees",
        "is_system": False,
    },
    {
        "account_code": "5140",
        "account_name": "Bank Charges & Commission",
        "account_type": "expense",
        "account_subgroup": "indirect_expenses",
        "description": "Bank transaction fees, processing charges, and interest",
        "is_system": False,
    },
    {
        "account_code": "5150",
        "account_name": "Utilities & Office Expenses",
        "account_type": "expense",
        "account_subgroup": "indirect_expenses",
        "description": "Electricity, internet, stationery, and office upkeep",
        "is_system": False,
    },
]


class ChartOfAccountsService:

    @staticmethod
    def verify_client_access(db: Session, client_id: uuid.UUID, user: User) -> Client:
        """
        Verify that client exists and authenticated user has authorization.
        Admins can access any client; standard users can only access their own clients.
        """
        client = db.query(Client).filter(Client.id == client_id, Client.status != "deleted").first()
        if not client:
            raise NotFoundException(detail=f"Client {client_id} not found")

        if user.role != "admin" and client.user_id is not None and client.user_id != user.id:
            raise ForbiddenException(detail="You are not authorized to manage the Chart of Accounts for this client")

        return client

    @classmethod
    def initialize_default_accounts(cls, db: Session, client_id: uuid.UUID, user: User) -> DefaultCoaInitResponse:
        """
        Idempotently initialize standard ICAI default accounts for a client.
        Preserves existing accounts; never duplicates or overwrites customized accounts.
        """
        cls.verify_client_access(db, client_id, user)

        # Retrieve existing account codes and names for this client
        existing = db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id).all()
        existing_codes = {acc.account_code for acc in existing}
        existing_names = {acc.account_name.strip().lower() for acc in existing}

        new_accounts: List[ChartOfAccounts] = []
        skipped_count = 0

        for item in ICAI_DEFAULT_ACCOUNTS:
            code = item["account_code"]
            name = item["account_name"].strip().lower()

            if code in existing_codes or name in existing_names:
                skipped_count += 1
                continue

            acc = ChartOfAccounts(
                client_id=client_id,
                account_code=item["account_code"],
                account_name=item["account_name"],
                account_type=item["account_type"],
                account_subgroup=item.get("account_subgroup"),
                role=item.get("role") or determine_account_role(item["account_code"], item["account_name"], item["account_type"]),
                description=item.get("description"),
                is_active=True,
                is_system=item.get("is_system", False),
            )
            new_accounts.append(acc)
            existing_codes.add(code)
            existing_names.add(name)

        if new_accounts:
            db.add_all(new_accounts)
            db.commit()

        total_accounts = db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id).count()

        logger.info(
            "Initialized CoA for client %s: %d created, %d skipped, %d total",
            client_id, len(new_accounts), skipped_count, total_accounts
        )

        return DefaultCoaInitResponse(
            client_id=client_id,
            created_count=len(new_accounts),
            skipped_count=skipped_count,
            total_accounts=total_accounts,
            message=(
                f"Chart of Accounts initialized: {len(new_accounts)} account(s) created, "
                f"{skipped_count} existing account(s) preserved."
            ),
        )

    @classmethod
    def get_accounts(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        account_type: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[ChartOfAccounts]:
        """List flat chart of accounts for a client with optional filters."""
        cls.verify_client_access(db, client_id, user)

        query = db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id)

        if not include_inactive:
            query = query.filter(ChartOfAccounts.is_active.is_(True))

        if account_type:
            query = query.filter(ChartOfAccounts.account_type == account_type.lower())

        return query.order_by(ChartOfAccounts.account_code.asc()).all()

    @classmethod
    def get_account_tree(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        include_inactive: bool = False,
    ) -> List[AccountTreeNodeResponse]:
        """Retrieve client accounts structured as a nested parent-subaccount tree."""
        all_accounts = cls.get_accounts(db, client_id, user, include_inactive=include_inactive)

        # Build adjacency mapping
        nodes: Dict[uuid.UUID, AccountTreeNodeResponse] = {}
        for acc in all_accounts:
            nodes[acc.id] = AccountTreeNodeResponse(
                id=acc.id,
                client_id=acc.client_id,
                account_code=acc.account_code,
                account_name=acc.account_name,
                account_type=acc.account_type,
                account_subgroup=acc.account_subgroup,
                parent_account_id=acc.parent_account_id,
                description=acc.description,
                is_active=acc.is_active,
                is_system=acc.is_system,
                created_at=acc.created_at,
                updated_at=acc.updated_at,
                sub_accounts=[],
            )

        root_nodes: List[AccountTreeNodeResponse] = []
        for acc in all_accounts:
            node = nodes[acc.id]
            if acc.parent_account_id and acc.parent_account_id in nodes:
                nodes[acc.parent_account_id].sub_accounts.append(node)
            else:
                root_nodes.append(node)

        return root_nodes

    @classmethod
    def get_account_by_id(cls, db: Session, account_id: uuid.UUID, user: User) -> ChartOfAccounts:
        """Fetch a specific account and verify user authorization on its client."""
        acc = db.query(ChartOfAccounts).filter(ChartOfAccounts.id == account_id).first()
        if not acc:
            raise NotFoundException(detail=f"Account {account_id} not found")

        cls.verify_client_access(db, acc.client_id, user)
        return acc

    @classmethod
    def create_account(cls, db: Session, data: AccountCreate, user: User) -> ChartOfAccounts:
        """Create a custom account for a client with strict uniqueness and parent validation."""
        cls.verify_client_access(db, data.client_id, user)

        # 1. Uniqueness check for account_code within client
        existing_code = (
            db.query(ChartOfAccounts)
            .filter(
                ChartOfAccounts.client_id == data.client_id,
                ChartOfAccounts.account_code == data.account_code,
            )
            .first()
        )
        if existing_code:
            raise ConflictException(
                detail=f"Account code '{data.account_code}' already exists for this client (Account: '{existing_code.account_name}')"
            )

        # 2. Uniqueness check for account_name within client
        existing_name = (
            db.query(ChartOfAccounts)
            .filter(
                ChartOfAccounts.client_id == data.client_id,
                func.lower(ChartOfAccounts.account_name) == data.account_name.lower(),
            )
            .first()
        )
        if existing_name:
            raise ConflictException(
                detail=f"Account name '{data.account_name}' already exists for this client (Code: '{existing_name.account_code}')"
            )

        # 3. Parent account validation (must belong to same client)
        if data.parent_account_id:
            parent = db.query(ChartOfAccounts).filter(ChartOfAccounts.id == data.parent_account_id).first()
            if not parent:
                raise NotFoundException(detail="Parent account not found")
            if parent.client_id != data.client_id:
                raise BadRequestException(detail="Parent account must belong to the same client")
            if not parent.is_active:
                raise BadRequestException(detail="Cannot assign an inactive account as parent")

        new_account = ChartOfAccounts(
            client_id=data.client_id,
            account_code=data.account_code,
            account_name=data.account_name,
            account_type=data.account_type,
            account_subgroup=data.account_subgroup,
            role=data.role or determine_account_role(data.account_code, data.account_name, data.account_type),
            parent_account_id=data.parent_account_id,
            description=data.description,
            is_active=data.is_active,
            is_system=False,
        )

        db.add(new_account)
        db.commit()
        db.refresh(new_account)

        logger.info("Created account %s (%s) for client %s", new_account.account_code, new_account.account_name, data.client_id)
        return new_account

    @classmethod
    def update_account(cls, db: Session, account_id: uuid.UUID, data: AccountUpdate, user: User) -> ChartOfAccounts:
        """Update account properties with system-account guards and hierarchy cycle checks."""
        acc = cls.get_account_by_id(db, account_id, user)

        # Name update uniqueness check
        if data.account_name and data.account_name.strip().lower() != acc.account_name.strip().lower():
            conflict = (
                db.query(ChartOfAccounts)
                .filter(
                    ChartOfAccounts.client_id == acc.client_id,
                    ChartOfAccounts.id != acc.id,
                    func.lower(ChartOfAccounts.account_name) == data.account_name.strip().lower(),
                )
                .first()
            )
            if conflict:
                raise ConflictException(detail=f"Account name '{data.account_name}' already in use by code '{conflict.account_code}'")
            acc.account_name = data.account_name.strip()

        # Parent account cycle check
        if data.parent_account_id is not None:
            if data.parent_account_id == acc.id:
                raise BadRequestException(detail="An account cannot be its own parent")

            parent = db.query(ChartOfAccounts).filter(ChartOfAccounts.id == data.parent_account_id).first()
            if not parent:
                raise NotFoundException(detail="Parent account not found")
            if parent.client_id != acc.client_id:
                raise BadRequestException(detail="Parent account must belong to the same client")

            # Check if parent is a descendant of acc (prevent cycle)
            descendant_ids = cls._get_descendant_ids(db, acc.id)
            if data.parent_account_id in descendant_ids:
                raise BadRequestException(detail="Hierarchy cycle detected: Cannot set an account's descendant as its parent")

            acc.parent_account_id = data.parent_account_id

        if data.account_subgroup is not None:
            acc.account_subgroup = data.account_subgroup

        if data.role is not None:
            acc.role = data.role

        if data.description is not None:
            acc.description = data.description

        if data.is_active is not None:
            if not data.is_active and acc.is_system:
                raise BadRequestException(detail="Essential system accounts cannot be deactivated")
            acc.is_active = data.is_active

        db.commit()
        db.refresh(acc)
        return acc

    @classmethod
    def delete_account(cls, db: Session, account_id: uuid.UUID, user: User) -> None:
        """Safely delete a custom account. Rejects system accounts or accounts with children."""
        acc = cls.get_account_by_id(db, account_id, user)

        if acc.is_system:
            raise BadRequestException(detail="Core system accounts cannot be deleted")

        has_children = db.query(ChartOfAccounts).filter(ChartOfAccounts.parent_account_id == acc.id).first()
        if has_children:
            raise BadRequestException(detail="Cannot delete account with existing sub-accounts. Please reassign or delete sub-accounts first.")

        db.delete(acc)
        db.commit()
        logger.info("Deleted account %s for client %s", account_id, acc.client_id)

    @classmethod
    def _get_descendant_ids(cls, db: Session, parent_id: uuid.UUID) -> Set[uuid.UUID]:
        """Recursively gather all descendant IDs to prevent cyclical trees."""
        descendants: Set[uuid.UUID] = set()
        queue = [parent_id]
        while queue:
            curr = queue.pop(0)
            children = db.query(ChartOfAccounts.id).filter(ChartOfAccounts.parent_account_id == curr).all()
            for (child_id,) in children:
                if child_id not in descendants:
                    descendants.add(child_id)
                    queue.append(child_id)
        return descendants
