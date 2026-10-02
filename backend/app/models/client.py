"""
Client Model — Full client business profile.
UUID primary key. Indexed on client_code, gst_number, pan_number.
"""

import uuid
from sqlalchemy import Column, String, DateTime, Text, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    client_code = Column(String(50), unique=True, nullable=False, index=True)
    company_name = Column(String(255), nullable=False, index=True)
    client_type = Column(String(50), nullable=False, default="company")             # company | individual | llp | partnership
    contact_person = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)
    gst_number = Column(String(20), nullable=True, index=True)
    pan_number = Column(String(15), nullable=True, index=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True, default="India")
    risk_level = Column(String(20), nullable=False, default="low")
    status = Column(String(20), nullable=False, default="active")
    # ── New fields ────────────────────────────────
    billing_cycle = Column(String(20), nullable=True, default="monthly")            # monthly | quarterly  (frontend: Client Type)
    return_frequency = Column(String(20), nullable=True, default="Quarterly", server_default="Quarterly")  # Monthly | Quarterly
    contact_number = Column(String(20), nullable=True)                              # mobile number
    email_address = Column(String(255), nullable=True)                              # client email (separate from CA email)
    location = Column(String(255), nullable=True)                                   # city, state
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationships ─────────────────────────────
    user = relationship("User", back_populates="clients")
    accounting_records = relationship("AccountingRecord", back_populates="client", cascade="all, delete-orphan")
    gst_records = relationship("GSTRecord", back_populates="client", cascade="all, delete-orphan")
    tax_records = relationship("TaxRecord", back_populates="client", cascade="all, delete-orphan")
    audit_reports = relationship("AuditReport", back_populates="client", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="client", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="client", cascade="all, delete-orphan")
    uploaded_documents = relationship("UploadedDocument", back_populates="client", cascade="all, delete-orphan")
    chart_of_accounts = relationship("ChartOfAccounts", back_populates="client", cascade="all, delete-orphan")
    journal_entries = relationship("JournalEntry", back_populates="client", cascade="all, delete-orphan")


    # ── Composite indexes ──────────────────────────
    __table_args__ = (
        Index("ix_clients_status_risk", "status", "risk_level"),
        Index("ix_clients_gst_pan", "gst_number", "pan_number"),
    )

    def __repr__(self) -> str:
        return f"<Client id={self.id} code={self.client_code} name={self.company_name}>"
