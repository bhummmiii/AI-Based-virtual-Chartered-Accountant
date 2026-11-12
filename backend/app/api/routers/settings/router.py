"""
Settings Router — Profile, security, notifications, preferences, and API keys endpoints.
"""

import secrets
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.core.security import verify_password, hash_password
from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.settings import (
    FullSettingsResponse,
    ProfileUpdateRequest,
    SecurityUpdateRequest,
    PasswordChangeRequest,
    NotificationsUpdateRequest,
    PreferencesUpdateRequest,
    ApiKeyResponse,
)
from app.schemas.common import APIResponse

router = APIRouter()


def mask_key(key: str) -> str:
    if not key:
        return "fl_live_••••••••••••••••"
    if len(key) <= 12:
        return "••••••••"
    prefix = key[:8]
    suffix = key[-4:]
    return f"{prefix}••••••••••••{suffix}"


def get_or_create_settings(db: Session, user: User) -> UserSettings:
    settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if not settings:
        initial_key = f"fl_live_{secrets.token_hex(16)}"
        settings = UserSettings(
            user_id=user.id,
            membership_no="ICAI-123456",
            two_factor_enabled=True,
            login_alerts=True,
            session_timeout_minutes=30,
            compliance_deadlines=True,
            audit_alerts=True,
            client_activity=False,
            product_updates=True,
            language="en",
            currency="inr",
            theme="dark",
            api_key=initial_key,
            api_key_created_at=datetime.now(timezone.utc),
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def build_full_response(user: User, settings: UserSettings) -> FullSettingsResponse:
    parts = (user.full_name or "").strip().split(maxsplit=1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""

    return FullSettingsResponse(
        id=user.id,
        first_name=first_name,
        last_name=last_name,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        membership_no=settings.membership_no or "ICAI-123456",
        profile_image=user.profile_image,
        two_factor_enabled=settings.two_factor_enabled,
        login_alerts=settings.login_alerts,
        session_timeout_minutes=settings.session_timeout_minutes,
        compliance_deadlines=settings.compliance_deadlines,
        audit_alerts=settings.audit_alerts,
        client_activity=settings.client_activity,
        product_updates=settings.product_updates,
        language=settings.language,
        currency=settings.currency,
        theme=settings.theme,
        api_key=settings.api_key or "",
        masked_key=mask_key(settings.api_key or ""),
    )


@router.get("", response_model=APIResponse[FullSettingsResponse], summary="Get full settings and profile")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_settings(db, current_user)
    data = build_full_response(current_user, settings)
    return APIResponse(data=data, message="Settings retrieved successfully")


@router.put("/profile", response_model=APIResponse[FullSettingsResponse], summary="Update personal profile information")
def update_profile(
    payload: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_settings(db, current_user)

    # Name update
    if payload.first_name is not None or payload.last_name is not None:
        parts = (current_user.full_name or "").strip().split(maxsplit=1)
        cur_first = parts[0] if parts else ""
        cur_last = parts[1] if len(parts) > 1 else ""
        
        new_first = payload.first_name if payload.first_name is not None else cur_first
        new_last = payload.last_name if payload.last_name is not None else cur_last
        current_user.full_name = f"{new_first.strip()} {new_last.strip()}".strip()

    # Email update
    if payload.email is not None and payload.email.lower() != current_user.email.lower():
        existing = db.query(User).filter(User.email == payload.email.lower(), User.id != current_user.id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use by another account",
            )
        current_user.email = payload.email.lower()

    # Phone update
    if payload.phone is not None:
        current_user.phone = payload.phone.strip()

    # Profile image update (supports updating image or clearing with null/empty)
    if "profile_image" in payload.model_fields_set:
        current_user.profile_image = payload.profile_image if payload.profile_image else None

    # Membership number
    if payload.membership_no is not None:
        settings.membership_no = payload.membership_no.strip()

    db.commit()
    db.refresh(current_user)
    db.refresh(settings)

    data = build_full_response(current_user, settings)
    return APIResponse(data=data, message="Profile updated successfully")


@router.put("/security", response_model=APIResponse[FullSettingsResponse], summary="Update security settings")
def update_security(
    payload: SecurityUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_settings(db, current_user)

    if payload.two_factor_enabled is not None:
        settings.two_factor_enabled = payload.two_factor_enabled
    if payload.login_alerts is not None:
        settings.login_alerts = payload.login_alerts
    if payload.session_timeout_minutes is not None:
        settings.session_timeout_minutes = payload.session_timeout_minutes

    db.commit()
    db.refresh(settings)

    data = build_full_response(current_user, settings)
    return APIResponse(data=data, message="Security settings updated successfully")


@router.post("/change-password", response_model=APIResponse[Dict[str, Any]], summary="Change account password")
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password entered is incorrect",
        )

    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters long",
        )

    current_user.password_hash = hash_password(payload.new_password)
    db.commit()

    return APIResponse(data={"success": True}, message="Password changed successfully")


@router.put("/notifications", response_model=APIResponse[FullSettingsResponse], summary="Update notification preferences")
def update_notifications(
    payload: NotificationsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_settings(db, current_user)

    if payload.compliance_deadlines is not None:
        settings.compliance_deadlines = payload.compliance_deadlines
    if payload.audit_alerts is not None:
        settings.audit_alerts = payload.audit_alerts
    if payload.client_activity is not None:
        settings.client_activity = payload.client_activity
    if payload.product_updates is not None:
        settings.product_updates = payload.product_updates

    db.commit()
    db.refresh(settings)

    data = build_full_response(current_user, settings)
    return APIResponse(data=data, message="Notification preferences updated successfully")


@router.put("/preferences", response_model=APIResponse[FullSettingsResponse], summary="Update user interface preferences")
def update_preferences(
    payload: PreferencesUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_settings(db, current_user)

    if payload.language is not None:
        settings.language = payload.language
    if payload.currency is not None:
        settings.currency = payload.currency
    if payload.theme is not None:
        settings.theme = payload.theme

    db.commit()
    db.refresh(settings)

    data = build_full_response(current_user, settings)
    return APIResponse(data=data, message="Preferences updated successfully")


@router.post("/api-key/generate", response_model=APIResponse[ApiKeyResponse], summary="Generate a new API key")
def generate_api_key(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_settings(db, current_user)

    new_key = f"fl_live_{secrets.token_hex(16)}"
    now = datetime.now(timezone.utc)
    settings.api_key = new_key
    settings.api_key_created_at = now
    db.commit()
    db.refresh(settings)

    return APIResponse(
        data=ApiKeyResponse(
            api_key=new_key,
            masked_key=mask_key(new_key),
            created_at=now,
        ),
        message="New API key generated successfully. Previous key has been revoked.",
    )
