"""
Tests for the email service (app/email.py) and Gmail OTP integration.

Covers:
  - Dev fallback (no MAIL config → logs instead of sending)
  - OTP email dispatch (mocked SMTP)
  - Password reset email dispatch (mocked SMTP)
  - SMTP failure handling (returns False, doesn't crash)
  - Registration now requires email
  - OTP is emailed on registration
  - Forgot-password triggers reset email
"""

import smtplib
from unittest.mock import MagicMock, call, patch

import bcrypt

from app import db
from app.models import Store, User


class FakeRedis:
    def __init__(self):
        self.data = {}

    def setex(self, key, ttl, value):
        self.data[key] = str(value)

    def get(self, key):
        return self.data.get(key)

    def delete(self, key):
        self.data.pop(key, None)

    def ping(self):
        return True


# ─── Unit tests for app.email ────────────────────────────────────────────────


def test_send_otp_email_dev_fallback(app):
    """When email is disabled, OTP email falls back to logger (no SMTP)."""
    # Ensure fallback by disabling email or clearing credentials
    app.config["EMAIL_ENABLED"] = False
    with app.app_context():
        from app.email import send_otp_email

        result = send_otp_email("user@example.com", "123456")
        assert result is True  # dev/disabled fallback always succeeds


def test_send_password_reset_email_dev_fallback(app):
    """When email is disabled, password reset email falls back to logger."""
    app.config["EMAIL_ENABLED"] = False
    with app.app_context():
        from app.email import send_password_reset_email

        result = send_password_reset_email("user@example.com", "some-reset-token")
        assert result is True


@patch("app.email.smtplib.SMTP")
def test_send_otp_email_via_smtp(mock_smtp_class, app):
    """With SMTP config set, OTP email goes through SMTP."""
    app.config["EMAIL_ENABLED"] = True
    app.config["SMTP_USER"] = "test@gmail.com"
    app.config["SMTP_PASSWORD"] = "test-app-password"

    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

    with app.app_context():
        from app.email import send_otp_email

        result = send_otp_email("user@example.com", "654321")
        assert result is True

    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("test@gmail.com", "test-app-password")
    mock_server.sendmail.assert_called_once()

    # Clean up
    app.config["SMTP_USER"] = ""
    app.config["SMTP_PASSWORD"] = ""


@patch("app.email.smtplib.SMTP")
def test_send_otp_email_normalizes_gmail_app_password_spacing(mock_smtp_class, app):
    """Gmail app passwords copied with spaces should still authenticate."""
    app.config["EMAIL_ENABLED"] = True
    app.config["SMTP_USER"] = "test@gmail.com"
    app.config["SMTP_PASSWORD"] = " abcd efgh ijkl mnop "

    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

    with app.app_context():
        from app.email import send_otp_email

        result = send_otp_email("user@example.com", "333333")
        assert result is True

    mock_server.login.assert_called_once_with("test@gmail.com", "abcdefghijklmnop")
    app.config["SMTP_USER"] = ""
    app.config["SMTP_PASSWORD"] = ""


@patch("app.email.smtplib.SMTP")
def test_send_otp_email_accepts_mail_aliases(mock_smtp_class, app):
    """Legacy MAIL_USERNAME / MAIL_PASSWORD aliases should also work."""
    app.config["EMAIL_ENABLED"] = True
    app.config["SMTP_USER"] = ""
    app.config["SMTP_PASSWORD"] = ""
    app.config["MAIL_USERNAME"] = "alias@gmail.com"
    app.config["MAIL_PASSWORD"] = "alias-password"

    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)

    with app.app_context():
        from app.email import send_otp_email

        result = send_otp_email("user@example.com", "987654")
        assert result is True

    mock_server.login.assert_called_once_with("alias@gmail.com", "alias-password")
    mock_server.sendmail.assert_called_once()

    app.config["MAIL_USERNAME"] = ""
    app.config["MAIL_PASSWORD"] = ""


@patch("app.email.smtplib.SMTP")
def test_send_otp_email_falls_back_to_mail_aliases_on_auth_failure(mock_smtp_class, app):
    """Fallback to MAIL aliases when the primary SMTP pair is stale."""
    app.config["EMAIL_ENABLED"] = True
    app.config["SMTP_USER"] = "stale@gmail.com"
    app.config["SMTP_PASSWORD"] = "stale-password"
    app.config["MAIL_USERNAME"] = "alias@gmail.com"
    app.config["MAIL_PASSWORD"] = "alias-password"

    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_server.login.side_effect = [
        smtplib.SMTPAuthenticationError(534, b"bad credentials"),
        None,
    ]

    with app.app_context():
        from app.email import send_otp_email

        result = send_otp_email("user@example.com", "246810")
        assert result is True

    assert mock_server.login.call_args_list == [
        call("stale@gmail.com", "stale-password"),
        call("alias@gmail.com", "alias-password"),
    ]
    mock_server.sendmail.assert_called_once()

    app.config["SMTP_USER"] = ""
    app.config["SMTP_PASSWORD"] = ""
    app.config["MAIL_USERNAME"] = ""
    app.config["MAIL_PASSWORD"] = ""


