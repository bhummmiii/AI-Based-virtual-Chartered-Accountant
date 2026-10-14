"""Add government updates quality fields (K1, K3, K4, K6, K10, K12).

Revision ID: 0012_add_gov_quality_fields
Revises: 0011_add_gov_updates_tables
Create Date: 2026-10-14 19:30:00 UTC
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0012_add_gov_quality_fields"
down_revision = "0011_add_gov_updates_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Update gov_sources with K1 fields
    if insp.has_table("gov_sources"):
        existing_cols = {c["name"] for c in insp.get_columns("gov_sources")}
        
        if "last_attempt_at" not in existing_cols:
            op.add_column("gov_sources", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        if "consecutive_failures" not in existing_cols:
            op.add_column("gov_sources", sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"))
        if "failure_stage" not in existing_cols:
            op.add_column("gov_sources", sa.Column("failure_stage", sa.String(50), nullable=True))
        if "next_retry_at" not in existing_cols:
            op.add_column("gov_sources", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
        if "last_probe_at" not in existing_cols:
            op.add_column("gov_sources", sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True))

    # 2. Update gov_updates with K3, K4, K6, K10, K12 fields
    if insp.has_table("gov_updates"):
        existing_cols_u = {c["name"] for c in insp.get_columns("gov_updates")}

        if "issue_date_source" not in existing_cols_u:
            op.add_column("gov_updates", sa.Column("issue_date_source", sa.String(50), nullable=True))
        if "date_precision" not in existing_cols_u:
            op.add_column("gov_updates", sa.Column("date_precision", sa.String(20), nullable=False, server_default="day"))
        if "doc_number_source" not in existing_cols_u:
            op.add_column("gov_updates", sa.Column("doc_number_source", sa.String(50), nullable=True))
        if "link_quality" not in existing_cols_u:
            op.add_column("gov_updates", sa.Column("link_quality", sa.String(50), nullable=False, server_default="direct_document"))
        if "ministry" not in existing_cols_u:
            op.add_column("gov_updates", sa.Column("ministry", sa.String(255), nullable=True))
        if "hidden" not in existing_cols_u:
            op.add_column("gov_updates", sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        if "hidden_reason" not in existing_cols_u:
            op.add_column("gov_updates", sa.Column("hidden_reason", sa.String(255), nullable=True))
        if "is_manual" not in existing_cols_u:
            op.add_column("gov_updates", sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        if "manual_added_by" not in existing_cols_u:
            op.add_column("gov_updates", sa.Column("manual_added_by", UUID(as_uuid=True), nullable=True))
        if "manual_added_at" not in existing_cols_u:
            op.add_column("gov_updates", sa.Column("manual_added_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    pass
