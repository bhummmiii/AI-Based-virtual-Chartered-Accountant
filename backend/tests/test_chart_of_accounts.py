"""
Unit and Integration Tests for Chart of Accounts (Phase 1).

Tests:
1. Standard ICAI default accounts initialization.
2. Initialization idempotency (running multiple times creates 0 duplicates).
3. Client data isolation (clients can have identical codes without collision).
4. Code and name uniqueness within a single client.
5. Parent-subaccount hierarchy and tree generation.
6. Cross-client parent rejection.
7. Hierarchy cycle detection (cannot set an account's descendant as its parent).
8. Protection of system accounts (cannot be deleted or deactivated).
9. Authorization and client access control.
"""

import sys
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.session import Base
from app.models.user import User
from app.models.client import Client
from app.models.chart_of_accounts import ChartOfAccounts
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.schemas.chart_of_accounts import AccountCreate, AccountUpdate
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ForbiddenException,
    BadRequestException,
)


@pytest.fixture
def db_session():
    """Create a completely isolated, in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[User.__table__, Client.__table__, ChartOfAccounts.__table__],
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def setup_users_and_clients(db_session):
    """Seed test users and clients for multi-tenant isolation testing."""
    # User 1: Regular CA
    ca_user = User(
        id=uuid.uuid4(),
        email="ca1@example.com",
        full_name="CA Sharma",
        password_hash="hashed_secret",
        role="ca",
        is_active=True,
    )
    # User 2: Another CA
    other_ca = User(
        id=uuid.uuid4(),
        email="ca2@example.com",
        full_name="CA Verma",
        password_hash="hashed_secret",
        role="ca",
        is_active=True,
    )
    # User 3: Admin
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="System Admin",
        password_hash="hashed_secret",
        role="admin",
        is_active=True,
    )

    db_session.add_all([ca_user, other_ca, admin_user])
    db_session.flush()

    # Client A owned by User 1
    client_a = Client(
        id=uuid.uuid4(),
        user_id=ca_user.id,
        client_code="CLI-A",
        company_name="Apex Enterprises",
        contact_person="Ramesh Patel",
        status="active",
    )
    # Client B owned by User 2
    client_b = Client(
        id=uuid.uuid4(),
        user_id=other_ca.id,
        client_code="CLI-B",
        company_name="Bharat Logistics",
        contact_person="Suresh Nair",
        status="active",
    )

    db_session.add_all([client_a, client_b])
    db_session.commit()

    return {
        "ca_user": ca_user,
        "other_ca": other_ca,
        "admin_user": admin_user,
        "client_a": client_a,
        "client_b": client_b,
    }


# ── 1. Default Accounts Initialization & Idempotency ────────────────────

def test_default_coa_initialization(db_session, setup_users_and_clients):
    data = setup_users_and_clients
    client_a = data["client_a"]
    user = data["ca_user"]

    res = ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, user)
    assert res.created_count > 15
    assert res.skipped_count == 0
    assert res.total_accounts == res.created_count

    # Check key ICAI accounts exist
    accounts = ChartOfAccountsService.get_accounts(db_session, client_a.id, user)
    codes = {a.account_code: a for a in accounts}

    assert "1010" in codes  # Cash in Hand
    assert "1020" in codes  # Bank Current Account
    assert "1100" in codes  # Sundry Debtors
    assert "1210" in codes  # Input CGST
    assert "2010" in codes  # Sundry Creditors
    assert "2110" in codes  # Output CGST
    assert "4010" in codes  # Sales Revenue
    assert "5010" in codes  # Purchase Expense

    # Verify classifications
    assert codes["1010"].account_type == "asset"
    assert codes["2010"].account_type == "liability"
    assert codes["4010"].account_type == "revenue"
    assert codes["5010"].account_type == "expense"


def test_initialization_idempotency(db_session, setup_users_and_clients):
    data = setup_users_and_clients
    client_a = data["client_a"]
    user = data["ca_user"]

    # First run
    res1 = ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, user)
    total_first = res1.total_accounts

    # Second run — must not duplicate anything
    res2 = ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, user)
    assert res2.created_count == 0
    assert res2.skipped_count == total_first
    assert res2.total_accounts == total_first


# ── 2. Client Data Isolation & Uniqueness ─────────────────────────────────

def test_client_data_isolation(db_session, setup_users_and_clients):
    data = setup_users_and_clients
    client_a = data["client_a"]
    client_b = data["client_b"]
    user_a = data["ca_user"]
    user_b = data["other_ca"]

    # Both clients initialize their own CoA
    res_a = ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, user_a)
    res_b = ChartOfAccountsService.initialize_default_accounts(db_session, client_b.id, user_b)

    # Identical codes exist for both clients without collision
    acc_a = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_a.id, ChartOfAccounts.account_code == "1010").first()
    acc_b = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_b.id, ChartOfAccounts.account_code == "1010").first()

    assert acc_a is not None
    assert acc_b is not None
    assert acc_a.id != acc_b.id
    assert acc_a.client_id == client_a.id
    assert acc_b.client_id == client_b.id


def test_code_and_name_uniqueness_within_client(db_session, setup_users_and_clients):
    data = setup_users_and_clients
    client_a = data["client_a"]
    user_a = data["ca_user"]

    # Initialize default accounts
    ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, user_a)

    # Duplicate code attempt
    with pytest.raises(ConflictException) as exc1:
        ChartOfAccountsService.create_account(
            db_session,
            AccountCreate(
                client_id=client_a.id,
                account_code="1010",  # Already exists (Cash)
                account_name="Custom Petty Cash",
                account_type="asset",
            ),
            user_a,
        )
    assert "already exists" in str(exc1.value.detail)

    # Duplicate name attempt
    with pytest.raises(ConflictException) as exc2:
        ChartOfAccountsService.create_account(
            db_session,
            AccountCreate(
                client_id=client_a.id,
                account_code="1099",
                account_name="Cash in Hand",  # Already exists
                account_type="asset",
            ),
            user_a,
        )
    assert "already exists" in str(exc2.value.detail)


# ── 3. Parent-Subaccount Hierarchy & Tree Generation ──────────────────────

def test_parent_hierarchy_and_tree(db_session, setup_users_and_clients):
    data = setup_users_and_clients
    client_a = data["client_a"]
    user_a = data["ca_user"]

    ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, user_a)

    # Find parent "Sundry Debtors" (1100)
    parent_debtors = db_session.query(ChartOfAccounts).filter(
        ChartOfAccounts.client_id == client_a.id,
        ChartOfAccounts.account_code == "1100"
    ).first()

    # Create sub-account for specific customer
    sub_debtor = ChartOfAccountsService.create_account(
        db_session,
        AccountCreate(
            client_id=client_a.id,
            account_code="1101",
            account_name="Tata Motors Ltd (Debtor)",
            account_type="asset",
            account_subgroup="sundry_debtors",
            parent_account_id=parent_debtors.id,
        ),
        user_a,
    )
    assert sub_debtor.parent_account_id == parent_debtors.id

    # Retrieve tree
    tree = ChartOfAccountsService.get_account_tree(db_session, client_a.id, user_a)
    debtor_root = next((node for node in tree if node.account_code == "1100"), None)
    assert debtor_root is not None
    assert len(debtor_root.sub_accounts) == 1
    assert debtor_root.sub_accounts[0].account_code == "1101"
    assert debtor_root.sub_accounts[0].account_name == "Tata Motors Ltd (Debtor)"


def test_cross_client_parent_rejection(db_session, setup_users_and_clients):
    data = setup_users_and_clients
    client_a = data["client_a"]
    client_b = data["client_b"]
    user_a = data["ca_user"]
    user_b = data["other_ca"]

    ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, user_a)
    ChartOfAccountsService.initialize_default_accounts(db_session, client_b.id, user_b)

    # Get Client B's account
    client_b_acc = db_session.query(ChartOfAccounts).filter(
        ChartOfAccounts.client_id == client_b.id,
        ChartOfAccounts.account_code == "1100"
    ).first()

    # Attempt to use Client B's account as parent for Client A's new account
    with pytest.raises(BadRequestException) as exc:
        ChartOfAccountsService.create_account(
            db_session,
            AccountCreate(
                client_id=client_a.id,
                account_code="1199",
                account_name="Alien Sub-Debtor",
                account_type="asset",
                parent_account_id=client_b_acc.id,
            ),
            user_a,
        )
    assert "must belong to the same client" in str(exc.value.detail)


def test_hierarchy_cycle_prevention(db_session, setup_users_and_clients):
    data = setup_users_and_clients
    client_a = data["client_a"]
    user_a = data["ca_user"]

    ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, user_a)
    cash_acc = db_session.query(ChartOfAccounts).filter(
        ChartOfAccounts.client_id == client_a.id,
        ChartOfAccounts.account_code == "1010"
    ).first()

    # Attempt to set account as its own parent
    with pytest.raises(BadRequestException) as exc:
        ChartOfAccountsService.update_account(
            db_session,
            cash_acc.id,
            AccountUpdate(parent_account_id=cash_acc.id),
            user_a,
        )
    assert "cannot be its own parent" in str(exc.value.detail)


# ── 4. System Accounts Protection ─────────────────────────────────────────

def test_system_account_deletion_and_deactivation_guard(db_session, setup_users_and_clients):
    data = setup_users_and_clients
    client_a = data["client_a"]
    user_a = data["ca_user"]

    ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, user_a)

    system_acc = db_session.query(ChartOfAccounts).filter(
        ChartOfAccounts.client_id == client_a.id,
        ChartOfAccounts.account_code == "1010",
        ChartOfAccounts.is_system == True
    ).first()

    # Attempt to delete system account
    with pytest.raises(BadRequestException) as exc_del:
        ChartOfAccountsService.delete_account(db_session, system_acc.id, user_a)
    assert "Core system accounts cannot be deleted" in str(exc_del.value.detail)

    # Attempt to deactivate system account
    with pytest.raises(BadRequestException) as exc_deact:
        ChartOfAccountsService.update_account(
            db_session,
            system_acc.id,
            AccountUpdate(is_active=False),
            user_a,
        )
    assert "Essential system accounts cannot be deactivated" in str(exc_deact.value.detail)


# ── 5. Authorization & Multi-tenant Control ───────────────────────────────

def test_unauthorized_client_access(db_session, setup_users_and_clients):
    data = setup_users_and_clients
    client_a = data["client_a"]  # Owned by User 1
    other_ca = data["other_ca"]  # User 2

    # User 2 tries to initialize Client A's accounts
    with pytest.raises(ForbiddenException) as exc1:
        ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, other_ca)
    assert "not authorized" in str(exc1.value.detail).lower()

    # User 2 tries to list Client A's accounts
    with pytest.raises(ForbiddenException) as exc2:
        ChartOfAccountsService.get_accounts(db_session, client_a.id, other_ca)
    assert "not authorized" in str(exc2.value.detail).lower()

    # Admin CAN access Client A's accounts
    admin = data["admin_user"]
    res_admin = ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, admin)
    assert res_admin.created_count > 0
