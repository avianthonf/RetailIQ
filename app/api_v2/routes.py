from flask import g, jsonify, request

from app import db
from app.auth.utils import format_response
from app.developer.gateway import record_usage, require_oauth
from app.models import Product, Transaction

from . import api_v2_bp


@api_v2_bp.after_request
def after_api_request(response):
    return record_usage(response)


@api_v2_bp.route("/inventory", methods=["GET"])
@require_oauth(scopes=["read:inventory"])
def get_inventory():
    """Example V2 API: List products for a merchant's store."""
    store_id = request.args.get("store_id")
    if not store_id:
        return format_response(False, error={"code": "MISSING_STORE", "message": "store_id is required"}), 400

    products = db.session.query(Product).filter_by(store_id=store_id).all()
    return format_response(
        True,
        data=[
            {
                "id": p.product_id,
                "name": p.name,
                "sku": p.sku_code,
                "stock": float(p.current_stock or 0),
                "price": float(p.selling_price or 0),
            }
            for p in products
        ],
    ), 200


@api_v2_bp.route("/sales", methods=["GET"])
@require_oauth(scopes=["read:sales"])
def get_sales():
    """Example V2 API: List recent transactions."""
    store_id = request.args.get("store_id")
    if not store_id:
        return format_response(False, error={"code": "MISSING_STORE", "message": "store_id is required"}), 400

    transactions = (
        db.session.query(Transaction)
        .filter_by(store_id=store_id)
        .order_by(Transaction.created_at.desc())
        .limit(50)
        .all()
    )
    return format_response(
        True,
        data=[
            {"id": t.transaction_id, "total": float(t.total_amount), "created_at": t.created_at.isoformat()}
            for t in transactions
        ],
    ), 200
