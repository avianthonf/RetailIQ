from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from app import db
from app.models import Product, ProductPriceHistory, Alert, DailySkuSummary

class ProductService:
    @staticmethod
    def generate_next_sku(store_id: int) -> str:
        count = db.session.query(func.count(Product.product_id)).filter(Product.store_id == store_id).scalar() or 0
        return f"SKU-{store_id}-{count + 1}"

    @staticmethod
    def log_price_history(product_id: int, cost_price: float, selling_price: float, changed_by: int):
        history = ProductPriceHistory(
            product_id=product_id,
            cost_price=cost_price,
            selling_price=selling_price,
            changed_at=datetime.now(timezone.utc),
            changed_by=changed_by,
        )
        db.session.add(history)

    @staticmethod
    def create_alert(store_id: int, alert_type: str, priority: str, product_id: int, message: str):
        alert = Alert(
            store_id=store_id,
            alert_type=alert_type,
            priority=priority,
            product_id=product_id,
            message=message,
            created_at=datetime.now(timezone.utc),
            resolved_at=None,
        )
        db.session.add(alert)

    @staticmethod
    def get_slow_moving_product_ids(store_id: int) -> set[int]:
        cutoff = date_type.today() - timedelta(days=30)
        sold_ids = (
            db.session.query(DailySkuSummary.product_id)
            .filter(
                DailySkuSummary.store_id == store_id,
                DailySkuSummary.date >= cutoff,
                DailySkuSummary.units_sold > 0,
            )
            .distinct()
            .subquery()
        )

        slow = (
            db.session.query(Product.product_id)
            .filter(
                Product.store_id == store_id,
                Product.is_active == True,
                ~Product.product_id.in_(select(sold_ids.c.product_id)),
            )
            .all()
        )
        return {row.product_id for row in slow}
