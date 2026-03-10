from app import db
from app.models import Category

DEFAULT_CATEGORIES = {
    "grocery": ["Beverages", "Dairy", "Snacks", "Staples", "Household", "Personal Care"],
    "pharmacy": ["OTC Medicine", "Vitamins", "Personal Care", "Baby Care", "Equipment"],
    "electronics": ["Mobile & Tablets", "Laptops", "Accessories", "Audio", "Home Appliances", "Cameras"],
    "clothing": ["Men", "Women", "Kids", "Footwear", "Accessories", "Sports"],
    "general": ["Food", "Beverages", "Household", "Clothing", "Electronics", "Stationery"],
    "other": ["Category 1", "Category 2", "Category 3"],
}

MAX_CATEGORIES = 50

class StoreService:
    @staticmethod
    def seed_default_categories(store_id: int, store_type: str):
        """Seeds default categories if none exist and store_type matches defined defaults."""
        if store_type not in DEFAULT_CATEGORIES:
            return 0
            
        existing_count = db.session.query(Category.category_id).filter_by(store_id=store_id).count()
        if existing_count > 0:
            return 0
            
        added = 0
        for cat_name in DEFAULT_CATEGORIES[store_type]:
            db.session.add(
                Category(
                    store_id=store_id,
                    name=cat_name,
                    gst_rate=0.0,
                )
            )
            added += 1
        return added

    @staticmethod
    def is_category_limit_reached(store_id: int) -> bool:
        """Checks if the store has hit the maximum allowed categories."""
        count = db.session.query(Category.category_id).filter_by(store_id=store_id).count()
        return count >= MAX_CATEGORIES
