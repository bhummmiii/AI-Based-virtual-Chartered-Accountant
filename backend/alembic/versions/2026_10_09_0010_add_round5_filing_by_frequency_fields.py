"""Add round 5 filing by frequency fields: period_type and frequency_at_filing on gst_records.

Revision ID: 0010_round5_filing_by_frequency_fields
Revises: 0009_round4_gst_parity_fields
Create Date: 2026-10-09 10:00:00 UTC
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0010_round5_filing_freq"
down_revision = "0009_round4_gst_parity_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gst_records", sa.Column("period_type", sa.String(20), nullable=True))
    op.add_column("gst_records", sa.Column("frequency_at_filing", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("gst_records", "frequency_at_filing")
    op.drop_column("gst_records", "period_type")
