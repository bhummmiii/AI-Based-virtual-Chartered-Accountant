"""
User Settings Model — CA personal preferences, security settings, and API keys.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, backref

from app.database.session import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    # Profile extra fields
    membership_no = Column(String(100), nullable=True, default="ICAI-123456")
    
    # Security preferences
    two_factor_enabled = Column(Boolean, nullable=False, default=True)
    login_alerts = Column(Boolean, nullable=False, default=True)
    session_timeout_minutes = Column(Integer, nullable=False, default=30)
    
    # Notification preferences
    compliance_deadlines = Column(Boolean, nullable=False, default=True)
    audit_alerts = Column(Boolean, nullable=False, default=True)
    client_activity = Column(Boolean, nullable=False, default=False)
    product_updates = Column(Boolean, nullable=False, default=True)
    
    # System preferences
    language = Column(String(20), nullable=False, default="en")
    currency = Column(String(20), nullable=False, default="inr")
    theme = Column(String(20), nullable=False, default="dark")
    
    # API key
    api_key = Column(String(255), nullable=True)
    api_key_created_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", backref=backref("settings", uselist=False, cascade="all, delete-orphan"))

    def __repr__(self) -> str:
        return f"<UserSettings user_id={self.user_id} membership_no={self.membership_no}>"
