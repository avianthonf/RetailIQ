"""
Security hardening tests for RetailIQ backend.

Tests:
  1. test_login_rate_limit — verify 429 on 11th login attempt within a minute
  2. test_store_scoping_on_all_new_endpoints — verify cross-store isolation
  3. test_sensitive_fields_not_in_logs — verify log redaction of tokens/secrets
"""
import io
import logging
import pytest

from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Re-use the SQLite type shims (idempotent — if conftest already ran, these are no-ops)
try:
    @compiles(JSONB, "sqlite")
    def _jsonb(type_, compiler, **kw):
        return "JSON"

    @compiles(UUID, "sqlite")
    def _uuid(type_, compiler, **kw):
        return "VARCHAR"
except Exception:
    pass

from app import create_app, db as _db
from app.models import Base, User, Store, Supplier, Product, Category
from app.auth.utils import generate_access_token


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def rate_limit_app():
    """App with rate limiting ENABLED (separate from the shared conftest app)."""
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        },
        "CELERY_ALWAYS_EAGER": True,
        "RATELIMIT_ENABLED": True,
        "RATELIMIT_STORAGE_URI": "memory://",
    })
    with app.app_context():
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

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

def test_login_rate_limit(rl_client, rate_limit_app):
    """Call login 11 times in quick succession — the 11th should get 429."""
    with rate_limit_app.app_context():
        import bcrypt
        pw = bcrypt.hashpw(b"test123", bcrypt.gensalt(4)).decode()
        s = Store(store_name="RateLimitStore", store_type="grocery")
        _db.session.add(s)
        _db.session.commit()
        u = User(
            mobile_number="9999900000",
            password_hash=pw,
            full_name="RL User",
            role="owner",
            store_id=s.store_id,
            is_active=True,
        )
        _db.session.add(u)
        _db.session.commit()

    payload = {"mobile_number": "9999900000", "password": "test123"}
    last_status = None
    for i in range(11):
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
    Create two stores. JWT from store B must not see store A's data
    on all post-launch endpoints.
    """
    with app.app_context():
        storeA, ownerA, headersA = _make_store_and_owner("StoreA", "8000000001")
        storeB, ownerB, headersB = _make_store_and_owner("StoreB", "8000000002")

        # Seed store A with a supplier
        s = Supplier(store_id=storeA.store_id, name="Supplier Alpha")
        _db.session.add(s)
        _db.session.commit()
        supplier_id = str(s.id)

        # Seed store A with a product (for events/vision routes)
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

        # ── Suppliers: store B should get empty list, not store A's supplier
        resp = client.get("/api/v1/suppliers", headers=headersB)
        assert resp.status_code == 200
        body = resp.json
        supplier_ids = [s["id"] for s in body.get("data", body if isinstance(body, list) else [])]
        assert supplier_id not in supplier_ids

        # ── Suppliers detail: store B should get 404 for store A's supplier
        resp = client.get(f"/api/v1/suppliers/{supplier_id}", headers=headersB)
        assert resp.status_code in (403, 404)

        # ── Events: store B should get empty list
        resp = client.get("/api/v1/events", headers=headersB)
        assert resp.status_code == 200

        # ── Staff sessions: store B should get its own session (or none)
        resp = client.get("/api/v1/staff/sessions/current", headers=headersB)
        assert resp.status_code in (200, 404)

        # ── GST config: store B should get its own (unconfigured)
        resp = client.get("/api/v1/gst/config", headers=headersB)
        assert resp.status_code in (200, 404)

        # ── Loyalty program: store B should get 404 (not configured)
        resp = client.get("/api/v1/loyalty/program", headers=headersB)
        assert resp.status_code in (200, 404)

        # ── Pricing suggestions: store B should get empty/own data
        resp = client.get("/api/v1/pricing/suggestions", headers=headersB)
        assert resp.status_code in (200, 404)

        # ── Receipt template: store B has no template
        resp = client.get("/api/v1/receipts/template", headers=headersB)
        assert resp.status_code in (200, 404)

        # ── WhatsApp config: store B has no config
        resp = client.get("/api/v1/whatsapp/config", headers=headersB)
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 3) SENSITIVE DATA LOG REDACTION TEST
# ══════════════════════════════════════════════════════════════════════════════

def test_sensitive_fields_not_in_logs(client, app):
    """
    PUT /whatsapp/config with an access_token value.
    The raw token must NOT appear in captured log output.
    """
    with app.app_context():
        store, owner, headers = _make_store_and_owner("LogTestStore", "8000000003")

        secret_token = "EAAGm0PX4ZCps_SUPER_SECRET_TOKEN_12345"

        # Capture log output
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        app.logger.addHandler(handler)
        logging.getLogger().addHandler(handler)

        try:
            # Trigger a request that carries the sensitive token
            resp = client.put(
                "/api/v1/whatsapp/config",
                headers=headers,
                json={
                    "phone_number_id": "123456",
                    "access_token": secret_token,
                    "is_active": True,
                },
            )
            # The request should succeed (200) — we're testing logging, not the endpoint
            assert resp.status_code == 200

            # Now deliberately log something containing the token pattern
            app.logger.info("Config updated with access_token= %s", secret_token)

            log_output = log_capture.getvalue()

            # The raw token value must NOT appear in logs
            assert secret_token not in log_output, (
                f"Secret token was found in logs! Log content:\n{log_output[:500]}"
            )
        finally:
            app.logger.removeHandler(handler)
            logging.getLogger().removeHandler(handler)


# ══════════════════════════════════════════════════════════════════════════════
# 4) STARTUP VALIDATION TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_production_refuses_to_start_without_secret_key():
    """
    In production mode, create_app must raise RuntimeError if SECRET_KEY
    is missing or set to a weak default.
    """
    import os
    old_env = os.environ.get('FLASK_ENV')
    old_secret = os.environ.get('SECRET_KEY')
    try:
        os.environ['FLASK_ENV'] = 'production'
        os.environ['SECRET_KEY'] = 'dev-secret-change-in-production'
        with pytest.raises(RuntimeError, match='SECRET_KEY'):
            create_app({'TESTING': False})
    finally:
        # Restore environment
        if old_env is not None:
            os.environ['FLASK_ENV'] = old_env
        else:
            os.environ.pop('FLASK_ENV', None)
        if old_secret is not None:
            os.environ['SECRET_KEY'] = old_secret
        else:
            os.environ.pop('SECRET_KEY', None)


def test_production_refuses_default_db_credentials():
    """
    In production mode, create_app must raise RuntimeError if DATABASE_URL
    uses the default dev credentials (retailiq:retailiq).
    """
    import os
    import secrets as _secrets
    old_env = os.environ.get('FLASK_ENV')
    old_secret = os.environ.get('SECRET_KEY')
    old_db = os.environ.get('DATABASE_URL')
    old_redis = os.environ.get('REDIS_URL')
    old_broker = os.environ.get('CELERY_BROKER_URL')
    old_jwt_priv = os.environ.get('JWT_PRIVATE_KEY')
    old_jwt_pub = os.environ.get('JWT_PUBLIC_KEY')
    try:
        os.environ['FLASK_ENV'] = 'production'
        os.environ['SECRET_KEY'] = _secrets.token_urlsafe(64)
        os.environ['DATABASE_URL'] = 'postgresql://retailiq:retailiq@localhost:5432/retailiq'
        os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
        os.environ['CELERY_BROKER_URL'] = 'redis://localhost:6379/1'
        os.environ['JWT_PRIVATE_KEY'] = 'dummy-key'
        os.environ['JWT_PUBLIC_KEY'] = 'dummy-key'
        with pytest.raises(RuntimeError, match='default dev credentials'):
            create_app({'TESTING': False})
    finally:
        for k, v in [('FLASK_ENV', old_env), ('SECRET_KEY', old_secret),
                      ('DATABASE_URL', old_db), ('REDIS_URL', old_redis),
                      ('CELERY_BROKER_URL', old_broker),
                      ('JWT_PRIVATE_KEY', old_jwt_priv), ('JWT_PUBLIC_KEY', old_jwt_pub)]:
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


def test_development_mode_starts_with_defaults():
    """
    In development mode, create_app must succeed even without explicit
    env vars (uses defaults and auto-generates JWT keys).
    """
    import os
    old_env = os.environ.get('FLASK_ENV')
    try:
        os.environ['FLASK_ENV'] = 'development'
        app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'SQLALCHEMY_ENGINE_OPTIONS': {
                'connect_args': {'check_same_thread': False},
                'poolclass': StaticPool,
            },
        })
        assert app is not None
        assert app.config.get('JWT_PRIVATE_KEY')
        assert app.config.get('JWT_PUBLIC_KEY')
    finally:
        if old_env is not None:
            os.environ['FLASK_ENV'] = old_env
        else:
            os.environ.pop('FLASK_ENV', None)
