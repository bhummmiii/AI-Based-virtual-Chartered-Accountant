"""Create accounting_periods table for fiscal period controls and lockout

Revision ID: 0007_add_accounting_periods
Revises: 0006_add_journal_entries
Create Date: 2026-09-29 00:00:00 UTC
"""

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0007_add_accounting_periods"
down_revision = "0006_add_journal_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounting_periods",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_name", sa.String(100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "closed_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("closing_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("client_id", "period_name", name="uq_accounting_period_client_name"),
    )
    op.create_index("ix_accounting_periods_client_id", "accounting_periods", ["client_id"])
    op.create_index(
        "ix_accounting_period_client_dates",
        "accounting_periods",
        ["client_id", "start_date", "end_date"],
    )
    op.create_index("ix_accounting_period_status", "accounting_periods", ["status"])


def downgrade() -> None:
    op.drop_index("ix_accounting_period_status", table_name="accounting_periods")
    op.drop_index("ix_accounting_period_client_dates", table_name="accounting_periods")
    op.drop_index("ix_accounting_periods_client_id", table_name="accounting_periods")
    op.drop_table("accounting_periods")
