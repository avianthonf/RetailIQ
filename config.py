"""
RetailIQ Configuration
======================
Environment-based configuration classes.
"""

import os
from datetime import timedelta


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value not in (None, ""):
            return value
    return default


class Config:
    # ── Flask Core ────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = False
    TESTING = False

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://retailiq:retailiq@localhost:5432/retailiq")
    # SQLAlchemy uses SQLALCHEMY_DATABASE_URI
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", 10)),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 20)),
    }

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/1"))
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get("JWT_ACCESS_EXPIRES_HOURS", 24)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.environ.get("JWT_REFRESH_EXPIRES_DAYS", 30)))
    JWT_ALGORITHM = "HS256"

    # ── OTP ───────────────────────────────────────────────────────────────────
    OTP_TTL_SECONDS = int(os.environ.get("OTP_TTL_SECONDS", 120))
    OTP_RESEND_COOLDOWN_SECONDS = int(os.environ.get("OTP_RESEND_COOLDOWN_SECONDS", 45))

    # ── Email ─────────────────────────────────────────────────────────────────
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = _first_env("SMTP_USER", "MAIL_USERNAME")
    SMTP_PASSWORD = _first_env("SMTP_PASSWORD", "MAIL_PASSWORD")
    SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@retailiq.com")
    EMAIL_ENABLED = (
        os.environ.get(
            "EMAIL_ENABLED",
            "true"
            if _first_env("ENVIRONMENT", "FLASK_ENV", default="development").lower() == "production"
            and SMTP_USER
            and SMTP_PASSWORD
            else "false",
        ).lower()
        == "true"
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATELIMIT_STORAGE_URL = os.environ.get("REDIS_URL", "memory://")
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "200/hour")
    RATELIMIT_ENABLED = os.environ.get("RATELIMIT_ENABLED", "true").lower() == "true"

    # ── App Metadata ──────────────────────────────────────────────────────────
    APP_NAME = "RetailIQ"
    APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
    ENVIRONMENT = _first_env("ENVIRONMENT", "FLASK_ENV", default="development").lower()

    # ── Railway / Cloud ───────────────────────────────────────────────────────
    PORT = int(os.environ.get("PORT", 5000))

    # ── Celery Beat Schedule (seconds) ────────────────────────────────────────
    FORECAST_BATCH_INTERVAL = int(os.environ.get("FORECAST_BATCH_INTERVAL", 3600))


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "postgresql://retailiq:retailiq@localhost:5432/retailiq_test"
    )
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    # Force reading from env in prod
    SECRET_KEY = os.environ.get("SECRET_KEY") or (_ for _ in ()).throw(
        RuntimeError("SECRET_KEY environment variable is required in production")
    )

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", 20)),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 40)),
    }


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config():
    env = os.environ.get("FLASK_ENV", os.environ.get("ENVIRONMENT", "development")).lower()
    return config_map.get(env, DevelopmentConfig)
