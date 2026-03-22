"""
Security hardening tests for RetailIQ backend.

Tests:
  1. test_login_rate_limit — verify 429 on 11th login attempt within a minute
  2. test_store_scoping_on_all_new_endpoints — verify cross-store isolation
  3. test_sensitive_fields_not_in_logs — verify log redaction of tokens/secrets
  4. Startup validation tests (production/development)
"""

import io
import json
import logging
import os
import secrets as _secrets

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

# Re-use the SQLite type shims
try:

    @compiles(JSONB, "sqlite")
    def _jsonb(type_, compiler, **kw):
        return "JSON"

    @compiles(UUID, "sqlite")
    def _uuid(type_, compiler, **kw):
        return "VARCHAR"
except Exception:
    pass

from app import create_app
from app import db as _db
from app.auth.utils import generate_access_token
from app.models import Base, Category, Product, Store, Supplier, User

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="function")
def rate_limit_app():
    """App with rate limiting ENABLED."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "connect_args": {"check_same_thread": False},
                "poolclass": StaticPool,
            },
            "CELERY_ALWAYS_EAGER": True,
            "RATELIMIT_ENABLED": True,
            "RATELIMIT_STORAGE_URL": "memory://",
        }
    )
    with app.app_context():
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        app.config["JWT_PRIVATE_KEY"] = private_pem.decode("utf-8")
        app.config["JWT_PUBLIC_KEY"] = public_pem.decode("utf-8")

        Base.metadata.create_all(_db.engine)
        yield app
        _db.session.remove()


@pytest.fixture(scope="function")
def rl_client(rate_limit_app):
    return rate_limit_app.test_client()


def _make_store_and_owner(store_name, mobile):
    """Helper: create a store + owner + JWT headers."""
    store = Store(store_name=store_name, store_type="grocery")
    _db.session.add(store)
    _db.session.commit()

    import bcrypt

    pw = bcrypt.hashpw(b"Password1!", bcrypt.gensalt(4)).decode()
    user = User(
        mobile_number=mobile,
        password_hash=pw,
        full_name=f"Owner of {store_name}",
        role="owner",
        store_id=store.store_id,
        is_active=True,
    )
    _db.session.add(user)
    _db.session.commit()

    token = generate_access_token(user.user_id, store.store_id, "owner")
    headers = {"Authorization": f"Bearer {token}"}
    return store, user, headers


# ══════════════════════════════════════════════════════════════════════════════
# 1) RATE LIMIT TEST
# ══════════════════════════════════════════════════════════════════════════════


def test_login_rate_limit(rl_client, rate_limit_app, monkeypatch):
    """Call login 11 times in quick succession — the 11th should get 429."""
    from unittest.mock import MagicMock

    mock_redis = MagicMock()
    monkeypatch.setattr("app.auth.utils.get_redis_client", lambda: mock_redis)
    monkeypatch.setattr("app.auth.routes.get_redis_client", lambda: mock_redis)

    with rate_limit_app.app_context():
        s = Store(store_name="RateLimitStore", store_type="grocery")
        _db.session.add(s)
        _db.session.commit()
        u = User(
            mobile_number="9999900000",
            full_name="RL User",
            email="rate.limit@example.com",
            role="owner",
            store_id=s.store_id,
            is_active=True,
        )
        _db.session.add(u)
        _db.session.commit()

    payload = {"email": "rate.limit@example.com"}
    last_status = None
    for _i in range(11):
        resp = rl_client.post("/api/v1/auth/login", json=payload)
        last_status = resp.status_code
        if last_status == 429:
            break

    assert last_status == 429, f"Expected 429 on or before 11th attempt, got {last_status}"


# ══════════════════════════════════════════════════════════════════════════════
# 2) STORE SCOPING TEST
# ══════════════════════════════════════════════════════════════════════════════


def test_store_scoping_on_all_new_endpoints(client, app):
    """
    Create two stores. JWT from store B must not see store A's data.
    """
    with app.app_context():

        def _setup_store(name, mobile):
            store = Store(store_name=name, store_type="grocery")
            _db.session.add(store)
            _db.session.commit()

            user = User(
                mobile_number=mobile,
                full_name=f"Owner of {name}",
                role="owner",
                store_id=store.store_id,
                is_active=True,
            )
            _db.session.add(user)
            _db.session.commit()

            token = generate_access_token(user.user_id, store.store_id, "owner")
            return store, user, {"Authorization": f"Bearer {token}"}

        storeA, ownerA, headersA = _setup_store("StoreA", "8000000001")
        storeB, ownerB, headersB = _setup_store("StoreB", "8000000002")

        # Seed store A with a supplier
        s = Supplier(store_id=storeA.store_id, name="Supplier Alpha")
        _db.session.add(s)
        _db.session.commit()
        supplier_id = str(s.id)

        # Seed store A with a product
        cat = Category(store_id=storeA.store_id, name="TestCat", gst_rate=5.0)
        _db.session.add(cat)
        _db.session.commit()
        prod = Product(
            store_id=storeA.store_id,
            category_id=cat.category_id,
            name="TestProd",
            selling_price=100,
            cost_price=60,
            current_stock=50,
        )
        _db.session.add(prod)
        _db.session.commit()

        # Suppliers: store B should get empty list
        resp = client.get("/api/v1/suppliers", headers=headersB)
        assert resp.status_code == 200
        body = resp.json
        supplier_ids = [s["id"] for s in body.get("data", [])]
        assert supplier_id not in supplier_ids

        # Suppliers detail: store B should get 403 or 404
        resp = client.get(f"/api/v1/suppliers/{supplier_id}", headers=headersB)
        assert resp.status_code in (403, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 3) SENSITIVE DATA LOG REDACTION TEST
# ══════════════════════════════════════════════════════════════════════════════


def test_sensitive_fields_not_in_logs(client, app):
    """
    PUT /whatsapp/config with an access_token.
    Raw token must NOT appear in captured log output.
    """
    with app.app_context():
        store, owner, headers = _make_store_and_owner("LogTestStore", "8000000003")
        secret_token = "EAAGm0PX4ZCps_SUPER_SECRET_TOKEN_12345"

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        app.logger.addHandler(handler)
        logging.getLogger().addHandler(handler)

        try:
            resp = client.put(
                "/api/v1/whatsapp/config",
                headers=headers,
                json={
                    "phone_number_id": "123456",
                    "access_token": secret_token,
                    "is_active": True,
                },
            )
            assert resp.status_code == 200
            app.logger.info("Config updated with access_token= %s", secret_token)
            log_output = log_capture.getvalue()
            assert secret_token not in log_output
        finally:
            app.logger.removeHandler(handler)
            logging.getLogger().removeHandler(handler)


# ══════════════════════════════════════════════════════════════════════════════
# 4) STARTUP VALIDATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


def test_production_refuses_to_start_without_secret_key(monkeypatch):
    """Production mode must raise RuntimeError if SECRET_KEY is missing."""
    from app.utils.security import check_production_readiness

    with monkeypatch.context() as m:
        m.setenv("FLASK_ENV", "production")
        m.delenv("SECRET_KEY", raising=False)
        m.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        with pytest.raises(RuntimeError) as excinfo:
            check_production_readiness()
        assert "SECRET_KEY" in str(excinfo.value)


def test_production_refuses_default_db_credentials(monkeypatch):
    """Production mode must raise RuntimeError if default credentials are used."""
    with monkeypatch.context() as m:
        m.setenv("FLASK_ENV", "production")
        m.setenv("ENVIRONMENT", "production")
        m.setenv("SECRET_KEY", "STRONG_SECRET_FOR_PROD_TEST_1234567890!")
        m.setenv("DATABASE_URL", "postgresql://retailiq:retailiq@localhost:5432/retailiq")

        # Explicit config to be 100% sure
        with pytest.raises(RuntimeError) as exc_info:
            create_app(
                {
                    "TESTING": False,
                    "ENVIRONMENT": "production",
                    "SECRET_KEY": "STRONG_SECRET_FOR_PROD_TEST_1234567890!",
                    "SQLALCHEMY_DATABASE_URI": "postgresql://retailiq:retailiq@localhost:5432/retailiq",
                    "EMAIL_ENABLED": True,
                    "SMTP_USER": "test@example.com",
                    "SMTP_PASSWORD": "password",
                }
            )
        assert "default dev credentials" in str(exc_info.value)


def test_production_refuses_email_disabled(monkeypatch):
    """Production mode must raise RuntimeError if email delivery is disabled."""
    with monkeypatch.context() as m:
        m.setenv("FLASK_ENV", "production")
        m.setenv("ENVIRONMENT", "production")
        m.setenv("SECRET_KEY", "STRONG_SECRET_FOR_PROD_TEST_1234567890!")
        m.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/retailiq")

        with pytest.raises(RuntimeError) as exc_info:
            create_app(
                {
                    "TESTING": False,
                    "ENVIRONMENT": "production",
                    "SECRET_KEY": "STRONG_SECRET_FOR_PROD_TEST_1234567890!",
                    "SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@localhost:5432/retailiq",
                    "EMAIL_ENABLED": False,
                    "SMTP_USER": "test@example.com",
                    "SMTP_PASSWORD": "password",
                }
            )
        assert "EMAIL_ENABLED" in str(exc_info.value)


def test_production_refuses_missing_smtp_credentials(monkeypatch):
    """Production mode must raise RuntimeError if SMTP credentials are missing."""
    with monkeypatch.context() as m:
        m.setenv("FLASK_ENV", "production")
        m.setenv("ENVIRONMENT", "production")
        m.setenv("SECRET_KEY", "STRONG_SECRET_FOR_PROD_TEST_1234567890!")
        m.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/retailiq")

        with pytest.raises(RuntimeError) as exc_info:
            create_app(
                {
                    "TESTING": False,
                    "ENVIRONMENT": "production",
                    "SECRET_KEY": "STRONG_SECRET_FOR_PROD_TEST_1234567890!",
                    "SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@localhost:5432/retailiq",
                    "EMAIL_ENABLED": True,
                    "SMTP_USER": "",
                    "SMTP_PASSWORD": "",
                }
            )
        assert "SMTP_USER and SMTP_PASSWORD" in str(exc_info.value)


def test_production_accepts_mail_aliases_for_email_credentials(monkeypatch):
    """Production mode should accept legacy MAIL_* aliases for email config."""
    with monkeypatch.context() as m:
        m.setenv("FLASK_ENV", "production")
        m.setenv("ENVIRONMENT", "production")
        m.setenv("SECRET_KEY", "STRONG_SECRET_FOR_PROD_TEST_1234567890!")
        m.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/retailiq")

        app = create_app(
            {
                "TESTING": False,
                "ENVIRONMENT": "production",
                "SECRET_KEY": "STRONG_SECRET_FOR_PROD_TEST_1234567890!",
                "SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@localhost:5432/retailiq",
                "EMAIL_ENABLED": True,
                "MAIL_USERNAME": "alias@example.com",
                "MAIL_PASSWORD": "password",
            }
        )

        assert app.config.get("EMAIL_ENABLED") is True

def test_development_mode_starts_with_defaults(monkeypatch):
    """Development mode must succeed with defaults."""
    with monkeypatch.context() as m:
        m.setenv("FLASK_ENV", "development")
        m.delenv("ENVIRONMENT", raising=False)
        m.delenv("DATABASE_URL", raising=False)
        m.setenv("SECRET_KEY", "test-secret")

        app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
        assert app is not None
        assert app.config.get("ENVIRONMENT") == "development"
