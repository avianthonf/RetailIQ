import logging
import os
import re
import sys

from flask import Flask, jsonify
from flask_cors import CORS

_SENSITIVE_PATTERNS = re.compile(
    r'((?:access_token|password|secret|api_key|token)\s*[=:]\s*)\S+',
    re.IGNORECASE,
)
_SENSITIVE_REPLACE = r'\1***REDACTED***'


class SensitiveDataFilter(logging.Filter):
    """Redact sensitive values from log records before emission."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.msg, record.args = self._redact_msg_args(record.msg, record.args)
        else:
            record.msg = _SENSITIVE_PATTERNS.sub(_SENSITIVE_REPLACE, str(record.msg))
        return True

    @staticmethod
    def _redact_msg_args(msg, args):
        try:
            formatted = msg % args if args else str(msg)
        except (TypeError, ValueError):
            return msg, args
        redacted = _SENSITIVE_PATTERNS.sub(_SENSITIVE_REPLACE, formatted)
        return redacted, None


def create_app(config_object=None):
    try:
        from . import db, limiter

        app = Flask(__name__)

        # ── Configuration ──────────────────────────────────────────────────────
        if config_object is None:
            from config import get_config

            config_object = get_config()

        if isinstance(config_object, dict):
            app.config.from_mapping(config_object)
        else:
            app.config.from_object(config_object)

        # Ensure ENVIRONMENT defaults to development
        app.config.setdefault("ENVIRONMENT", "development")

        # ── Default JWT Config ────────────────────────────────────────────────
        app.config.setdefault("JWT_ACCESS_TOKEN_EXPIRES", 3600)
        app.config.setdefault("JWT_REFRESH_TOKEN_EXPIRES", 86400 * 30)
        app.config.setdefault("JWT_ALGORITHM", "HS256")
        app.config.setdefault("JWT_SECRET_KEY", "dev-secret-key-12345")
        app.config.setdefault("SECRET_KEY", os.environ.get("SECRET_KEY", "dev-secret-key-12345"))

        if app.config.get("TESTING"):
            app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

        if not app.config.get("SQLALCHEMY_DATABASE_URI"):
            app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL") or "sqlite:///:memory:"

        # Railway injects DATABASE_URL with postgres:// prefix (deprecated), fix it
        db_url = app.config.get("SQLALCHEMY_DATABASE_URI")
        if db_url and db_url.startswith("postgres://"):
            app.config["SQLALCHEMY_DATABASE_URI"] = db_url.replace("postgres://", "postgresql://", 1)

        # ── Logging (stdout for Railway / Docker log capture) ────────────────
        log_level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
        log_fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

        # Explicit stdout handler — Railway/Docker only capture stdout/stderr
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(log_level)
        stdout_handler.setFormatter(log_fmt)

        _sensitive_filter = SensitiveDataFilter()

        # Configure root logger so ALL library loggers (smtplib, etc.) are captured
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        # Remove any pre-existing handlers to avoid duplicates
        root_logger.handlers.clear()
        root_logger.addHandler(stdout_handler)
        root_logger.addFilter(_sensitive_filter)

        # Ensure Flask's own logger also uses stdout
        app.logger.handlers.clear()
        app.logger.addHandler(stdout_handler)
        app.logger.setLevel(log_level)
        app.logger.propagate = False
        app.logger.addFilter(_sensitive_filter)

        # ── Extensions ─────────────────────────────────────────────────────────
        db.init_app(app)

        # Rate limiter — use Redis if available, fall back to memory
        # We explicitly exclude "memory://" from truthy checks to force fallback if REDIS_URL exists
        explicit_storage_url = app.config.get("RATELIMIT_STORAGE_URL") or app.config.get("RATELIMIT_STORAGE_URI")
        if explicit_storage_url:
            redis_url = explicit_storage_url
        elif app.config.get("TESTING") or not app.config.get("RATELIMIT_ENABLED", True):
            redis_url = "memory://"
        else:
            redis_url = (
                app.config.get("REDIS_URL")
                or os.environ.get("REDIS_URL")
                or os.environ.get("CELERY_BROKER_URL")
                or "memory://"
            )

        # Debug logging for production (masking credentials)
        if app.config.get("ENVIRONMENT") == "production":
            masked_url = redis_url
            if "@" in redis_url:
                prefix = redis_url.split("@")[0].split("//")[0] + "//"
                suffix = redis_url.split("@")[1]
                masked_url = f"{prefix}****:****@{suffix}"
            app.logger.info(f"Resolved RATELIMIT_STORAGE_URL: {masked_url}")

        app.config["RATELIMIT_STORAGE_URL"] = redis_url
        app.config["RATELIMIT_STORAGE_URI"] = redis_url
        limiter.init_app(app)

        CORS(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}})

        # ── Production Readiness Check ────────────────────────────────────────
        if app.config.get("ENVIRONMENT") == "production" or os.environ.get("FLASK_ENV") == "production":
            from .utils.security import check_production_readiness

            with app.app_context():
                check_production_readiness()

        # ── Register Blueprints ────────────────────────────────────────────────
        from . import _register_blueprints

        _register_blueprints(app)

        # ── Health & Root Routes ───────────────────────────────────────────────
        @app.route("/health")
        def health():
            return jsonify({"status": "ok", "version": app.config.get("APP_VERSION", "1.0.0")}), 200

        @app.route("/")
        def root():
            return jsonify(
                {
                    "name": "RetailIQ API",
                    "version": app.config.get("APP_VERSION", "1.0.0"),
                    "docs": "/api/v1",
                    "health": "/health",
                }
            ), 200

        # ── Error Handlers ─────────────────────────────────────────────────────
        from . import _register_error_handlers

        _register_error_handlers(app)

        # ── Shell Context ──────────────────────────────────────────────────────
        @app.shell_context_processor
        def make_shell_context():
            from app import models  # noqa

            return {"db": db, "app": app}

        return app
    except BaseException as e:
        raise e
