"""Add government updates module tables: gov_sources, gov_updates, gov_fetch_runs, gov_saved_updates.

Revision ID: 0011_add_gov_updates_tables
Revises: 0010_round5_filing_freq
Create Date: 2026-10-12 12:00:00 UTC
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0011_add_gov_updates_tables"
down_revision = "0010_round5_filing_freq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. gov_sources
    if not insp.has_table("gov_sources"):
        op.create_table(
            "gov_sources",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(100), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("base_url", sa.String(500), nullable=False),
            sa.Column("domain", sa.String(255), nullable=False),
            sa.Column("tier", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("scope", sa.String(50), nullable=False, server_default="national"),
            sa.Column("state_code", sa.String(10), nullable=True),
            sa.Column("method", sa.String(50), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("status", sa.String(50), nullable=False, server_default="ok"),
            sa.Column("robots_ok", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("captcha_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("probe_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tos_note", sa.Text(), nullable=True),
            sa.Column("crawl_delay_seconds", sa.Float(), nullable=False, server_default="3.0"),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_gov_sources_code", "gov_sources", ["code"])
        op.create_index("ix_gov_sources_domain", "gov_sources", ["domain"])
        op.create_index("ix_gov_sources_state_code", "gov_sources", ["state_code"])

    # 2. gov_updates
    if not insp.has_table("gov_updates"):
        op.create_table(
            "gov_updates",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("gov_sources.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(1000), nullable=False),
            sa.Column("doc_type", sa.String(50), nullable=False, server_default="other"),
            sa.Column("legal_status", sa.String(50), nullable=False, server_default="unknown"),
            sa.Column("doc_number", sa.String(255), nullable=True),
            sa.Column("issue_date", sa.Date(), nullable=True),
            sa.Column("effective_date", sa.Date(), nullable=True),
            sa.Column("category", sa.String(50), nullable=False),
            sa.Column("topics", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("law_version", sa.String(100), nullable=True, server_default="unknown"),
            sa.Column("url", sa.String(1000), nullable=False),
            sa.Column("pdf_url", sa.String(1000), nullable=True),
            sa.Column("content_text", sa.Text(), nullable=True),
            sa.Column("text_status", sa.String(50), nullable=False, server_default="no_text"),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(50), nullable=False, server_default="active"),
            sa.Column("status_confidence", sa.Float(), nullable=True),
            sa.Column("supersedes_refs", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("backfilled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("ai_summary", sa.JSON(), nullable=True),
            sa.Column("ai_model", sa.String(100), nullable=True),
            sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ai_status", sa.String(50), nullable=True),
        )
        op.create_index("ix_gov_updates_source_id", "gov_updates", ["source_id"])
        op.create_index("ix_gov_updates_doc_number", "gov_updates", ["doc_number"])
        op.create_index("ix_gov_updates_issue_date", "gov_updates", ["issue_date"])
        op.create_index("ix_gov_updates_category", "gov_updates", ["category"])
        op.create_index("ix_gov_updates_content_hash", "gov_updates", ["content_hash"])
        op.create_index("ix_gov_updates_cat_date", "gov_updates", ["category", "issue_date"])
        op.create_index("ix_gov_updates_source_doc_date", "gov_updates", ["source_id", "doc_number", "issue_date"])
        op.create_index("ix_gov_updates_url", "gov_updates", ["url"])

    # 3. gov_fetch_runs
    if not insp.has_table("gov_fetch_runs"):
        op.create_table(
            "gov_fetch_runs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("gov_sources.id", ondelete="CASCADE"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(50), nullable=False, server_default="running"),
            sa.Column("items_new", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("items_updated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("items_skipped", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
        )
        op.create_index("ix_gov_fetch_runs_source_id", "gov_fetch_runs", ["source_id"])

    # 4. gov_saved_updates
    if not insp.has_table("gov_saved_updates"):
        op.create_table(
            "gov_saved_updates",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("update_id", UUID(as_uuid=True), sa.ForeignKey("gov_updates.id", ondelete="CASCADE"), nullable=False),
            sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "update_id", name="uq_gov_saved_user_update"),
        )
        op.create_index("ix_gov_saved_updates_user_id", "gov_saved_updates", ["user_id"])
        op.create_index("ix_gov_saved_updates_update_id", "gov_saved_updates", ["update_id"])


def downgrade() -> None:
    op.drop_table("gov_saved_updates")
    op.drop_table("gov_fetch_runs")
    op.drop_table("gov_updates")
    op.drop_table("gov_sources")
