"""
Shared pytest fixtures for the RetailIQ backend test-suite.

Uses an in-memory SQLite database so no Postgres / Redis instance is needed.

IMPORTANT – SQLite in-memory databases are per-connection by default.
We use StaticPool to force all SQLAlchemy connections (fixture sessions AND
Flask request sessions) to share the exact same connection/DB instance.
"""
import os

import pytest
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool


# ── make Postgres-specific types work on SQLite ─────────────────────────────
@compiles(JSONB, "sqlite")
def _compile_jsonb(type_, compiler, **kw):
    return "JSON"

@compiles(UUID, "sqlite")
def _compile_uuid(type_, compiler, **kw):
    return "VARCHAR"
# ────────────────────────────────────────────────────────────────────────────

from app import create_app
from app import db as _db
from app.auth.utils import generate_access_token
from app.models import Base, Category, Product, Store, User

# ---------------------------------------------------------------------------
# App / DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def app():
    """Create a fresh Flask app with an in-memory SQLite DB for each test.

    Uses StaticPool so every SQLAlchemy connection (fixture sessions AND Flask
    test-client request sessions) shares the exact same in-memory database.
    Without this each new connection gets an empty SQLite DB.
    """
    test_app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        },
        "CELERY_ALWAYS_EAGER": True,
        # Disable rate-limiting in tests
        "RATELIMIT_ENABLED": False,
        "RATELIMIT_STORAGE_URI": "memory://",
    })

    with test_app.app_context():
        # Generate test RSA keys
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
        test_app.config["JWT_PRIVATE_KEY"] = private_pem.decode("utf-8")
        test_app.config["JWT_PUBLIC_KEY"] = public_pem.decode("utf-8")

        Base.metadata.create_all(_db.engine)
        yield test_app
        _db.session.remove()

        # Safely delete all data ignoring FK constraints in SQLite
        with _db.engine.connect() as conn:
            conn.execute(_db.text("PRAGMA foreign_keys = OFF;"))
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(_db.text(f"DELETE FROM {table.name};"))
            conn.commit()
            conn.execute(_db.text("PRAGMA foreign_keys = ON;"))



@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def test_store(app):
    """Create a base store (no store_type so seeding tests work cleanly)."""
    store = Store(store_name="Test Supermart", store_type="grocery")
    _db.session.add(store)
    _db.session.commit()
    return store


@pytest.fixture(scope="function")
def test_owner(app, test_store):
    user = User(
        mobile_number="9000000001",
        full_name="Owner User",
        role="owner",
        store_id=test_store.store_id,
        is_active=True,
    )
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture(scope="function")
def test_staff(app, test_store):
    user = User(
        mobile_number="9000000002",
        full_name="Staff User",
        role="staff",
        store_id=test_store.store_id,
        is_active=True,
    )
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture(scope="function")
def owner_headers(app, test_owner, test_store):
    token = generate_access_token(test_owner.user_id, test_store.store_id, "owner")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def staff_headers(app, test_staff, test_store):
    token = generate_access_token(test_staff.user_id, test_store.store_id, "staff")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def test_category(app, test_store):
    cat = Category(store_id=test_store.store_id, name="Test Category", gst_rate=5.0)
    _db.session.add(cat)
    _db.session.commit()
    return cat


@pytest.fixture(scope="function")
def test_product(app, test_store, test_category):
    product = Product(
        store_id=test_store.store_id,
        category_id=test_category.category_id,
        name="Test Product",
        selling_price=100.0,
        cost_price=60.0,
        current_stock=50.0,
    )
    _db.session.add(product)
    _db.session.commit()
    return product
