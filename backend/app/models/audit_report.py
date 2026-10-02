"""
Audit Report Model — AI-generated and manual audit findings per client.
"""

import uuid
from sqlalchemy import Column, String, DateTime, Numeric, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class AuditReport(Base):
    __tablename__ = "audit_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_type = Column(String(50), nullable=False)        # statutory | internal | tax | gst | forensic
    audit_status = Column(String(30), nullable=False, default="pending")  # pending | in_progress | completed | flagged
    risk_score = Column(Numeric(5, 2), nullable=True)      # 0.00 – 100.00
    findings = Column(Text, nullable=True)
    recommendations = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationship ──────────────────────────────
    client = relationship("Client", back_populates="audit_reports")

    # ── Indexes ───────────────────────────────────
    __table_args__ = (
        Index("ix_audit_client_status", "client_id", "audit_status"),
        Index("ix_audit_type", "audit_type"),
    )

    def __repr__(self) -> str:
        return f"<AuditReport id={self.id} client={self.client_id} type={self.audit_type} status={self.audit_status}>"
