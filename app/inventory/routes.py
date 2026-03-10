import contextlib
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from flask import g, request
from marshmallow import ValidationError
from sqlalchemy import exists, func, select

from .. import db
from ..auth.decorators import require_auth, require_role
from ..models import (
    Alert,
    Product,
    StockAdjustment,
    StockAudit,
    StockAuditItem,
    ProductPriceHistory,
)
from . import inventory_bp
from .schemas import (
    ProductCreateSchema,
    ProductUpdateSchema,
    StockAuditSchema,
    StockUpdateSchema,
    ProductSchema,
)
from .services import ProductService
from app.utils.responses import standard_json

# ──────────────────────────────────────────────────────────────
# Products – Collection
# ──────────────────────────────────────────────────────────────


@inventory_bp.route("/products", methods=["GET"])
@require_auth
def list_products():
    store_id = g.current_user["store_id"]

    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    category_id = request.args.get("category_id", type=int)
    is_active = request.args.get("is_active")
    low_stock = request.args.get("low_stock", "false").lower() == "true"
    slow_moving = request.args.get("slow_moving", "false").lower() == "true"

    query = db.session.query(Product).filter(Product.store_id == store_id)

    if category_id is not None:
        query = query.filter(Product.category_id == category_id)

    if is_active is not None:
        query = query.filter(Product.is_active == (is_active.lower() == "true"))

    if low_stock:
        query = query.filter(Product.current_stock <= Product.reorder_level)

    total = query.count()
    products = query.order_by(Product.product_id).offset((page - 1) * page_size).limit(page_size).all()

    # Apply slow_moving filter after fetching (needs daily_sku_summary query)
    if slow_moving:
        slow_ids = ProductService.get_slow_moving_product_ids(store_id)
        products = [p for p in products if p.product_id in slow_ids]
        # Re-count with slow_moving is approximate; total reflects pre-filter
        total = len(products)

    from .schemas import ProductSchema
    return standard_json(
        data=ProductSchema(many=True).dump(products), 
        meta={"page": page, "page_size": page_size, "total": total}
    )


@inventory_bp.route("/products", methods=["POST"])
@require_auth
@require_role("owner")
def create_product():
    try:
        data = ProductCreateSchema().load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    store_id = g.current_user["store_id"]
    user_id = g.current_user["user_id"]

    # Auto-generate SKU if blank
    sku = data.get("sku_code") or None
    if not sku:
        sku = ProductService.generate_next_sku(store_id)

    from ..models import Product
    product = Product(
        store_id=store_id,
        category_id=data.get("category_id"),
        name=data["name"],
        sku_code=sku,
        uom=data.get("uom"),
        cost_price=data["cost_price"],
        selling_price=data["selling_price"],
        current_stock=data.get("current_stock", 0.0),
        reorder_level=data.get("reorder_level", 0.0),
        supplier_name=data.get("supplier_name"),
        barcode=data.get("barcode"),
        image_url=data.get("image_url"),
        lead_time_days=data.get("lead_time_days", 3),
        is_active=True,
    )

    db.session.add(product)
    db.session.flush()  # get product_id before committing

    # Log initial price
    ProductService.log_price_history(product.product_id, data["cost_price"], data["selling_price"], user_id)
    db.session.commit()

    from .schemas import ProductSchema
    return standard_json(data=ProductSchema().dump(product), status_code=201)


# ──────────────────────────────────────────────────────────────
# Products – Single resource
# ──────────────────────────────────────────────────────────────


@inventory_bp.route("/products/<int:product_id>", methods=["GET"])
@require_auth
def get_product(product_id):
    store_id = g.current_user["store_id"]
    from ..models import Product
    product = db.session.query(Product).filter_by(product_id=product_id, store_id=store_id).first()
    if not product:
        return standard_json(success=False, message="Product not found", status_code=404)
    from .schemas import ProductSchema
    return standard_json(data=ProductSchema().dump(product))


