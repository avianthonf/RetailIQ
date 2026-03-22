"""
Comprehensive tests for Alembic migration correctness and schema drift prevention.

Validates that:
- Migration column types match SQLAlchemy model definitions
- env.py include_object filters are configured correctly
- Alembic check passes on a fresh database (no schema drift)
- Expression-based indexes are properly excluded from comparison
"""

import importlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy import Text, inspect

from app.models import Base

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations" / "versions"


# ===========================================================================
# Unit Tests: reconcile migration column types
# ===========================================================================


class TestReconcileMigrationTypes:
    """Verify 121021f2b187 reconcile migration uses Text() not String(None)."""

    RECONCILE_FILE = MIGRATIONS_DIR / "121021f2b187_reconcile_schema_drift.py"

    def _read_migration(self):
        return self.RECONCILE_FILE.read_text(encoding="utf-8")

    def test_reconcile_migration_exists(self):
        assert self.RECONCILE_FILE.exists(), "Reconcile migration file missing"

    def test_no_string_length_none_in_reconcile(self):
        """sa.String(length=None) should never appear — use sa.Text() instead."""
        content = self._read_migration()
        matches = re.findall(r"sa\.String\(length=None\)", content)
        assert len(matches) == 0, (
            f"Found {len(matches)} occurrence(s) of sa.String(length=None) in reconcile migration. "
            "These should be sa.Text() to match model definitions."
        )

    @pytest.mark.parametrize(
        "table,column",
        [
            ("translation_keys", "description"),
            ("translations", "value"),
            ("insurance_products", "description"),
            ("country_tax_configs", "compliance_notes"),
            ("merchant_kyc", "notes"),
            ("kyc_records", "rejection_reason"),
            ("e_invoices", "xml_payload"),
            ("e_invoices", "qr_code_data"),
            ("e_invoices", "digital_signature"),
            ("marketplace_catalog_items", "description"),
            ("marketplace_supplier_reviews", "review_text"),
            ("audit_logs", "user_agent"),
        ],
    )
    def test_text_column_uses_sa_text(self, table, column):
        """Each Text column in the reconcile migration must use sa.Text()."""
        content = self._read_migration()
        # Find the create_table block for this table and verify the column
        # uses sa.Text() — a simple check that the column name appears near sa.Text()
        pattern = rf'"{column}".*?sa\.Text\(\)'
        assert re.search(pattern, content, re.DOTALL), (
            f"Column '{table}.{column}' should use sa.Text() in reconcile migration"
        )


# ===========================================================================
# Unit Tests: developer platform migration column types
# ===========================================================================


class TestDeveloperPlatformMigrationTypes:
    """Verify d6e87a2b9c45 uses DateTime() not TIMESTAMP() for model columns."""

    DEV_PLATFORM_FILE = MIGRATIONS_DIR / "d6e87a2b9c45_developer_platform.py"

    def _read_migration(self):
        return self.DEV_PLATFORM_FILE.read_text(encoding="utf-8")

    def test_dev_platform_migration_exists(self):
        assert self.DEV_PLATFORM_FILE.exists(), "Developer platform migration file missing"

    @pytest.mark.parametrize(
        "column_pattern",
        [
            r'"created_at", sa\.DateTime\(\)',  # developers.created_at
            r'"minute_bucket", sa\.DateTime\(\)',  # api_usage_records.minute_bucket
            r'"last_attempt_at", sa\.DateTime\(\)',  # webhook_events.last_attempt_at
            r'"published_at", sa\.DateTime\(\)',  # marketplace_apps.published_at
        ],
    )
    def test_datetime_column_uses_sa_datetime(self, column_pattern):
        """DateTime columns must use sa.DateTime() not sa.TIMESTAMP()."""
        content = self._read_migration()
        assert re.search(column_pattern, content), (
            f"Expected pattern {column_pattern} not found in developer platform migration. "
            "Columns should use sa.DateTime() to match model definitions."
        )

    def test_no_timestamp_in_dev_platform(self):
        """sa.TIMESTAMP() should not appear in developer platform migration."""
        content = self._read_migration()
        matches = re.findall(r"sa\.TIMESTAMP\(\)", content)
        assert len(matches) == 0, (
            f"Found {len(matches)} occurrence(s) of sa.TIMESTAMP() in developer platform migration. "
            "These should be sa.DateTime() to match missing_models.py."
        )


# ===========================================================================
# Unit Tests: market intelligence migration column types
# ===========================================================================


class TestMarketIntelligenceMigrationTypes:
    """Verify 0a1b2c3d4e5f uses DateTime() not TIMESTAMP()."""

    MI_FILE = MIGRATIONS_DIR / "0a1b2c3d4e5f_market_intelligence.py"

    def test_mi_migration_exists(self):
        assert self.MI_FILE.exists(), "Market intelligence migration file missing"

    def test_no_timestamp_in_mi_migration(self):
        """sa.TIMESTAMP() should not appear in market intelligence migration."""
        content = self.MI_FILE.read_text(encoding="utf-8")
        matches = re.findall(r"sa\.TIMESTAMP\(\)", content)
        assert len(matches) == 0, (
            f"Found {len(matches)} occurrence(s) of sa.TIMESTAMP() in market intelligence migration. "
            "These should be sa.DateTime() to match missing_models.py."
        )


# ===========================================================================
# Unit Tests: env.py include_object configuration
# ===========================================================================


