from flask import Blueprint, request, g
from sqlalchemy import select

from .. import db
from ..models import Store, Category, Product
from ..auth.decorators import require_auth, require_role
from .schemas import StoreProfileSchema, CategorySchema, TaxConfigSchema
from marshmallow import ValidationError

store_bp = Blueprint('store', __name__)

# ---------------------------------------------------------------------------
# Default categories seeded on first store-type assignment
# ---------------------------------------------------------------------------
DEFAULT_CATEGORIES = {
    'grocery':     ['Beverages', 'Dairy', 'Snacks', 'Staples', 'Household', 'Personal Care'],
    'pharmacy':    ['OTC Medicine', 'Vitamins', 'Personal Care', 'Baby Care', 'Equipment'],
    'electronics': ['Mobile & Tablets', 'Laptops', 'Accessories', 'Audio', 'Home Appliances', 'Cameras'],
    'clothing':    ['Men', 'Women', 'Kids', 'Footwear', 'Accessories', 'Sports'],
    'general':     ['Food', 'Beverages', 'Household', 'Clothing', 'Electronics', 'Stationery'],
    'other':       ['Category 1', 'Category 2', 'Category 3'],
}

MAX_CATEGORIES = 50


def standard_response(data=None, message="Success", status_code=200, **kwargs):
    """Standard JSON envelope used across the store module."""
    response = {
        "status": "success" if status_code < 400 else "error",
        "message": message,
    }
    if data is not None:
        response["data"] = data
    response.update(kwargs)
    return response, status_code


# ---------------------------------------------------------------------------
# Store Profile  –  GET /api/v1/store/profile
#                   PUT /api/v1/store/profile
# ---------------------------------------------------------------------------

@store_bp.route('/profile', methods=['GET'])
@require_auth
def get_profile():
    store = db.session.scalar(
        select(Store).filter_by(store_id=g.current_user['store_id'])
    )
    if not store:
        return standard_response(message="Store not found", status_code=404)
    return standard_response(data=StoreProfileSchema().dump(store))


@store_bp.route('/profile', methods=['PUT'])
@require_auth
@require_role('owner')
def update_profile():
    schema = StoreProfileSchema()
    try:
        data = schema.load(request.json or {}, partial=True)
    except ValidationError as err:
        return standard_response(message="Validation error", status_code=400, errors=err.messages)

    store = db.session.scalar(
        select(Store).filter_by(store_id=g.current_user['store_id'])
    )
    if not store:
        return standard_response(message="Store not found", status_code=404)

    # Expire the cached object so we get a fresh read from the DB
    db.session.expire(store)

    # Re-fetch after expiry to get the real current state
    store = db.session.get(Store, store.store_id)

    # Track whether this is the very first time store_type is being set
    is_first_setup = store.store_type is None

    for key, value in data.items():
        setattr(store, key, value)

    # Seed default categories when store_type is assigned for the first time
    if (
        is_first_setup
        and 'store_type' in data
        and data['store_type'] in DEFAULT_CATEGORIES
    ):
        existing_count = db.session.scalar(
            select(db.func.count(Category.category_id))
            .where(Category.store_id == store.store_id)
        ) or 0

        if existing_count == 0:
            for cat_name in DEFAULT_CATEGORIES[data['store_type']]:
                db.session.add(Category(
                    store_id=store.store_id,
                    name=cat_name,
                    gst_rate=0.0,
                ))

    db.session.commit()
    return standard_response(message="Store profile updated", data=schema.dump(store))


# ---------------------------------------------------------------------------
# Categories  –  GET  /api/v1/store/categories
#                POST /api/v1/store/categories
#                PUT  /api/v1/store/categories/<id>
#                DELETE /api/v1/store/categories/<id>
# ---------------------------------------------------------------------------

@store_bp.route('/categories', methods=['GET'])
@require_auth
def list_categories():
    categories = db.session.scalars(
        select(Category).filter_by(store_id=g.current_user['store_id'])
    ).all()
    return standard_response(data=CategorySchema(many=True).dump(categories))


