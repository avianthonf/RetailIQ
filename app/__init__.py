import logging
import os
import re
import sys
import time

import redis as redis_lib
from celery import Celery
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

db = SQLAlchemy()
limiter = Limiter(key_func=get_remote_address)
celery_app = Celery()

# ── Known-weak secret values that MUST be rejected in production ────────────
_WEAK_SECRETS = frozenset(
    {
        "",
        "dev-secret-key",
        "dev-secret-change-in-production",
        "yoursecretkey",
        "change-me",
        "secret",
        "supersecret",
    }
)


def _generate_rsa_keys():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_pem.decode("utf-8"), public_pem.decode("utf-8")


def _validate_env(is_production, logger):
    """
    Validate required environment variables.

    In production: missing or weak values raise RuntimeError (fail fast).
    In development: missing values log warnings and use defaults.
    """
    errors = []

    # ── SECRET_KEY ───────────────────────────────────────────────────────
    secret = os.environ.get("SECRET_KEY", "")
    if is_production and secret.lower() in _WEAK_SECRETS:
        errors.append(
            "SECRET_KEY is missing or set to a known weak default. "
            'Generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
        )

    # ── DATABASE_URL ────────────────────────────────────────────────────
    db_url = os.environ.get("DATABASE_URL", "")
    if is_production and not db_url:
        errors.append("DATABASE_URL is required in production. " "Format: postgresql://user:password@host:5432/dbname")
    elif is_production and "retailiq:retailiq@" in db_url:
        errors.append(
            "DATABASE_URL uses default dev credentials (retailiq:retailiq). " "Set a strong password for production."
        )

    # ── REDIS_URL ───────────────────────────────────────────────────────
    redis_url = os.environ.get("REDIS_URL", "")
    if is_production and not redis_url:
        errors.append("REDIS_URL is required in production.")

    # ── CELERY_BROKER_URL ───────────────────────────────────────────────
    broker_url = os.environ.get("CELERY_BROKER_URL", "")
    if is_production and not broker_url:
        errors.append("CELERY_BROKER_URL is required in production.")

    # ── JWT keys ────────────────────────────────────────────────────────
    jwt_priv = os.environ.get("JWT_PRIVATE_KEY", "")
    jwt_pub = os.environ.get("JWT_PUBLIC_KEY", "")
    if is_production and (not jwt_priv or not jwt_pub):
        errors.append(
            "JWT_PRIVATE_KEY and JWT_PUBLIC_KEY are required in production. "
            "Generate with: openssl genrsa -out jwt.pem 2048"
        )
    elif is_production:
        # Check RSA key length/entropy (should be >= 2048)
        try:
            from cryptography.hazmat.primitives import serialization

            # Support both \n and raw newlines as per the code in create_app
            def _fix_pem(val):
                return val.replace("\\\\n", "\n").replace("\\n", "\n")

            decoded_key = _fix_pem(jwt_priv)
            key = serialization.load_pem_private_key(decoded_key.encode(), password=None)
            if key.key_size < 2048:
                errors.append(f"JWT_PRIVATE_KEY is too short ({key.key_size} bits). Use 2048 or higher.")
        except Exception as e:
            errors.append(f"Failed to validate JWT_PRIVATE_KEY: {e}")

    # ── Fail fast ───────────────────────────────────────────────────────
    if errors:
        msg = (
            "\n\n"
            "╔══════════════════════════════════════════════════════════╗\n"
            "║  STARTUP ABORTED — Missing or invalid configuration     ║\n"
            "╚══════════════════════════════════════════════════════════╝\n\n"
        )
        for i, err in enumerate(errors, 1):
            msg += f"  {i}. {err}\n"
        msg += "\nCopy .env.example to .env and fill in production values:\n" "  cp .env.example .env\n\n"
        raise RuntimeError(msg)

    # ── Dev-mode warnings ───────────────────────────────────────────────
    if not is_production:
        if not secret:
            logger.warning("SECRET_KEY not set — using ephemeral default (dev only)")
        if not db_url:
            logger.warning("DATABASE_URL not set — using default dev URI")
        if not redis_url:
            logger.warning("REDIS_URL not set — using default redis://redis:6379/0")


