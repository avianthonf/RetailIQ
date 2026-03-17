import logging
import os
import sys

from flask import Flask, jsonify
from flask_cors import CORS


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

        # ── Logging ────────────────────────────────────────────────────────────
        logging.basicConfig(
            level=logging.DEBUG if app.config.get("DEBUG") else logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

        # ── Extensions ─────────────────────────────────────────────────────────
        db.init_app(app)

        # Rate limiter — use Redis if available, fall back to memory
        redis_url = app.config.get("REDIS_URL", "memory://")
        app.config.setdefault("RATELIMIT_STORAGE_URL", redis_url)
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
