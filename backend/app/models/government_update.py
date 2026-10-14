"""
Government Updates Models:
- GovSource: Tracked official public source registry
- GovUpdate: Normalized circular, notification, order, advisory, standard
- GovFetchRun: Operational audit log per scrape/fetch run
- GovSavedUpdate: Per-user persistent bookmark of updates
"""

import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Date,
    Text,
    Boolean,
    ForeignKey,
    Index,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class GovSource(Base):
    __tablename__ = "gov_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    base_url = Column(String(500), nullable=False)
    domain = Column(String(255), nullable=False, index=True)
    tier = Column(Integer, nullable=False, default=1)  # 1, 2, or 3
    scope = Column(String(50), nullable=False, default="national")  # national | state
    state_code = Column(String(10), nullable=True, index=True)  # GST state code e.g. "27"
    method = Column(String(50), nullable=False)  # rss | html_listing | pdf_listing
    enabled = Column(Boolean, nullable=False, default=True)
    status = Column(String(50), nullable=False, default="ok")  # ok | degraded | blocked_requires_verification | disabled
    robots_ok = Column(Boolean, nullable=False, default=True)
    captcha_detected = Column(Boolean, nullable=False, default=False)
    probe_date = Column(DateTime(timezone=True), nullable=True)
    tos_note = Column(Text, nullable=True)
    crawl_delay_seconds = Column(Float, nullable=False, default=3.0)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    failure_stage = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    last_probe_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    updates = relationship("GovUpdate", back_populates="source", cascade="all, delete-orphan")
    fetch_runs = relationship("GovFetchRun", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<GovSource id={self.id} code={self.code} status={self.status} enabled={self.enabled}>"


class GovUpdate(Base):
    __tablename__ = "gov_updates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    source_id = Column(UUID(as_uuid=True), ForeignKey("gov_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(1000), nullable=False)
    doc_type = Column(String(50), nullable=False, default="other")  # circular|notification|order|instruction|advisory|press_release|gazette|standard|rules|act|faq|administrative|newsletter|recruitment_or_tender|event_or_exam|other
    legal_status = Column(String(50), nullable=False, default="unknown")  # operative_instrument|press_release_not_law|advisory|explanatory|newsletter|administrative_not_law|draft_or_proposal|unknown
    doc_number = Column(String(255), nullable=True, index=True)
    doc_number_source = Column(String(50), nullable=True)  # listing|feed|detail_page|document_text
    issue_date = Column(Date, nullable=True, index=True)
    issue_date_source = Column(String(50), nullable=True)  # listing|feed|detail_page|document_text|none
    date_precision = Column(String(20), nullable=False, default="day")  # day|month|year|none
    effective_date = Column(Date, nullable=True)
    category = Column(String(50), nullable=False, index=True)  # GST|INCOME_TAX|TDS|BUDGET|ACCOUNTING|COMPANIES|BANKING|OTHER
    topics = Column(JSON, nullable=False, default=list)  # Fixed taxonomy
    law_version = Column(String(100), nullable=True, default="unknown")  # e.g. "CGST Act 2017", "Income-tax Act, 2025"
    url = Column(String(1000), nullable=False)
    link_quality = Column(String(50), nullable=False, default="direct_document")  # direct_document|listing_only|homepage
    ministry = Column(String(255), nullable=True)
    pdf_url = Column(String(1000), nullable=True)
    content_text = Column(Text, nullable=True)
    text_status = Column(String(50), nullable=False, default="no_text")  # ok|no_text|unreadable|too_large
    content_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="active")  # active|amended|superseded|withdrawn|unknown
    status_confidence = Column(Float, nullable=True)
    supersedes_refs = Column(JSON, nullable=False, default=list)
    hidden = Column(Boolean, nullable=False, default=False)
    hidden_reason = Column(String(255), nullable=True)
    is_manual = Column(Boolean, nullable=False, default=False)
    manual_added_by = Column(UUID(as_uuid=True), nullable=True)
    manual_added_at = Column(DateTime(timezone=True), nullable=True)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    backfilled = Column(Boolean, nullable=False, default=False)
    ai_summary = Column(JSON, nullable=True)  # {summary, who_is_affected, key_dates[], action_items[]}
    ai_model = Column(String(100), nullable=True)
    ai_generated_at = Column(DateTime(timezone=True), nullable=True)
    ai_status = Column(String(50), nullable=True)  # none|pending|generated|rejected_ungrounded|failed

    source = relationship("GovSource", back_populates="updates")
    saved_by = relationship("GovSavedUpdate", back_populates="update", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_gov_updates_cat_date", "category", "issue_date"),
        Index("ix_gov_updates_source_doc_date", "source_id", "doc_number", "issue_date"),
        Index("ix_gov_updates_url", "url"),
    )

    def __repr__(self) -> str:
        return f"<GovUpdate id={self.id} category={self.category} title={self.title[:40]}>"


class GovFetchRun(Base):
    __tablename__ = "gov_fetch_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    source_id = Column(UUID(as_uuid=True), ForeignKey("gov_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), nullable=False, default="running")  # running|success|failed|partial|blocked
    items_new = Column(Integer, nullable=False, default=0)
    items_updated = Column(Integer, nullable=False, default=0)
    items_skipped = Column(Integer, nullable=False, default=0)
    http_status = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    source = relationship("GovSource", back_populates="fetch_runs")

    def __repr__(self) -> str:
        return f"<GovFetchRun id={self.id} source={self.source_id} status={self.status} new={self.items_new}>"


class GovSavedUpdate(Base):
    __tablename__ = "gov_saved_updates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    update_id = Column(UUID(as_uuid=True), ForeignKey("gov_updates.id", ondelete="CASCADE"), nullable=False, index=True)
    saved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    update = relationship("GovUpdate", back_populates="saved_by")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "update_id", name="uq_gov_saved_user_update"),
    )

    def __repr__(self) -> str:
        return f"<GovSavedUpdate user={self.user_id} update={self.update_id}>"