@inventory_bp.route("/products/<int:product_id>", methods=["PUT"])
@require_auth
def update_product(product_id):
    store_id = g.current_user["store_id"]
    user_id = g.current_user["user_id"]

    product = db.session.query(Product).filter_by(product_id=product_id, store_id=store_id).first()
    if not product:
        return standard_json(success=False, message="Product not found", status_code=404)

    try:
        data = ProductUpdateSchema().load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    # Determine new price values
    new_cost = data.get("cost_price", float(product.cost_price) if product.cost_price is not None else None)
    new_sell = data.get("selling_price", float(product.selling_price) if product.selling_price is not None else None)

    price_changed = ("cost_price" in data or "selling_price" in data) and (
        new_cost != (float(product.cost_price) if product.cost_price is not None else None)
        or new_sell != (float(product.selling_price) if product.selling_price is not None else None)
    )

    # Apply updates
    for field in [
        "name",
        "category_id",
        "sku_code",
        "uom",
        "reorder_level",
        "supplier_name",
        "barcode",
        "image_url",
        "lead_time_days",
        "is_active",
    ]:
        if field in data:
            setattr(product, field, data[field])

    if "cost_price" in data:
        product.cost_price = data["cost_price"]
    if "selling_price" in data:
        product.selling_price = data["selling_price"]

    if price_changed:
        ProductService.log_price_history(product.product_id, new_cost, new_sell, user_id)

        # MARGIN_WARNING if cost > selling after update
        if new_cost is not None and new_sell is not None and new_cost > new_sell:
            ProductService.create_alert(
                store_id=store_id,
                alert_type="MARGIN_WARNING",
                priority="CRITICAL",
                product_id=product.product_id,
                message=(
                    f"Cost price ({new_cost}) exceeds selling price ({new_sell}) "
                    f"for product '{product.name}' (ID: {product.product_id})."
                ),
            )

    db.session.commit()
    from .schemas import ProductSchema
    return standard_json(data=ProductSchema().dump(product))


@inventory_bp.route("/products/<int:product_id>", methods=["DELETE"])
@require_auth
@require_role("owner")
def delete_product(product_id):
    store_id = g.current_user["store_id"]
    from ..models import Product
    product = db.session.query(Product).filter_by(product_id=product_id, store_id=store_id).first()
    if not product:
        return standard_json(success=False, message="Product not found", status_code=404)

    product.is_active = False
    db.session.commit()
    return standard_json(message="Product deactivated")


# ──────────────────────────────────────────────────────────────
# Stock Update
# ──────────────────────────────────────────────────────────────


