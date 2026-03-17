from flask import Blueprint, g, request
from marshmallow import ValidationError
from sqlalchemy import select

from app.utils.responses import standard_json

from .. import db
from ..auth.decorators import require_auth, require_role
from ..models import Category, Product, Store
from . import store_bp
from .schemas import CategorySchema, StoreProfileSchema, TaxConfigSchema
from .services import StoreService

# ---------------------------------------------------------------------------
# Store Profile  –  GET /api/v1/store/profile
#                   PUT /api/v1/store/profile
# ---------------------------------------------------------------------------


@store_bp.route("/profile", methods=["GET"])
@require_auth
def get_profile():
    store = db.session.scalar(select(Store).filter_by(store_id=g.current_user["store_id"]))
    if not store:
        return standard_json(success=False, message="Store not found", status_code=404)
    return standard_json(data=StoreProfileSchema().dump(store))


@store_bp.route("/profile", methods=["PUT"])
@require_auth
@require_role("owner")
def update_profile():
    schema = StoreProfileSchema()
    try:
        data = schema.load(request.json or {}, partial=True)
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    store = db.session.scalar(select(Store).filter_by(store_id=g.current_user["store_id"]))
    if not store:
        return standard_json(success=False, message="Store not found", status_code=404)

    # Expire the cached object so we get a fresh read from the DB
    db.session.expire(store)

    # Re-fetch after expiry to get the real current state
    store = db.session.get(Store, store.store_id)

    # Track whether this is the very first time store_type is being set
    is_first_setup = store.store_type is None

    for key, value in data.items():
        setattr(store, key, value)

    db.session.commit()

    # Seed default categories when store_type is assigned for the first time
    if is_first_setup and "store_type" in data:
        StoreService.seed_default_categories(store.store_id, data["store_type"])
        db.session.commit()

    return standard_json(message="Store profile updated", data=schema.dump(store))


# ---------------------------------------------------------------------------
# Categories  –  GET  /api/v1/store/categories
#                POST /api/v1/store/categories
#                PUT  /api/v1/store/categories/<id>
#                DELETE /api/v1/store/categories/<id>
# ---------------------------------------------------------------------------


@store_bp.route("/categories", methods=["GET"])
@require_auth
def list_categories():
    categories = db.session.scalars(select(Category).filter_by(store_id=g.current_user["store_id"])).all()
    return standard_json(data=CategorySchema(many=True).dump(categories))


@store_bp.route("/categories", methods=["POST"])
@require_auth
@require_role("owner")
def create_category():
    if StoreService.is_category_limit_reached(g.current_user["store_id"]):
        return standard_json(
            success=False,
            message="Maximum of 50 categories allowed per store reached",
            status_code=422,
        )

    schema = CategorySchema()
    try:
        data = schema.load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    new_cat = Category(store_id=g.current_user["store_id"], **data)
    db.session.add(new_cat)
    db.session.commit()
    return standard_json(message="Category created", data=schema.dump(new_cat), status_code=201)


@store_bp.route("/categories/<int:category_id>", methods=["PUT"])
@require_auth
@require_role("owner")
def update_category(category_id):
    schema = CategorySchema()
    try:
        data = schema.load(request.json or {}, partial=True)
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    category = db.session.scalar(
        select(Category).filter_by(
            category_id=category_id,
            store_id=g.current_user["store_id"],
        )
    )
    if not category:
        return standard_json(success=False, message="Category not found", status_code=404)

    for key, value in data.items():
        setattr(category, key, value)

    db.session.commit()
    return standard_json(message="Category updated", data=schema.dump(category))


@store_bp.route("/categories/<int:category_id>", methods=["DELETE"])
@require_auth
@require_role("owner")
def delete_category(category_id):
    category = db.session.scalar(
        select(Category).filter_by(
            category_id=category_id,
            store_id=g.current_user["store_id"],
        )
    )
    if not category:
        return standard_json(success=False, message="Category not found", status_code=404)

    # Rule: cannot hard-delete when products are still assigned – deactivate instead
    product_count = (
        db.session.scalar(
            select(db.func.count(Product.product_id)).filter_by(
                category_id=category_id, store_id=g.current_user["store_id"]
            )
        )
        or 0
    )

    if product_count > 0:
        return standard_json(
            success=False,
            message=("Cannot delete category with assigned products. " "Please reassign or delete products first."),
            status_code=422,
        )

    # Soft-delete: mark as inactive
    category.is_active = False
    db.session.commit()
    return standard_json(message="Category deactivated successfully")


# ---------------------------------------------------------------------------
# Tax Config  –  GET /api/v1/store/tax-config
#                PUT /api/v1/store/tax-config
# ---------------------------------------------------------------------------


@store_bp.route("/tax-config", methods=["GET"])
@require_auth
def get_tax_config():
    categories = db.session.scalars(select(Category).filter_by(store_id=g.current_user["store_id"])).all()
    tax_data = [{"category_id": c.category_id, "name": c.name, "gst_rate": float(c.gst_rate or 0)} for c in categories]
    return standard_json(data={"taxes": tax_data})


@store_bp.route("/tax-config", methods=["PUT"])
@require_auth
@require_role("owner")
def update_tax_config():
    schema = TaxConfigSchema()
    try:
        data = schema.load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    taxes = data.get("taxes", [])
    store_id = g.current_user["store_id"]
    updates_made = 0

    for item in taxes:
        category = db.session.scalar(
            select(Category).filter_by(
                category_id=item["category_id"],
                store_id=store_id,
            )
        )
        if category:
            category.gst_rate = item["gst_rate"]
            updates_made += 1

    if updates_made > 0:
        db.session.commit()

    return standard_json(message=f"Updated GST rates for {updates_made} categories")
