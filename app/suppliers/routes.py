from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from flask import Blueprint, g, jsonify, request

from app import db
from app.auth.decorators import require_auth
from app.auth.utils import format_response
from app.models import GoodsReceiptNote, Product, PurchaseOrder, PurchaseOrderItem, Supplier, SupplierProduct
from app.suppliers.analytics import compute_avg_lead_time, compute_price_change_pct, compute_supplier_fill_rate
from app.utils.sanitize import sanitize_string

suppliers_bp = Blueprint("suppliers", __name__)


def _store_id() -> int:
    return g.current_user["store_id"]


def _user_id() -> int:
    return g.current_user["user_id"]


# ── 1. SUPPLIER CRUD ──────────────────────────────────────────────────────────


@suppliers_bp.route("/suppliers", methods=["GET"])
@require_auth
def list_suppliers():
    """GET /api/v1/suppliers — list all active suppliers for store."""
    sid = _store_id()
    suppliers = db.session.query(Supplier).filter_by(store_id=sid, is_active=True).all()

    data = []
    for s in suppliers:
        fill_rate = compute_supplier_fill_rate(s.id, sid, 90, db)
        avg_lead_time = compute_avg_lead_time(s.id, sid, db)

        # compute price_change_6m_pct inline
        # Average over all their products
        sps = db.session.query(SupplierProduct).filter_by(supplier_id=s.id).all()
        pcs = []
        for sp in sps:
            pc = compute_price_change_pct(s.id, sp.product_id, 6, db)
            if pc is not None:
                pcs.append(pc)
        price_change_6m = sum(pcs) / len(pcs) if pcs else None

        data.append(
            {
                "id": str(s.id),
                "name": s.name,
                "contact_name": s.contact_name,
                "email": s.email,
                "phone": s.phone,
                "payment_terms_days": s.payment_terms_days,
                "avg_lead_time_days": round(avg_lead_time, 1) if avg_lead_time else None,
                "fill_rate_90d": round(fill_rate * 100, 1),
                "price_change_6m_pct": round(price_change_6m, 2) if price_change_6m is not None else None,
            }
        )

    return format_response(data=data)


@suppliers_bp.route("/suppliers", methods=["POST"])
@require_auth
def create_supplier():
    sid = _store_id()
    body = request.get_json() or {}

    if not body.get("name"):
        return format_response(error="name is required", status_code=422)

    s = Supplier(
        store_id=sid,
        name=sanitize_string(body["name"], 128),
        contact_name=sanitize_string(body.get("contact_name"), 128),
        phone=body.get("phone"),
        email=body.get("email"),
        address=sanitize_string(body.get("address"), 512),
        payment_terms_days=body.get("payment_terms_days", 30),
    )
    db.session.add(s)
    db.session.commit()

    return format_response(data={"id": str(s.id)}, status_code=201)


@suppliers_bp.route("/suppliers/<uuid:supplier_id>", methods=["GET"])
@require_auth
def get_supplier(supplier_id):
    sid = _store_id()
    s = db.session.query(Supplier).filter_by(id=supplier_id, store_id=sid).first()
    if not s:
        return format_response(error="Supplier not found", status_code=404)

    # get sourced products
    sps_rows = (
        db.session.query(SupplierProduct, Product)
        .join(Product)
        .filter(SupplierProduct.supplier_id == supplier_id)
        .all()
    )
    sps = []
    for sp, p in sps_rows:
        sps.append(
            {
                "product_id": p.product_id,
                "name": p.name,
                "quoted_price": float(sp.quoted_price or 0),
                "lead_time_days": sp.lead_time_days,
            }
        )

    # last 90 days of PO history
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    pos = (
        db.session.query(PurchaseOrder)
        .filter(
            PurchaseOrder.supplier_id == supplier_id, PurchaseOrder.store_id == sid, PurchaseOrder.created_at >= cutoff
        )
        .order_by(PurchaseOrder.created_at.desc())
        .all()
    )

    po_history = [
        {
            "id": str(po.id),
            "status": po.status,
            "expected_delivery_date": str(po.expected_delivery_date) if po.expected_delivery_date else None,
            "created_at": str(po.created_at),
        }
        for po in pos
    ]

    fill_rate = compute_supplier_fill_rate(s.id, sid, 90, db)
    avg_lead_time = compute_avg_lead_time(s.id, sid, db)

    profile = {
        "id": str(s.id),
        "name": s.name,
        "contact": {"name": s.contact_name, "phone": s.phone, "email": s.email, "address": s.address},
        "payment_terms_days": s.payment_terms_days,
        "is_active": s.is_active,
        "analytics": {
            "avg_lead_time_days": round(avg_lead_time, 1) if avg_lead_time else None,
            "fill_rate_90d": round(fill_rate * 100, 1),
        },
        "sourced_products": sps,
        "recent_purchase_orders": po_history,
    }

    return format_response(data=profile)


