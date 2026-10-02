"""
GovernmentRule Model — Scraped government notifications and circulars.
Standalone table (no FK — rules are global, not per-client).
"""

import uuid
from sqlalchemy import Column, String, DateTime, Date, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.session import Base


class GovernmentRule(Base):
    __tablename__ = "government_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    category = Column(String(100), nullable=False, index=True)   # GST | Income Tax | TDS | Budget | SEBI | RBI
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    source = Column(String(255), nullable=True)                  # CBDT | GSTN | RBI | MCA
    source_url = Column(String(1000), nullable=True)
    published_date = Column(Date, nullable=True)
    scraped_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Indexes ───────────────────────────────────
    __table_args__ = (
        Index("ix_gov_rules_category_date", "category", "published_date"),
    )

    def __repr__(self) -> str:
        return f"<GovernmentRule id={self.id} category={self.category} title={self.title[:40]}>"
