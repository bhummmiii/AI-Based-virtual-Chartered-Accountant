"""Add extended client fields: billing_cycle, contact_number, email_address, location

Revision ID: 0002_add_client_extended_fields
Revises: 0001_initial_schema
Create Date: 2026-07-28 12:00:00 UTC

Safe migration — adds 4 nullable columns to clients table.
All existing rows keep their data intact (NULL for new columns).
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_client_extended_fields"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("billing_cycle",   sa.String(20),  nullable=True, server_default="monthly"))
    op.add_column("clients", sa.Column("contact_number",  sa.String(20),  nullable=True))
    op.add_column("clients", sa.Column("email_address",   sa.String(255), nullable=True))
    op.add_column("clients", sa.Column("location",        sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "location")
    op.drop_column("clients", "email_address")
    op.drop_column("clients", "contact_number")
    op.drop_column("clients", "billing_cycle")