@patch("app.email.smtplib.SMTP")
def test_send_password_reset_email_via_smtp(mock_smtp_class, app):
    """With SMTP config set, password reset email goes through SMTP."""
    app.config["EMAIL_ENABLED"] = True
    app.config["SMTP_USER"] = "test@gmail.com"
    app.config["SMTP_PASSWORD"] = "test-app-password"

    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

    with app.app_context():
        from app.email import send_password_reset_email

        result = send_password_reset_email("user@example.com", "abc-reset-token")
        assert result is True

    mock_server.sendmail.assert_called_once()

    app.config["SMTP_USER"] = ""
    app.config["SMTP_PASSWORD"] = ""


@patch("app.email.smtplib.SMTP")
def test_smtp_failure_returns_false(mock_smtp_class, app):
    """If SMTP raises, send returns False (doesn't crash the request)."""
    app.config["EMAIL_ENABLED"] = True
    app.config["SMTP_USER"] = "test@gmail.com"
    app.config["SMTP_PASSWORD"] = "test-app-password"

    mock_smtp_class.side_effect = Exception("Connection refused")

    with app.app_context():
        from app.email import send_otp_email

        result = send_otp_email("user@example.com", "111111")
        assert result is False

    app.config["SMTP_USER"] = ""
    app.config["SMTP_PASSWORD"] = ""


# ─── Integration tests: registration + OTP email ────────────────────────────


def test_registration_requires_email(client, app, monkeypatch):
    """Registration without email returns 400 validation error."""
    fake = FakeRedis()
    monkeypatch.setattr("app.auth.utils.get_redis_client", lambda: fake)
    monkeypatch.setattr("app.auth.routes.get_redis_client", lambda: fake)

    resp = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "No Email User",
            "mobile_number": "9333333333",
            "password": "secret123",
        },
    )
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["success"] is False
    # Check for 'email' error in the error object (which might be a dict)
    errors = str(data.get("error", "")).lower()
    assert "email" in errors


def test_registration_sends_otp_email(client, app, monkeypatch):
    """After registration with email, generate_otp is called with email param."""
    fake = FakeRedis()
    monkeypatch.setattr("app.auth.utils.get_redis_client", lambda: fake)
    monkeypatch.setattr("app.auth.routes.get_redis_client", lambda: fake)

    # Patch send_otp_email to capture calls
    captured = {}

    def mock_send_otp(to_email, otp_code):
        captured["to_email"] = to_email
        captured["otp_code"] = otp_code
        return True

    monkeypatch.setattr("app.email.send_otp_email", mock_send_otp)

    resp = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Email OTP User",
            "mobile_number": "9444444444",
            "password": "secret123",
            "store_name": "Email Store",
            "email": "emailotp@example.com",
        },
    )
    assert resp.status_code == 201

    # Verify OTP was stored in Redis
    otp = fake.get("otp:emailotp@example.com")
    assert otp is not None

    # Verify email was dispatched
    assert captured["to_email"] == "emailotp@example.com"
    assert captured["otp_code"] == otp


def test_login_sends_otp_email(client, app, monkeypatch):
    """Login by email should trigger an OTP email."""
    fake = FakeRedis()
    monkeypatch.setattr("app.auth.utils.get_redis_client", lambda: fake)
    monkeypatch.setattr("app.auth.routes.get_redis_client", lambda: fake)

    captured = {}

    def mock_send_otp(to_email, otp_code):
        captured["to_email"] = to_email
        captured["otp_code"] = otp_code
        return True

    monkeypatch.setattr("app.email.send_otp_email", mock_send_otp)

    with app.app_context():
        store = Store(store_name="Login Store", store_type="grocery")
        db.session.add(store)
        db.session.flush()

        user = User(
            mobile_number="9555555556",
            full_name="Login User",
            email="login@example.com",
            role="owner",
            store_id=store.store_id,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": "login@example.com"})
    assert resp.status_code == 200

    otp = fake.get("otp:login@example.com")
    assert otp is not None
    assert captured["to_email"] == "login@example.com"
    assert captured["otp_code"] == otp


def test_forgot_password_sends_reset_email(client, app, monkeypatch):
    """Forgot password dispatches a reset email to the user."""
    fake = FakeRedis()
    monkeypatch.setattr("app.auth.utils.get_redis_client", lambda: fake)
    monkeypatch.setattr("app.auth.routes.get_redis_client", lambda: fake)

    # Create a user first
    with app.app_context():
        store = Store(store_name="Reset Store", store_type="grocery")
        db.session.add(store)
        db.session.flush()

        pw_hash = bcrypt.hashpw(b"secret123", bcrypt.gensalt(12)).decode("utf-8")
        user = User(
            mobile_number="9555555555",
            password_hash=pw_hash,
            full_name="Reset User",
            email="reset@example.com",
            role="owner",
            store_id=store.store_id,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()

    # Capture reset email
    captured = {}

    def mock_send_reset(to_email, reset_token):
        captured["to_email"] = to_email
        captured["token"] = reset_token
        return True

    monkeypatch.setattr("app.email.send_password_reset_email", mock_send_reset)

    resp = client.post(
        "/api/v1/auth/forgot-password",
        json={
            "mobile_number": "9555555555",
        },
    )
    assert resp.status_code == 200

    # Verify reset email was dispatched to user's email
    assert captured["to_email"] == "reset@example.com"
    assert captured["token"] is not None
