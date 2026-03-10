from datetime import datetime, timezone
from typing import List, Optional

from flask import g, jsonify, request

from app import db
from app.auth.decorators import require_auth
from app.auth.utils import format_response
from app.models.marketplace_models import (
    RFQ,
    CatalogItem,
    MarketplacePOItem,
    MarketplacePurchaseOrder,
    ProcurementRecommendation,
    RFQResponse,
    SupplierProfile,
    SupplierReview,
)

from . import marketplace_bp
from .logistics import get_tracking_events
from .services import (
    create_marketplace_order,
    create_rfq,
    get_procurement_recommendations,
    get_supplier_dashboard,
    search_catalog,
)


@marketplace_bp.route("/search", methods=["GET"])
@require_auth
def search():
    query = request.args.get("query")
    category = request.args.get("category")
    price_min = request.args.get("price_min", type=float)
    price_max = request.args.get("price_max", type=float)
    supplier_rating_min = request.args.get("supplier_rating_min", type=float)
    moq_max = request.args.get("moq_max", type=int)
    sort_by = request.args.get("sort_by", "relevance")
    page = request.args.get("page", 1, type=int)
    limit = 20
    offset = (page - 1) * limit

    result = search_catalog(db.session, query, category, price_min, price_max, supplier_rating_min, moq_max, sort_by, limit, offset)
    return format_response(data=result)


@marketplace_bp.route("/recommendations", methods=["GET"])
@require_auth
def recommendations():
    merchant_id = g.current_user["store_id"]
    category = request.args.get("category")
    urgency = request.args.get("urgency")

    res = get_procurement_recommendations(db.session, merchant_id, category, urgency)
    return format_response(data=res)


@marketplace_bp.route("/rfq", methods=["POST"])
@require_auth
def create_rfq_route():
    data = request.get_json() or {}
    merchant_id = g.current_user["store_id"]
    items = data.get("items")

    if not items:
        return format_response(error="items required", status_code=422)

    res = create_rfq(db.session, merchant_id, items)
    return format_response(data=res, status_code=201)


@marketplace_bp.route("/rfq/<int:rfq_id>", methods=["GET"])
@require_auth
def get_rfq_route(rfq_id):
    merchant_id = g.current_user["store_id"]
    rfq = db.session.query(RFQ).filter(RFQ.id == rfq_id, RFQ.merchant_id == merchant_id).first()

    if not rfq:
        return format_response(error="RFQ not found", status_code=404)

    responses = db.session.query(RFQResponse).filter(RFQResponse.rfq_id == rfq_id).all()
    resp_list = [{
        "id": r.id,
        "supplier_profile_id": r.supplier_profile_id,
        "quoted_items": r.quoted_items,
        "total_price": float(r.total_price),
        "delivery_days": r.delivery_days,
        "status": r.status
    } for r in responses]

    result = {
        "id": rfq.id,
        "items": rfq.items,
        "status": rfq.status,
        "matched_suppliers_count": rfq.matched_suppliers_count,
        "created_at": rfq.created_at.isoformat(),
        "responses": resp_list
    }

    return format_response(data=result)


@marketplace_bp.route("/orders", methods=["POST"])
@require_auth
def create_order_route():
    data = request.get_json() or {}
    merchant_id = g.current_user["store_id"]

    supplier_id = data.get("supplier_id")
    items = data.get("items")
    payment_terms = data.get("payment_terms", "prepaid")
    finance_requested = data.get("finance_requested", False)

    if not supplier_id or not items:
        return format_response(error="supplier_id and items required", status_code=422)

    try:
        res = create_marketplace_order(db.session, merchant_id, supplier_id, items, payment_terms, finance_requested)
        return format_response(data=res, status_code=201)
    except ValueError as e:
        return format_response(error=str(e), status_code=422)


