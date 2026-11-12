"""
Tests for Settings Module — Profile, security, notifications, preferences, and API key management.
"""

import os
import pytest
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi.testclient import TestClient
from app.main import app
from app.database.session import SessionLocal
from app.models.user import User
from app.models.user_settings import UserSettings
from app.core.security import create_access_token, hash_password, verify_password


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def auth_headers(db_session):
    # Ensure test user exists
    user = db_session.query(User).filter(User.email == "test_settings_ca@example.com").first()
    if not user:
        user = User(
            full_name="Bhumi Jha",
            email="test_settings_ca@example.com",
            password_hash=hash_password("password123"),
            role="ca",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    else:
        user.full_name = "Bhumi Jha"
        user.password_hash = hash_password("password123")
        if user.settings:
            user.settings.membership_no = "ICAI-123456"
            user.settings.two_factor_enabled = True
            user.settings.login_alerts = True
            user.settings.session_timeout_minutes = 30
            user.settings.compliance_deadlines = True
            user.settings.audit_alerts = True
            user.settings.client_activity = False
            user.settings.product_updates = True
            user.settings.language = "en"
            user.settings.currency = "inr"
            user.settings.theme = "dark"
        db_session.commit()

    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
    return {"Authorization": f"Bearer {token}"}, user


def test_get_settings_auto_initializes(auth_headers):
    headers, user = auth_headers
    client = TestClient(app)

    response = client.get("/api/v1/settings", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["email"] == user.email
    assert data["first_name"] == "Bhumi"
    assert data["last_name"] == "Jha"
    assert data["membership_no"] == "ICAI-123456"
    assert data["two_factor_enabled"] is True
    assert data["session_timeout_minutes"] == 30
    assert data["language"] == "en"
    assert data["currency"] == "inr"
    assert data["api_key"].startswith("fl_live_")
    assert "••••" in data["masked_key"]


def test_update_profile(auth_headers, db_session):
    headers, user = auth_headers
    client = TestClient(app)

    update_payload = {
        "first_name": "Bhumi",
        "last_name": "Sharma",
        "membership_no": "ICAI-999888",
        "phone": "+91 9876543210",
    }
    response = client.put("/api/v1/settings/profile", json=update_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["first_name"] == "Bhumi"
    assert data["last_name"] == "Sharma"
    assert data["full_name"] == "Bhumi Sharma"
    assert data["membership_no"] == "ICAI-999888"
    assert data["phone"] == "+91 9876543210"

    # Verify persisted in DB
    db_session.expire_all()
    refreshed_user = db_session.query(User).filter(User.id == user.id).first()
    assert refreshed_user.full_name == "Bhumi Sharma"


def test_update_security_and_notifications(auth_headers):
    headers, _ = auth_headers
    client = TestClient(app)

    # Security update
    sec_payload = {
        "two_factor_enabled": False,
        "login_alerts": True,
        "session_timeout_minutes": 60,
    }
    sec_resp = client.put("/api/v1/settings/security", json=sec_payload, headers=headers)
    assert sec_resp.status_code == 200
    assert sec_resp.json()["data"]["two_factor_enabled"] is False
    assert sec_resp.json()["data"]["session_timeout_minutes"] == 60

    # Notifications update
    notif_payload = {
        "compliance_deadlines": True,
        "audit_alerts": False,
        "client_activity": True,
        "product_updates": True,
    }
    notif_resp = client.put("/api/v1/settings/notifications", json=notif_payload, headers=headers)
    assert notif_resp.status_code == 200
    assert notif_resp.json()["data"]["audit_alerts"] is False
    assert notif_resp.json()["data"]["client_activity"] is True


def test_change_password(auth_headers, db_session):
    headers, user = auth_headers
    client = TestClient(app)

    user.password_hash = hash_password("password123")
    db_session.commit()

    # Wrong current password fails
    fail_resp = client.post(
        "/api/v1/settings/change-password",
        json={"current_password": "wrong_password", "new_password": "new_secure_pwd_123"},
        headers=headers,
    )
    assert fail_resp.status_code == 400
    assert "incorrect" in fail_resp.json()["detail"].lower()

    # Correct current password succeeds
    ok_resp = client.post(
        "/api/v1/settings/change-password",
        json={"current_password": "password123", "new_password": "new_secure_pwd_123"},
        headers=headers,
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["data"]["success"] is True

    # Verify password hash updated
    refreshed_user = db_session.query(User).filter(User.id == user.id).first()
    assert verify_password("new_secure_pwd_123", refreshed_user.password_hash)


def test_generate_api_key(auth_headers):
    headers, _ = auth_headers
    client = TestClient(app)

    # Fetch initial settings
    initial = client.get("/api/v1/settings", headers=headers).json()["data"]
    old_key = initial["api_key"]

    # Generate new key
    gen_resp = client.post("/api/v1/settings/api-key/generate", headers=headers)
    assert gen_resp.status_code == 200
    new_data = gen_resp.json()["data"]

    assert new_data["api_key"].startswith("fl_live_")
    assert new_data["api_key"] != old_key
    assert "••••" in new_data["masked_key"]
