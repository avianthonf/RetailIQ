"""RetailIQ Inventory Services."""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ProductService:
    @staticmethod
    def generate_next_sku(store_id: int) -> str:
        """Generate the next auto-incrementing SKU for a store."""
        from sqlalchemy import func

        from app import db
        from app.models import Product

        count = db.session.query(func.count(Product.product_id)).filter_by(store_id=store_id).scalar() or 0
        return f"SKU-{store_id:04d}-{count + 1:06d}"

    @staticmethod
    def log_price_history(product_id: int, cost_price, selling_price, changed_by: int):
        """Insert a ProductPriceHistory record (no commit — caller commits)."""
        from app import db
        from app.models import ProductPriceHistory

        record = ProductPriceHistory(
            product_id=product_id,
            cost_price=cost_price,
            selling_price=selling_price,
            changed_by=changed_by,
            changed_at=datetime.now(timezone.utc),
        )
        db.session.add(record)

    @staticmethod
    def create_alert(store_id: int, alert_type: str, priority: str, product_id: int, message: str):
        """Create or update an inventory alert."""
        from app import db
        from app.models import Alert

        existing = (
            db.session.query(Alert)
            .filter(
                Alert.store_id == store_id,
                Alert.alert_type == alert_type,
                Alert.product_id == product_id,
                Alert.resolved_at.is_(None),
            )
            .first()
        )
        if existing:
            existing.message = message
            existing.priority = priority
        else:
            alert = Alert(
                store_id=store_id,
                alert_type=alert_type,
                priority=priority,
                product_id=product_id,
                message=message,
            )
            db.session.add(alert)

    @staticmethod
    def get_slow_moving_product_ids(store_id: int, days: int = 30, threshold: float = 0.5) -> set:
        """Return product_ids with avg daily units sold below threshold."""
        from sqlalchemy import func, text

        from app import db

        rows = db.session.execute(
            text("""
            SELECT product_id, SUM(units_sold)::float / :days AS avg_daily
            FROM daily_sku_summary
            WHERE store_id = :sid
              AND date >= CURRENT_DATE - :days
            GROUP BY product_id
            HAVING SUM(units_sold)::float / :days < :threshold
            """),
            {"sid": store_id, "days": days, "threshold": threshold},
        ).fetchall()
        return {r.product_id for r in rows}