@store_bp.route('/categories', methods=['POST'])
@require_auth
@require_role('owner')
def create_category():
    # Enforce the 50-category cap
    category_count = db.session.scalar(
        select(db.func.count(Category.category_id))
        .filter_by(store_id=g.current_user['store_id'])
    ) or 0

    if category_count >= MAX_CATEGORIES:
        return standard_response(
            message=f"Maximum of {MAX_CATEGORIES} categories allowed per store",
            status_code=400,
        )

    schema = CategorySchema()
    try:
        data = schema.load(request.json or {})
    except ValidationError as err:
        return standard_response(message="Validation error", status_code=400, errors=err.messages)

    new_cat = Category(store_id=g.current_user['store_id'], **data)
    db.session.add(new_cat)
    db.session.commit()
    return standard_response(
        message="Category created", data=schema.dump(new_cat), status_code=201
    )


@store_bp.route('/categories/<int:category_id>', methods=['PUT'])
@require_auth
@require_role('owner')
def update_category(category_id):
    schema = CategorySchema()
    try:
        data = schema.load(request.json or {}, partial=True)
    except ValidationError as err:
        return standard_response(message="Validation error", status_code=400, errors=err.messages)

    category = db.session.scalar(
        select(Category).filter_by(
            category_id=category_id,
            store_id=g.current_user['store_id'],
        )
    )
    if not category:
        return standard_response(message="Category not found", status_code=404)

    for key, value in data.items():
        setattr(category, key, value)

    db.session.commit()
    return standard_response(message="Category updated", data=schema.dump(category))


@store_bp.route('/categories/<int:category_id>', methods=['DELETE'])
@require_auth
@require_role('owner')
def delete_category(category_id):
    category = db.session.scalar(
        select(Category).filter_by(
            category_id=category_id,
            store_id=g.current_user['store_id'],
        )
    )
    if not category:
        return standard_response(message="Category not found", status_code=404)

    # Rule: cannot hard-delete when products are still assigned – deactivate instead
    product_count = db.session.scalar(
        select(db.func.count(Product.product_id))
        .filter_by(category_id=category_id, store_id=g.current_user['store_id'])
    ) or 0

    if product_count > 0:
        return standard_response(
            message=(
                "Cannot delete category with assigned products. "
                "Please reassign or delete products first."
            ),
            status_code=422,
        )

    # Soft-delete: mark as inactive
    category.is_active = False
    db.session.commit()
    return standard_response(message="Category deactivated successfully")


# ---------------------------------------------------------------------------
# Tax Config  –  GET /api/v1/store/tax-config
#                PUT /api/v1/store/tax-config
# ---------------------------------------------------------------------------

@store_bp.route('/tax-config', methods=['GET'])
@require_auth
def get_tax_config():
    categories = db.session.scalars(
        select(Category).filter_by(store_id=g.current_user['store_id'])
    ).all()
    tax_data = [
        {"category_id": c.category_id, "name": c.name, "gst_rate": float(c.gst_rate or 0)}
        for c in categories
    ]
    return standard_response(data={"taxes": tax_data})


@store_bp.route('/tax-config', methods=['PUT'])
@require_auth
@require_role('owner')
def update_tax_config():
    schema = TaxConfigSchema()
    try:
        data = schema.load(request.json or {})
    except ValidationError as err:
        return standard_response(message="Validation error", status_code=400, errors=err.messages)

    taxes = data.get('taxes', [])
    store_id = g.current_user['store_id']
    updates_made = 0

    for item in taxes:
        category = db.session.scalar(
            select(Category).filter_by(
                category_id=item['category_id'],
                store_id=store_id,
            )
        )
        if category:
            category.gst_rate = item['gst_rate']
            updates_made += 1

    if updates_made > 0:
        db.session.commit()

    return standard_response(
        message=f"Updated GST rates for {updates_made} categories"
    )