@suppliers_bp.route("/suppliers/<uuid:supplier_id>", methods=["PUT"])
@require_auth
def update_supplier(supplier_id):
    sid = _store_id()
    s = db.session.query(Supplier).filter_by(id=supplier_id, store_id=sid).first()
    if not s:
        return format_response(error="Supplier not found", status_code=404)

    body = request.get_json() or {}
    if "name" in body:
        s.name = sanitize_string(body["name"], 128)
    if "contact_name" in body:
        s.contact_name = sanitize_string(body["contact_name"], 128)
    if "phone" in body:
        s.phone = body["phone"]
    if "email" in body:
        s.email = body["email"]
    if "address" in body:
        s.address = sanitize_string(body["address"], 512)
    if "payment_terms_days" in body:
        s.payment_terms_days = body["payment_terms_days"]
    if "is_active" in body:
        s.is_active = body["is_active"]

    db.session.commit()
    return format_response(data={"id": str(s.id)}, status_code=200)


@suppliers_bp.route("/suppliers/<uuid:supplier_id>", methods=["DELETE"])
@require_auth
def delete_supplier(supplier_id):
    sid = _store_id()
    s = db.session.query(Supplier).filter_by(id=supplier_id, store_id=sid).first()
    if not s:
        return format_response(error="Supplier not found", status_code=404)

    s.is_active = False
    db.session.commit()
    return format_response(data={"id": str(s.id)}, status_code=200)


@suppliers_bp.route("/suppliers/<uuid:supplier_id>/products", methods=["POST"])
@require_auth
def link_supplier_product(supplier_id):
    sid = _store_id()
    s = db.session.query(Supplier).filter_by(id=supplier_id, store_id=sid).first()
    if not s:
        return format_response(error="Supplier not found", status_code=404)

    body = request.get_json() or {}
    if not body.get("product_id") or body.get("quoted_price") is None:
        return format_response(error="product_id and quoted_price required", status_code=422)

    sp = SupplierProduct(
        supplier_id=supplier_id,
        product_id=body["product_id"],
        quoted_price=body["quoted_price"],
        lead_time_days=body.get("lead_time_days", 3),
        is_preferred_supplier=body.get("is_preferred_supplier", False),
    )
    db.session.add(sp)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return format_response(error=str(e), status_code=422)

    return format_response(data={"id": str(sp.id)}, status_code=201)


# ── 2. PURCHASE ORDERS ────────────────────────────────────────────────────────


@suppliers_bp.route("/purchase-orders", methods=["GET"])
@require_auth
def list_purchase_orders():
    sid = _store_id()
    status_filter = request.args.get("status")

    q = db.session.query(PurchaseOrder).filter_by(store_id=sid)
    if status_filter:
        q = q.filter_by(status=status_filter)

    pos = q.order_by(PurchaseOrder.created_at.desc()).all()

    data = [
        {
            "id": str(po.id),
            "supplier_id": str(po.supplier_id),
            "status": po.status,
            "expected_delivery_date": str(po.expected_delivery_date) if po.expected_delivery_date else None,
            "created_at": str(po.created_at),
        }
        for po in pos
    ]

    return format_response(data=data)


@suppliers_bp.route("/purchase-orders", methods=["POST"])
@require_auth
def create_purchase_order():
    sid = _store_id()
    uid = _user_id()
    body = request.get_json() or {}

    if not body.get("supplier_id") or not body.get("items"):
        return format_response(error="supplier_id and items required", status_code=422)

    try:
        supplier_id = UUID(body["supplier_id"])
    except Exception:
        return format_response(error="Invalid supplier_id", status_code=422)

    edd = body.get("expected_delivery_date")
    if edd:
        try:
            edd = date.fromisoformat(edd)
        except Exception:
            return format_response(error="invalid date format", status_code=422)

    po = PurchaseOrder(
        store_id=sid,
        supplier_id=supplier_id,
        status="DRAFT",
        expected_delivery_date=edd,
        notes=sanitize_string(body.get("notes"), 500),
        created_by=uid,
    )
    db.session.add(po)
    db.session.flush()  # get po.id

    for item in body["items"]:
        poi = PurchaseOrderItem(
            po_id=po.id, product_id=item["product_id"], ordered_qty=item["ordered_qty"], unit_price=item["unit_price"]
        )
        db.session.add(poi)

    db.session.commit()
    return format_response(data={"id": str(po.id)}, status_code=201)