def create_app(config=None):
    # ── Load .env file BEFORE reading os.environ ────────────────────────
    # override=False means existing env vars (e.g. from docker-compose)
    # take priority over .env file values.
    dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    load_dotenv(dotenv_path, override=False)

    app = Flask(__name__)

    if config:
        app.config.update(config)

    is_production = os.environ.get("FLASK_ENV", "development") == "production"

    # ── Validate env vars (skip in test mode — fixtures provide config) ─
    if not app.config.get("TESTING"):
        _validate_env(is_production, app.logger)

    # ── Core config ─────────────────────────────────────────────────────
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", app.config.get("SECRET_KEY", "dev-secret-key"))

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
            "DATABASE_URL", "postgresql://retailiq:retailiq@postgres:5432/retailiq"
        )
    if not app.config.get("CELERY_BROKER_URL"):
        app.config["CELERY_BROKER_URL"] = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")

    # JWT RSA keys — mandatory in production, auto-generated only in dev/test
    jwt_private = os.environ.get("JWT_PRIVATE_KEY", "")
    jwt_public = os.environ.get("JWT_PUBLIC_KEY", "")
    if not app.config.get("JWT_PRIVATE_KEY"):
        if jwt_private and jwt_public:
            # .env stores PEM keys with \n as line separators.
            # Docker Compose passes these literally, so the env var may contain:
            #   - \\n  (two chars: backslash + n)  — from .env with \\n
            #   - real newlines                     — from .env with actual line breaks
            # Handle both by replacing literal backslash-n with real newlines.
            def _fix_pem(val):
                # Replace \\n (actual double-backslash + n) first, then \n (single backslash + n)
                return val.replace("\\\\n", "\n").replace("\\n", "\n")

            app.config["JWT_PRIVATE_KEY"] = _fix_pem(jwt_private)
            app.config["JWT_PUBLIC_KEY"] = _fix_pem(jwt_public)
        elif is_production:
            raise RuntimeError("JWT_PRIVATE_KEY and JWT_PUBLIC_KEY must be set in production")
        else:
            priv, pub = _generate_rsa_keys()
            app.config["JWT_PRIVATE_KEY"] = priv
            app.config["JWT_PUBLIC_KEY"] = pub

    if not app.config.get("RATELIMIT_STORAGE_URI"):
        app.config["RATELIMIT_STORAGE_URI"] = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    if not app.config.get("RATELIMIT_DEFAULT"):
        app.config["RATELIMIT_DEFAULT"] = "300/minute"

    # ── Email (Gmail SMTP) ──────────────────────────────────────────────
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")

    # Disable debug in production
    if is_production:
        app.config["DEBUG"] = False
        app.config["TESTING"] = False

    # CORS
    cors_origins = os.environ.get("CORS_ORIGINS", "")
    if cors_origins:
        CORS(app, origins=cors_origins.split(","), supports_credentials=True)
    elif not is_production:
        CORS(app)  # permissive in development only

    # ── Startup banner (non-test only) ──────────────────────────────────
    if not app.config.get("TESTING"):
        db_display = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        # Mask password in log output
        db_display = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", db_display)
        app.logger.info(
            "\n"
            "  ┌─────────────────────────────────────────────┐\n"
            "  │  RetailIQ starting                          │\n"
            "  ├─────────────────────────────────────────────┤\n"
            "  │  ENV:      %-31s │\n"
            "  │  DB:       %-31s │\n"
            "  │  REDIS:    %-31s │\n"
            "  │  BROKER:   %-31s │\n"
            "  │  JWT keys: %-31s │\n"
            "  │  .env:     %-31s │\n"
            "  └─────────────────────────────────────────────┘",
            os.environ.get("FLASK_ENV", "development"),
            db_display[:31],
            os.environ.get("REDIS_URL", "(default)")[:31],
            os.environ.get("CELERY_BROKER_URL", "(default)")[:31],
            "from env" if jwt_private else "auto-generated",
            "loaded" if os.path.exists(dotenv_path) else "NOT FOUND",
        )

    db.init_app(app)
    limiter.init_app(app)

    # ── Sensitive data log filter ────────────────────────────────────────
    class SensitiveDataFilter(logging.Filter):
        """Redact sensitive field values from log output."""

        _pattern = re.compile(
            r"(token|password|access_token|secret|x-api-key|auth_token|api_key|access_key)(\s*[:=]\s*)(\S+)",
            re.IGNORECASE,
        )

        def filter(self, record):
            if record.msg and isinstance(record.msg, str):
                record.msg = self._pattern.sub(r"\1\2***REDACTED***", record.msg)
            if record.args:
                new_args = []
                for a in record.args if isinstance(record.args, tuple) else (record.args,):
                    if isinstance(a, str):
                        a = self._pattern.sub(r"\1\2***REDACTED***", a)
                    new_args.append(a)
                record.args = tuple(new_args)
            return True

    sensitive_filter = SensitiveDataFilter()
    app.logger.addFilter(sensitive_filter)
    logging.getLogger().addFilter(sensitive_filter)

    # ── Dev-mode: SQLALCHEMY_ECHO + slow request hook ───────────────────
    if os.environ.get("FLASK_ENV", "development") == "development" and not app.config.get("TESTING"):
        app.config["SQLALCHEMY_ECHO"] = True

    @app.before_request
    def _record_request_start():
        from flask import g as _g

        _g._request_start_time = time.time()

    @app.after_request
    def _check_slow_request(response):
        from flask import g as _g

        start = getattr(_g, "_request_start_time", None)
        if start is not None:
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms > 500:
                app.logger.warning("[SLOW REQUEST] %s %s took %.0fms", request.method, request.path, elapsed_ms)

        # Add Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response

    # Configure Celery (support both legacy upper-case and Celery native lower-case keys)
    celery_conf = {
        "broker_url": app.config.get("CELERY_BROKER_URL"),
        "result_backend": app.config.get("CELERY_RESULT_BACKEND", app.config.get("CELERY_BROKER_URL")),
        "task_always_eager": bool(app.config.get("task_always_eager", app.config.get("CELERY_ALWAYS_EAGER", False))),
        "task_eager_propagates": bool(
            app.config.get("task_eager_propagates", app.config.get("CELERY_EAGER_PROPAGATES_EXCEPTIONS", True))
        ),
        # Celery 5.x warns that broker_connection_retry_on_startup will default to False in 6.0.
        # Force it on so compose logs stay clean and ECS workers auto-retry Redis outages on boot.
        "broker_connection_retry_on_startup": True,
    }
    celery_app.conf.update(celery_conf)
    celery_app.conf.update(app.config)

    # Register blueprints
    from app.analytics import analytics_bp
    from app.api_v2 import api_v2_bp
    from app.auth.oauth_routes import oauth_bp
    from app.decisions import decisions_bp
    from app.developer import developer_bp
    from app.finance import finance_bp
    from app.forecasting import forecasting_bp
    from app.nlp import nlp_bp

    from .ai_v2 import ai_v2_bp
    from .auth import auth_bp
    from .chain import chain_bp
    from .customers import customers_bp
    from .einvoicing import einvoicing_bp
    from .events import events_bp
    from .gst import gst_bp
    from .i18n import i18n_bp
    from .inventory import inventory_bp
    from .kyc import kyc_bp
    from .loyalty import loyalty_bp
    from .market_intelligence import market_intelligence_bp
    from .marketplace import marketplace_bp
    from .models import models_bp
    from .offline import offline_bp
    from .payments import payments_bp
    from .pricing import pricing_bp
    from .receipts import receipts_bp
    from .staff_performance import staff_performance_bp
    from .store import store_bp
    from .suppliers.routes import suppliers_bp
    from .tax_engine import tax_engine_bp
    from .team import team_bp
    from .transactions import transactions_bp
    from .vision import vision_bp
    from .whatsapp import whatsapp_bp

    app.register_blueprint(ai_v2_bp, url_prefix="/api/v2/ai")
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(i18n_bp, url_prefix="/api/v1")
    app.register_blueprint(tax_engine_bp, url_prefix="/api/v1")
    app.register_blueprint(payments_bp, url_prefix="/api/v1")
    app.register_blueprint(kyc_bp, url_prefix="/api/v1")
    app.register_blueprint(einvoicing_bp, url_prefix="/api/v1")
    app.register_blueprint(team_bp, url_prefix="/api/v1/team")
    app.register_blueprint(store_bp, url_prefix="/api/v1/store")
    app.register_blueprint(transactions_bp, url_prefix="/api/v1/transactions")
    app.register_blueprint(inventory_bp, url_prefix="/api/v1/inventory")
    app.register_blueprint(customers_bp, url_prefix="/api/v1/customers")
    app.register_blueprint(analytics_bp, url_prefix="/api/v1/analytics")
    app.register_blueprint(forecasting_bp, url_prefix="/api/v1/forecasting")
    app.register_blueprint(forecasting_bp, url_prefix="/api/v1/forecast", name="forecasting_alias1")
    app.register_blueprint(forecasting_bp, url_prefix="/api/v1", name="forecasting_alias2")
    app.register_blueprint(decisions_bp, url_prefix="/api/v1/recommendations")
    app.register_blueprint(nlp_bp, url_prefix="/api/v1/query")
    app.register_blueprint(models_bp, url_prefix="/api/v1/models")
    app.register_blueprint(receipts_bp, url_prefix="/api/v1")
    app.register_blueprint(suppliers_bp, url_prefix="/api/v1")
    app.register_blueprint(staff_performance_bp, url_prefix="/api/v1/staff")
    app.register_blueprint(offline_bp, url_prefix="/api/v1/offline")
    app.register_blueprint(loyalty_bp, url_prefix="/api/v1")
    app.register_blueprint(gst_bp, url_prefix="/api/v1")
    app.register_blueprint(whatsapp_bp, url_prefix="/api/v1")
    app.register_blueprint(chain_bp, url_prefix="/api/v1/chain")
    app.register_blueprint(pricing_bp, url_prefix="/api/v1/pricing")
    app.register_blueprint(events_bp, url_prefix="/api/v1")
    app.register_blueprint(vision_bp)
    app.register_blueprint(market_intelligence_bp, url_prefix="/api/v2/market")
    app.register_blueprint(developer_bp, url_prefix="/api/v1/developer")
    app.register_blueprint(oauth_bp, url_prefix="/oauth")
    app.register_blueprint(api_v2_bp, url_prefix="/api/v2")
    app.register_blueprint(finance_bp, url_prefix="/api/v2/finance")
    app.register_blueprint(marketplace_bp, url_prefix="/api/v2/marketplace")

    def _check_health():
        """Run actual DB and Redis connectivity checks."""
        health = {"status": "ok", "db": "unknown", "redis": "unknown"}
        http_status = 200

        # Check PostgreSQL
        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            health["db"] = "ok"
        except Exception as exc:
            health["db"] = "error"
            health["db_error"] = str(exc)
            health["status"] = "degraded"
            http_status = 503
            app.logger.error("Health check: DB unreachable: %s", exc)

        # Check Redis
        try:
            redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
            r = redis_lib.Redis.from_url(redis_url, socket_timeout=3)
            r.ping()
            health["redis"] = "ok"
        except Exception as exc:
            health["redis"] = "error"
            health["redis_error"] = str(exc)
            health["status"] = "degraded"
            http_status = 503
            app.logger.error("Health check: Redis unreachable: %s", exc)

        return jsonify(health), http_status

    # ALB / container orchestrator health probe (short path)
    @app.route("/health")
    def health_root():
        return _check_health()

    # API-namespaced health endpoint (backward compat)
    @app.route("/api/v1/health")
    def health_api():
        return _check_health()

    from marshmallow import ValidationError
    from werkzeug.exceptions import HTTPException

    from app.utils.responses import APIError, standard_json

    @app.errorhandler(APIError)
    def handle_api_error(err):
        return standard_json(
            success=False, message=err.message, status_code=err.status_code, error=err.errors, meta=err.meta
        )

    @app.errorhandler(ValidationError)
    def handle_validation_error(err):
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    @app.errorhandler(HTTPException)
    def handle_http_exception(err):
        """Pass through standard HTTP errors (like 429 Rate Limit)."""
        return standard_json(success=False, message=err.description, status_code=err.code, error={"code": err.name})

    @app.errorhandler(Exception)
    def handle_global_error(err):
        app.logger.exception("Unhandled exception: %s", err)
        return standard_json(
            success=False, message="Internal Server Error", status_code=500, error={"code": "SERVER_ERROR"}
        )

    return app
