"""developer platform tables

Revision ID: d6e87a2b9c45
Revises: f4a5b6c7d8e9
Create Date: 2026-03-09 21:25:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d6e87a2b9c45"
down_revision: Union[str, None] = "85d1654fde0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Developers ───────────────────────────────────────────────────────────
    op.create_table(
        "developers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=False),
        sa.Column("organization", sa.String(length=128), nullable=True),
        sa.Column("api_key_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # ── Developer Applications ───────────────────────────────────────────────
    op.create_table(
        "developer_applications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("developer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "app_type",
            sa.Enum("WEB", "MOBILE", "BACKEND", "INTEGRATION", name="app_type_enum"),
            nullable=False,
        ),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("client_secret_hash", sa.String(length=128), nullable=False),
        sa.Column("redirect_uris", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "tier",
            sa.Enum("FREE", "GROWTH", "BUSINESS", "ENTERPRISE", name="app_tier_enum"),
            server_default="FREE",
            nullable=False,
        ),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=False),
        sa.Column("monthly_quota", sa.Integer(), nullable=True),
        sa.Column("webhook_url", sa.String(length=512), nullable=True),
        sa.Column("webhook_secret", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "SUSPENDED", "REVOKED", name="app_status_enum"),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["developer_id"], ["developers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )
    op.create_index("idx_dev_app_client_id", "developer_applications", ["client_id"])

    # ── API Usage Records ────────────────────────────────────────────────────
    op.create_table(
        "api_usage_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("endpoint", sa.String(length=256), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("minute_bucket", sa.TIMESTAMP(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("avg_latency_ms", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("p99_latency_ms", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("bytes_transferred", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["app_id"], ["developer_applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_usage_app_minute", "api_usage_records", ["app_id", "minute_bucket"])

    # ── Webhook Events ───────────────────────────────────────────────────────
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("delivery_url", sa.String(length=512), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "DELIVERED",
                "FAILED",
                "DEAD_LETTERED",
                name="webhook_status_enum",
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_response_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.ForeignKeyConstraint(["app_id"], ["developer_applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Marketplace Apps ─────────────────────────────────────────────────────
    op.create_table(
        "marketplace_apps",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("developer_app_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("tagline", sa.String(length=256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("icon_url", sa.String(length=512), nullable=True),
        sa.Column("screenshots", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "pricing_model",
            sa.Enum("FREE", "FREEMIUM", "PAID", "SUBSCRIPTION", name="pricing_model_enum"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("install_count", sa.Integer(), nullable=False),
        sa.Column("avg_rating", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column(
            "security_scan_status",
            sa.Enum("PENDING", "PASSED", "FAILED", name="security_scan_status_enum"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.Enum(
                "SUBMITTED",
                "IN_REVIEW",
                "APPROVED",
                "REJECTED",
                name="review_status_enum",
            ),
            server_default="SUBMITTED",
            nullable=False,
        ),
        sa.Column("published_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["developer_app_id"], ["developer_applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("marketplace_apps")
    op.drop_table("webhook_events")
    op.drop_table("api_usage_records")
    op.drop_table("developer_applications")
    op.drop_table("developers")
    # Note: Enums are not dropped here to avoid issues with other tables if reused
    # but in this case they are specific to these tables.
    # op.execute("DROP TYPE app_type_enum")
    # op.execute("DROP TYPE app_tier_enum")
    # op.execute("DROP TYPE app_status_enum")
    # op.execute("DROP TYPE webhook_status_enum")
    # op.execute("DROP TYPE pricing_model_enum")
    # op.execute("DROP TYPE security_scan_status_enum")
    # op.execute("DROP TYPE review_status_enum")
