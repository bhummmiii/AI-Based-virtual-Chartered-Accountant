"""
Settings Pydantic Schemas — Models for updating profile, security, notifications, preferences, and API keys.
"""

from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime
import uuid


class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    membership_no: Optional[str] = Field(None, max_length=100)
    profile_image: Optional[str] = None  # Base64 data URL or image URL


class SecurityUpdateRequest(BaseModel):
    two_factor_enabled: Optional[bool] = None
    login_alerts: Optional[bool] = None
    session_timeout_minutes: Optional[int] = Field(None, ge=5, le=480)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class NotificationsUpdateRequest(BaseModel):
    compliance_deadlines: Optional[bool] = None
    audit_alerts: Optional[bool] = None
    client_activity: Optional[bool] = None
    product_updates: Optional[bool] = None


class PreferencesUpdateRequest(BaseModel):
    language: Optional[str] = Field(None, max_length=20)
    currency: Optional[str] = Field(None, max_length=20)
    theme: Optional[str] = Field(None, max_length=20)


class ApiKeyResponse(BaseModel):
    api_key: str
    masked_key: str
    created_at: Optional[datetime] = None


class FullSettingsResponse(BaseModel):
    # Profile information
    id: uuid.UUID
    first_name: str
    last_name: str
    full_name: str
    email: str
    phone: Optional[str] = None
    role: str
    membership_no: str
    profile_image: Optional[str] = None

    # Security settings
    two_factor_enabled: bool
    login_alerts: bool
    session_timeout_minutes: int

    # Notification preferences
    compliance_deadlines: bool
    audit_alerts: bool
    client_activity: bool
    product_updates: bool

    # Preferences
    language: str
    currency: str
    theme: str

    # API key
    api_key: str
    masked_key: str

    model_config = ConfigDict(from_attributes=True)
