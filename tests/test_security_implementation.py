"""
Comprehensive tests for the Security, Privacy & Compliance infrastructure.
Covers: RBAC models, AuditLog, field-level encryption, MFA (TOTP), and User MFA fields.
"""

import pyotp
import pytest

from app import db
from app.models import AuditLog, RBACPermission, User
from app.utils.audit import audit_log
from app.utils.security import (
    decrypt_pii,
    encrypt_pii,
    generate_mfa_secret,
    sanitize_html,
    verify_mfa_code,
)


# ---------------------------------------------------------------------------
# Encryption / Decryption
# ---------------------------------------------------------------------------
class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self, app):
        with app.app_context():
            plaintext = "John Doe — john@example.com"
            encrypted = encrypt_pii(plaintext)
            assert encrypted != plaintext
            assert decrypt_pii(encrypted) == plaintext

    def test_encrypt_empty_returns_empty(self, app):
        with app.app_context():
            assert encrypt_pii("") == ""
            assert encrypt_pii(None) is None

    def test_decrypt_bad_data_returns_input(self, app):
        with app.app_context():
            # If data can't be decrypted, original string is returned
            assert decrypt_pii("not-valid-base64!!") == "not-valid-base64!!"


# ---------------------------------------------------------------------------
# MFA (TOTP)
# ---------------------------------------------------------------------------
class TestMFA:
    def test_generate_secret_is_base32(self, app):
        with app.app_context():
            secret = generate_mfa_secret()
            assert len(secret) == 32  # pyotp default base32 length

    def test_correct_code_passes(self, app):
        with app.app_context():
            secret = generate_mfa_secret()
            totp = pyotp.TOTP(secret)
            assert verify_mfa_code(secret, totp.now()) is True

    def test_wrong_code_fails(self, app):
        with app.app_context():
            secret = generate_mfa_secret()
            assert verify_mfa_code(secret, "000000") is False


# ---------------------------------------------------------------------------
# Sanitisation
# ---------------------------------------------------------------------------
class TestSanitize:
    def test_strips_script_tags(self, app):
        with app.app_context():
            dirty = '<script>alert("xss")</script>Hello'
            assert sanitize_html(dirty) == 'alert("xss")Hello'

    def test_none_passthrough(self, app):
        with app.app_context():
            assert sanitize_html(None) is None
            assert sanitize_html("") == ""


# ---------------------------------------------------------------------------
# RBAC Permission Model
# ---------------------------------------------------------------------------
class TestRBACPermission:
    def test_create_and_query(self, app):
        with app.app_context():
            perm = RBACPermission(role="staff", resource="inventory", action="read")
            db.session.add(perm)
            db.session.commit()

            found = (
                db.session.query(RBACPermission).filter_by(role="staff", resource="inventory", action="read").first()
            )
            assert found is not None
            assert found.role == "staff"

    def test_missing_permission_returns_none(self, app):
        with app.app_context():
            found = (
                db.session.query(RBACPermission).filter_by(role="staff", resource="finance", action="delete").first()
            )
            assert found is None

    def test_conditions_jsonb(self, app):
        with app.app_context():
            perm = RBACPermission(
                role="merchant_admin",
                resource="transactions",
                action="read",
                conditions={"store_id": "own_store_only"},
            )
            db.session.add(perm)
            db.session.commit()

            found = db.session.query(RBACPermission).filter_by(role="merchant_admin", resource="transactions").first()
            assert found.conditions == {"store_id": "own_store_only"}


# ---------------------------------------------------------------------------
# Audit Logging
# ---------------------------------------------------------------------------
class TestAuditLog:
    def test_audit_log_is_created(self, app):
        with app.app_context():
            with app.test_request_context(environ_base={"REMOTE_ADDR": "10.0.0.1"}):
                audit_log(
                    "TEST_ACTION",
                    "TEST_RESOURCE",
                    resource_id="42",
                    result="SUCCESS",
                    meta_data={"detail": "integration-test"},
                )

                entry = db.session.query(AuditLog).filter_by(action="TEST_ACTION").first()
                assert entry is not None
                assert entry.result == "SUCCESS"
                assert entry.ip_address == "10.0.0.1"
                assert entry.meta_data == {"detail": "integration-test"}
                assert entry.resource_id == "42"

    def test_audit_log_failure_result(self, app):
        with app.app_context():
            with app.test_request_context(environ_base={"REMOTE_ADDR": "192.168.1.1"}):
                audit_log("LOGIN", "USER", resource_id="99", result="FAILURE")

                entry = db.session.query(AuditLog).filter_by(action="LOGIN", result="FAILURE").first()
                assert entry is not None
                assert entry.resource_id == "99"


# ---------------------------------------------------------------------------
# User MFA Fields
# ---------------------------------------------------------------------------
class TestUserMFAFields:
    def test_default_mfa_disabled(self, app):
        with app.app_context():
            user = User(mobile_number="9199990001", full_name="MFA Test")
            db.session.add(user)
            db.session.commit()

            assert user.mfa_enabled is False
            assert user.mfa_secret is None
            assert user.failed_login_attempts == 0

    def test_enable_mfa(self, app):
        with app.app_context():
            user = User(mobile_number="9199990002", full_name="MFA User")
            db.session.add(user)
            db.session.flush()

            secret = generate_mfa_secret()
            user.mfa_secret = secret
            user.mfa_enabled = True
            db.session.commit()

            fetched = db.session.query(User).filter_by(mobile_number="9199990002").first()
            assert fetched.mfa_enabled is True
            assert fetched.mfa_secret == secret