@inventory_bp.route("/products/<int:product_id>/stock-update", methods=["POST"])
@inventory_bp.route("/products/<int:product_id>/stock", methods=["POST"])
@require_auth
def stock_update(product_id):
    store_id = g.current_user["store_id"]
    user_id = g.current_user["user_id"]

    product = db.session.query(Product).filter_by(product_id=product_id, store_id=store_id).first()
    if not product:
        return standard_json(success=False, message="Product not found", status_code=404)

    try:
        data = StockUpdateSchema().load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    qty_added = data["quantity_added"]
    purchase_price = data["purchase_price"]
    supplier = data.get("supplier_name") or product.supplier_name
    update_cost = data.get("update_cost_price", False)

    # Increment stock
    current = float(product.current_stock) if product.current_stock is not None else 0.0
    product.current_stock = current + qty_added

    # Optionally update supplier
    if data.get("supplier_name"):
        product.supplier_name = data["supplier_name"]

    # Create adjustment record
    adjusted_at = datetime.now(timezone.utc)
    if data.get("date"):
        with contextlib.suppress(ValueError):
            adjusted_at = datetime.strptime(data["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)

    adj = StockAdjustment(
        product_id=product_id,
        quantity_added=qty_added,
        purchase_price=purchase_price,
        adjusted_by=user_id,
        adjusted_at=adjusted_at,
        reason=f"Stock update from supplier: {supplier}" if supplier else "Stock update",
    )
    db.session.add(adj)

    # Cost price update if requested and price differs
    old_cost = float(product.cost_price) if product.cost_price is not None else None
    if update_cost and (old_cost is None or purchase_price != old_cost):
        product.cost_price = purchase_price
        ProductService.log_price_history(
            product_id,
            purchase_price,
            float(product.selling_price) if product.selling_price is not None else None,
            user_id,
        )

    db.session.commit()
    from .schemas import ProductSchema
    return standard_json(data=ProductSchema().dump(product))


# ──────────────────────────────────────────────────────────────
# Stock Audit
# ──────────────────────────────────────────────────────────────


@inventory_bp.route("/products/stock-audit", methods=["POST"])
@inventory_bp.route("/audit", methods=["POST"])
@require_auth
@require_role("owner")
def stock_audit():
    store_id = g.current_user["store_id"]
    user_id = g.current_user["user_id"]

    try:
        data = StockAuditSchema().load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    audit = StockAudit(
        store_id=store_id,
        audit_date=datetime.now(timezone.utc),
        conducted_by=user_id,
        status="completed",
        notes=data.get("notes"),
    )
    db.session.add(audit)
    db.session.flush()  # get audit_id

    result_items = []
    for item_data in data["items"]:
        pid = item_data["product_id"]
        actual_qty = item_data["actual_qty"]

        product = db.session.query(Product).filter_by(product_id=pid, store_id=store_id).first()
        if not product:
            db.session.rollback()
            return standard_json(success=False, message=f"Product {pid} not found", status_code=404)

        expected = float(product.current_stock) if product.current_stock is not None else 0.0
        discrepancy = actual_qty - expected

        audit_item = StockAuditItem(
            audit_id=audit.audit_id,
            product_id=pid,
            expected_stock=expected,
            actual_stock=actual_qty,
            discrepancy=discrepancy,
        )
        db.session.add(audit_item)

        # Update stock to actual
        product.current_stock = actual_qty

        result_items.append(
            {
                "product_id": pid,
                "expected_stock": expected,
                "actual_stock": actual_qty,
                "discrepancy": discrepancy,
            }
        )

    db.session.commit()
    return standard_json(
        data={
            "audit_id": audit.audit_id,
            "audit_date": audit.audit_date.isoformat(),
            "items": result_items,
        },
        status_code=201
    )


# ──────────────────────────────────────────────────────────────
# Price History
# ──────────────────────────────────────────────────────────────


@inventory_bp.route("/products/<int:product_id>/price-history", methods=["GET"])
@require_auth
def price_history(product_id):
    store_id = g.current_user["store_id"]

    from ..models import Product
    # Verify product belongs to store
    product = db.session.query(Product).filter_by(product_id=product_id, store_id=store_id).first()
    if not product:
        return standard_json(success=False, message="Product not found", status_code=404)

    records = (
        db.session.query(ProductPriceHistory)
        .filter_by(product_id=product_id)
        .order_by(ProductPriceHistory.changed_at.desc())
        .all()
    )

    data = [
        {
            "id": r.id,
            "cost_price": float(r.cost_price) if r.cost_price is not None else None,
            "selling_price": float(r.selling_price) if r.selling_price is not None else None,
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            "changed_by": r.changed_by,
        }
        for r in records
    ]
    return standard_json(data=data)


# ──────────────────────────────────────────────────────────────
# Alerts
# ──────────────────────────────────────────────────────────────


@inventory_bp.route("/alerts", methods=["GET"])
@require_auth
def get_alerts():
    store_id = g.current_user["store_id"]

    alerts = (
        db.session.query(Alert)
        .filter(
            Alert.store_id == store_id,
            Alert.resolved_at.is_(None),
            Alert.alert_type.in_(["LOW_STOCK", "SLOW_MOVING", "MARGIN_WARNING"]),
        )
        .order_by(Alert.created_at.desc())
        .all()
    )

    data = [
        {
            "alert_id": a.alert_id,
            "alert_type": a.alert_type,
            "priority": a.priority,
            "product_id": a.product_id,
            "message": a.message,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]
    return standard_json(data=data)


@inventory_bp.route("/alerts/<int:alert_id>", methods=["DELETE"])
@require_auth
def dismiss_alert(alert_id):
    from datetime import datetime, timezone

    store_id = g.current_user["store_id"]
    from ..models import Alert
    alert = db.session.query(Alert).filter(Alert.alert_id == alert_id, Alert.store_id == store_id).first()
    if not alert:
        return standard_json(success=False, message="Alert not found", status_code=404)
    alert.resolved_at = datetime.now(timezone.utc)
    db.session.commit()
    return standard_json(message="Alert dismissed")