class TestEnvPyConfiguration:
    """Verify migrations/env.py has correct include_object filters."""

    ENV_FILE = PROJECT_ROOT / "migrations" / "env.py"

    def _read_env(self):
        return self.ENV_FILE.read_text(encoding="utf-8")

    def test_env_py_exists(self):
        assert self.ENV_FILE.exists()

    def test_sqlite_filter_skips_all_indexes(self):
        """SQLite include_object must skip all indexes."""
        content = self._read_env()
        assert "include_object_sqlite" in content
        assert re.search(
            r'def include_object_sqlite.*?if type_ == "index".*?return False',
            content,
            re.DOTALL,
        ), "SQLite filter must return False for all indexes"

    def test_pg_filter_skips_expression_indexes(self):
        """Postgres include_object must skip expression-based indexes."""
        content = self._read_env()
        assert "include_object_pg" in content
        for idx_name in [
            "idx_daily_sku_summary_store_product_date",
            "idx_daily_store_summary_store_date",
            "idx_transactions_store_created",
        ]:
            assert idx_name in content, f"Expression index '{idx_name}' must be listed in _EXPRESSION_INDEXES"

    def test_pg_filter_allows_regular_indexes(self):
        """Postgres filter must NOT skip regular (non-expression) indexes."""
        content = self._read_env()
        # The Postgres filter should only skip indexes in _EXPRESSION_INDEXES,
        # not ALL indexes like the SQLite filter does
        assert re.search(
            r'def include_object_pg.*?if type_ == "index" and name in _EXPRESSION_INDEXES',
            content,
            re.DOTALL,
        ), "Postgres filter must only skip expression indexes, not all indexes"

    def test_dialect_specific_filter_selection(self):
        """env.py must select different filters for SQLite vs Postgres."""
        content = self._read_env()
        assert 'connection.dialect.name == "sqlite"' in content
        assert "obj_filter = include_object_sqlite" in content
        assert "obj_filter = include_object_pg" in content


# ===========================================================================
# Unit Tests: Model column types match expectations
# ===========================================================================


class TestModelColumnTypes:
    """Verify SQLAlchemy model columns have the correct types."""

    @pytest.mark.parametrize(
        "model_name,column_name,expected_type",
        [
            ("TranslationKey", "description", sa.Text),
            ("Translation", "value", sa.Text),
            ("InsuranceProduct", "description", sa.Text),
            ("CountryTaxConfig", "compliance_notes", sa.Text),
            ("MerchantKYC", "notes", sa.Text),
            ("KYCRecord", "rejection_reason", sa.Text),
            ("EInvoice", "xml_payload", sa.Text),
            ("EInvoice", "qr_code_data", sa.Text),
            ("EInvoice", "digital_signature", sa.Text),
            ("CatalogItem", "description", sa.Text),
            ("SupplierReview", "review_text", sa.Text),
            ("AuditLog", "user_agent", sa.Text),
        ],
    )
    def test_text_columns_use_text_type(self, model_name, column_name, expected_type):
        """Model Text columns must use sa.Text, not sa.String."""
        model = None
        for mapper in Base.registry.mappers:
            if mapper.class_.__name__ == model_name:
                model = mapper.class_
                break
        assert model is not None, f"Model '{model_name}' not found in registry"
        col = model.__table__.columns[column_name]
        assert isinstance(col.type, expected_type), (
            f"{model_name}.{column_name} should be {expected_type.__name__}, got {type(col.type).__name__}"
        )

    @pytest.mark.parametrize(
        "model_name,column_name",
        [
            ("Developer", "created_at"),
            ("DeveloperApplication", "created_at"),
            ("MarketplaceApp", "published_at"),
            ("APIUsageRecord", "minute_bucket"),
            ("WebhookEvent", "last_attempt_at"),
            ("WebhookEvent", "created_at"),
        ],
    )
    def test_datetime_columns_use_datetime_type(self, model_name, column_name):
        """Developer platform model DateTime columns must use DateTime, not TIMESTAMP."""
        model = None
        for mapper in Base.registry.mappers:
            if mapper.class_.__name__ == model_name:
                model = mapper.class_
                break
        assert model is not None, f"Model '{model_name}' not found in registry"
        col = model.__table__.columns[column_name]
        assert isinstance(col.type, sa.DateTime), (
            f"{model_name}.{column_name} should be DateTime, got {type(col.type).__name__}"
        )


# ===========================================================================
# Integration Test: Alembic check on fresh database
# ===========================================================================


class TestAlembicCheck:
    """Integration tests verifying alembic check passes on fresh database."""

    def test_alembic_upgrade_and_check_sqlite(self, tmp_path):
        """Alembic upgrade + check must pass on a fresh SQLite database."""
        db_path = tmp_path / "test_alembic.db"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"

        # Run alembic upgrade head
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"alembic upgrade head failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

        # Run alembic check
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"alembic check detected drift:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "No new upgrade operations detected" in (result.stdout + result.stderr)


# ===========================================================================
# Migration chain integrity
# ===========================================================================


class TestMigrationChainIntegrity:
    """Verify the migration chain is consistent."""

    def test_all_migration_files_are_valid_python(self):
        """Every migration file must be valid Python."""
        for py_file in MIGRATIONS_DIR.glob("*.py"):
            if py_file.name == "__pycache__":
                continue
            try:
                compile(py_file.read_text(encoding="utf-8"), str(py_file), "exec")
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {py_file.name}: {e}")

    def test_migration_chain_has_single_head(self, tmp_path):
        """There must be exactly one head in the migration chain."""
        db_path = tmp_path / "test_heads.db"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "heads"],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
        # Count lines that contain revision hashes (head markers)
        head_lines = [l for l in output.strip().split("\n") if "(head)" in l]
        assert len(head_lines) == 1, f"Expected exactly 1 head, found {len(head_lines)}: {head_lines}"