@suppliers_bp.route("/purchase-orders/<uuid:po_id>/send", methods=["PUT", "POST"])
@require_auth
def send_purchase_order(po_id):
    sid = _store_id()
    po = db.session.query(PurchaseOrder).filter_by(id=po_id, store_id=sid).first()
    if not po:
        return format_response(error="PO not found", status_code=404)

    if po.status != "DRAFT":
        return format_response(error="Only DRAFT POs can be sent", status_code=422)

    items = db.session.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
    if not items:
        return format_response(error="Cannot send empty PO", status_code=422)

    po.status = "SENT"
    db.session.commit()
    return format_response(data={"id": str(po.id)}, status_code=200)


@suppliers_bp.route("/purchase-orders/<uuid:po_id>", methods=["GET"])
@require_auth
def get_purchase_order(po_id):
    sid = _store_id()
    po = db.session.query(PurchaseOrder).filter_by(id=po_id, store_id=sid).first()
    if not po:
        return format_response(error="PO not found", status_code=404)

    items = db.session.query(PurchaseOrderItem).filter_by(po_id=po.id).all()

    data = {
        "id": str(po.id),
        "supplier_id": str(po.supplier_id),
        "status": po.status,
        "expected_delivery_date": str(po.expected_delivery_date) if po.expected_delivery_date else None,
        "notes": po.notes,
        "created_at": str(po.created_at),
        "items": [
            {
                "product_id": i.product_id,
                "ordered_qty": float(i.ordered_qty),
                "received_qty": float(i.received_qty) if i.received_qty is not None else 0.0,
                "unit_price": float(i.unit_price) if i.unit_price is not None else 0.0,
            }
            for i in items
        ],
    }

    return format_response(data=data), 200


@suppliers_bp.route("/purchase-orders/<uuid:po_id>/receive", methods=["POST"])
@require_auth
def receive_purchase_order(po_id):
    sid = _store_id()
    uid = _user_id()
    body = request.get_json() or {}

    if not body.get("items"):
        return format_response(error="items required", status_code=422)

    po = db.session.query(PurchaseOrder).filter_by(id=po_id, store_id=sid).first()
    if not po:
        return format_response(error="PO not found", status_code=404)

    if po.status != "SENT":
        return format_response(error="Can only receive SENT POs", status_code=422)

    try:
        with db.session.begin_nested():
            grn = GoodsReceiptNote(po_id=po.id, store_id=sid, received_by=uid, notes=body.get("notes"))
            db.session.add(grn)

            # process items
            for req_item in body["items"]:
                poi = (
                    db.session.query(PurchaseOrderItem)
                    .filter_by(po_id=po.id, product_id=req_item["product_id"])
                    .with_for_update()
                    .first()
                )
                if not poi:
                    raise ValueError(f"Product {req_item['product_id']} not in PO")

                rcvd = float(req_item["received_qty"])
                poi.received_qty = float(poi.received_qty or 0) + rcvd

                # update stock
                product = (
                    db.session.query(Product)
                    .filter_by(product_id=req_item["product_id"], store_id=sid)
                    .with_for_update()
                    .first()
                )
                if not product:
                    raise ValueError(f"Product {req_item['product_id']} not found")

                product.current_stock = float(product.current_stock or 0) + rcvd

            # check if fully fulfilled
            all_items = db.session.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
            fully_received = all(float(i.received_qty or 0) >= float(i.ordered_qty) for i in all_items)
            if fully_received:
                po.status = "FULFILLED"

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return format_response(error=str(e), status_code=422)

    return format_response(data={"id": str(po.id), "status": po.status}, status_code=200)


@suppliers_bp.route("/purchase-orders/<uuid:po_id>/cancel", methods=["PUT"])
@require_auth
def cancel_purchase_order(po_id):
    sid = _store_id()
    po = db.session.query(PurchaseOrder).filter_by(id=po_id, store_id=sid).first()
    if not po:
        return format_response(error="PO not found", status_code=404)

    if po.status not in ("DRAFT", "SENT"):
        return format_response(error="Cannot cancel this PO", status_code=422)

    po.status = "CANCELLED"
    db.session.commit()
    return format_response(data={"id": str(po.id)}, status_code=200)
