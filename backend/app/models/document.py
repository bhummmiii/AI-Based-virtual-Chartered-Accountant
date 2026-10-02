"""
Document Model — Uploaded files (PDF, images, spreadsheets) per client.
"""

import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(100), nullable=False)        # pdf | image | excel | csv | doc
    storage_path = Column(String(500), nullable=False)     # path or S3 URL
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationship ──────────────────────────────
    client = relationship("Client", back_populates="documents")

    # ── Indexes ───────────────────────────────────
    __table_args__ = (
        Index("ix_document_client_type", "client_id", "file_type"),
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} name={self.file_name} type={self.file_type}>"