@marketplace_bp.route("/orders", methods=["GET"])
@require_auth
def list_orders_route():
    merchant_id = g.current_user["store_id"]
    status = request.args.get("status")
    supplier_id = request.args.get("supplier_id", type=int)
    page = request.args.get("page", 1, type=int)
    limit = 20
    offset = (page - 1) * limit

    q = db.session.query(MarketplacePurchaseOrder).filter(MarketplacePurchaseOrder.merchant_id == merchant_id)

    if status:
        q = q.filter(MarketplacePurchaseOrder.status == status)
    if supplier_id:
        q = q.filter(MarketplacePurchaseOrder.supplier_profile_id == supplier_id)

    total = q.count()
    orders = q.order_by(MarketplacePurchaseOrder.created_at.desc()).limit(limit).offset(offset).all()

    order_list = []
    for order in orders:
        order_list.append({
            "id": order.id,
            "order_number": order.order_number,
            "supplier_profile_id": order.supplier_profile_id,
            "status": order.status,
            "total": float(order.total),
            "payment_status": order.payment_status,
            "financed": order.financed_by_retailiq,
            "created_at": order.created_at.isoformat(),
            "expected_delivery": order.expected_delivery.isoformat() if order.expected_delivery else None
        })

    return format_response(data={"orders": order_list, "total": total, "page": page, "pages": (total + limit - 1) // limit})


@marketplace_bp.route("/orders/<int:order_id>", methods=["GET"])
@require_auth
def get_order_route(order_id):
    merchant_id = g.current_user["store_id"]
    order = db.session.query(MarketplacePurchaseOrder).filter(MarketplacePurchaseOrder.id == order_id, MarketplacePurchaseOrder.merchant_id == merchant_id).first()

    if not order:
        return format_response(error="Order not found", status_code=404)

    items = db.session.query(MarketplacePOItem).filter(MarketplacePOItem.order_id == order.id).all()
    item_list = [{
        "catalog_item_id": i.catalog_item_id,
        "quantity": i.quantity,
        "unit_price": float(i.unit_price),
        "subtotal": float(i.subtotal)
    } for i in items]

    res = {
        "id": order.id,
        "order_number": order.order_number,
        "supplier_profile_id": order.supplier_profile_id,
        "status": order.status,
        "subtotal": float(order.subtotal),
        "tax": float(order.tax),
        "shipping_cost": float(order.shipping_cost),
        "total": float(order.total),
        "payment_status": order.payment_status,
        "financed": order.financed_by_retailiq,
        "loan_id": order.loan_id,
        "created_at": order.created_at.isoformat(),
        "expected_delivery": order.expected_delivery.isoformat() if order.expected_delivery else None,
        "shipping_tracking": order.shipping_tracking,
        "items": item_list
    }

    return format_response(data=res)


@marketplace_bp.route("/orders/<int:order_id>/track", methods=["GET"])
@require_auth
def track_order_route(order_id):
    merchant_id = g.current_user["store_id"]
    order = db.session.query(MarketplacePurchaseOrder).filter(MarketplacePurchaseOrder.id == order_id, MarketplacePurchaseOrder.merchant_id == merchant_id).first()

    if not order:
        return format_response(error="Order not found", status_code=404)

    tracking_number = None
    if order.shipping_tracking and isinstance(order.shipping_tracking, dict):
        tracking_number = order.shipping_tracking.get("tracking_number")

    if not tracking_number:
        return format_response(data={"status": order.status, "tracking_events": [], "logistics_provider": None})

    events = get_tracking_events(tracking_number)

    return format_response(data={
        "status": order.status,
        "tracking_events": events,
        "estimated_delivery": order.expected_delivery.isoformat() if order.expected_delivery else None,
        "logistics_provider": order.shipping_tracking.get("provider", "Unknown") if order.shipping_tracking else None
    })


@marketplace_bp.route("/suppliers/dashboard", methods=["GET"])
@require_auth
def supplier_dashboard_route():
    # In a real system, the supplier identity would be derived from the user/auth token
    # For now, we accept a supplier_id query param or default to something
    supplier_profile_id = request.args.get("supplier_id", type=int)

    if not supplier_profile_id:
        return format_response(error="supplier_id required", status_code=422)

    res = get_supplier_dashboard(db.session, supplier_profile_id)
    return format_response(data=res)


@marketplace_bp.route("/suppliers/<int:supplier_id>/catalog", methods=["GET"])
@require_auth
def supplier_catalog_route(supplier_id):
    page = request.args.get("page", 1, type=int)
    limit = 50
    offset = (page - 1) * limit

    q = db.session.query(CatalogItem).filter(CatalogItem.supplier_profile_id == supplier_id, CatalogItem.is_active == True)
    total = q.count()
    items = q.limit(limit).offset(offset).all()

    item_list = [{
        "id": i.id,
        "sku": i.sku,
        "name": i.name,
        "category": i.category,
        "unit_price": float(i.unit_price),
        "moq": i.moq
    } for i in items]

    return format_response(data={"items": item_list, "total": total})


@marketplace_bp.route("/suppliers/onboard", methods=["POST"])
@require_auth
def supplier_onboard_route():
    data = request.get_json() or {}
    # Normally merchant creates a supplier, or supplier signs themselves up
    # Here we mock it by creating a SupplierProfile

    supplier_id = data.get("supplier_id") # Must map to an existing Supplier UUID if necessary, or we create one
    if not supplier_id:
        from app.models import Supplier
        # Create base supplier first
        store_id = g.current_user["store_id"]
        s = Supplier(store_id=store_id, name=data.get("business_name", "New Supplier"))
        db.session.add(s)
        db.session.flush()
        supplier_id = s.id

    profile = SupplierProfile(
        supplier_id=supplier_id,
        business_name=data.get("business_name", "New Supplier"),
        business_type=data.get("business_type", "WHOLESALER"),
        verified=False,
        categories=data.get("categories", []),
        payment_terms=data.get("payment_terms", {"net30": True})
    )
    db.session.add(profile)
    db.session.commit()

    return format_response(data={"id": profile.id, "business_name": profile.business_name}, status_code=201)

