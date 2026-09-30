"""Create chart_of_accounts table

Revision ID: 0005_add_chart_of_accounts
Revises: 0004_add_accounting_draft_fields
Create Date: 2026-09-29 00:00:00 UTC

Adds persistent, client-isolated chart_of_accounts table adhering to ICAI classifications:
- UUID primary key
- Client isolation with FK to clients.id (CASCADE)
- Account code and name uniqueness per client
- Self-referential parent_account_id for sub-account hierarchy
- Account type (asset, liability, equity, revenue, expense) and subgroups
- Active/inactive toggle and is_system protection flag
"""

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0005_add_chart_of_accounts"
down_revision = "0004_add_accounting_draft_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chart_of_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("account_code", sa.String(50), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(50), nullable=False),
        sa.Column("account_subgroup", sa.String(100), nullable=True),
        sa.Column(
            "parent_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chart_of_accounts.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("client_id", "account_code", name="uq_coa_client_code"),
        sa.UniqueConstraint("client_id", "account_name", name="uq_coa_client_name"),
    )

    op.create_index("ix_coa_client_type", "chart_of_accounts", ["client_id", "account_type"])
    op.create_index("ix_coa_client_active", "chart_of_accounts", ["client_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_coa_client_active", table_name="chart_of_accounts")
    op.drop_index("ix_coa_client_type", table_name="chart_of_accounts")
    op.drop_table("chart_of_accounts")
