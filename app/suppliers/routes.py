import io
import tempfile
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from flask import current_app, g, request, send_file

from app import db
from app.auth.decorators import require_auth
from app.auth.utils import format_response
from app.email import _send_raw
from app.models import GoodsReceiptNote, Product, PurchaseOrder, PurchaseOrderItem, Supplier, SupplierProduct
from app.suppliers.analytics import compute_avg_lead_time, compute_price_change_pct, compute_supplier_fill_rate
from app.utils.sanitize import sanitize_string

from . import po_bp, suppliers_bp


def _store_id() -> int:
    return g.current_user["store_id"]


def _user_id() -> int:
    return g.current_user["user_id"]


def _serialize_po_item(item):
    return {
        "line_item_id": str(item.id),
        "product_id": item.product_id,
        "ordered_qty": float(item.ordered_qty),
        "received_qty": float(item.received_qty) if item.received_qty is not None else 0.0,
        "unit_price": float(item.unit_price) if item.unit_price is not None else 0.0,
    }


def _serialize_po(po, items):
    return {
        "id": str(po.id),
        "supplier_id": str(po.supplier_id),
        "status": po.status,
        "expected_delivery_date": str(po.expected_delivery_date) if po.expected_delivery_date else None,
        "notes": po.notes,
        "created_at": str(po.created_at),
        "updated_at": str(po.updated_at) if po.updated_at else str(po.created_at),
        "items": [_serialize_po_item(item) for item in items],
    }


def _load_po_for_store(po_id, store_id):
    po = db.session.query(PurchaseOrder).filter_by(id=po_id, store_id=store_id).first()
    if not po:
        return None, None
    items = db.session.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
    return po, items


def _build_po_pdf_bytes(po, items, supplier):
    lines = [
        f"Purchase Order #{po.id}",
        f"Supplier: {supplier.name if supplier else po.supplier_id}",
        f"Status: {po.status}",
        f"Expected Delivery: {po.expected_delivery_date or 'N/A'}",
        "",
        "Items:",
    ]
    total = 0.0
    for item in items:
        line_total = float(item.ordered_qty) * float(item.unit_price)
        total += line_total
        lines.append(
            f"- Product {item.product_id}: {float(item.ordered_qty):.2f} x {float(item.unit_price):.2f} = {line_total:.2f}"
        )
    lines.extend(["", f"Total: INR {total:.2f}", "", po.notes or ""])

    html = "<html><body><pre style='font-family: monospace'>" + "\n".join(lines) + "</pre></body></html>"
    try:
        from weasyprint import HTML

        return HTML(string=html).write_pdf()
    except Exception:
        pdf_like = "%PDF-1.4\n" + "\n".join(lines) + "\n%%EOF"
        return pdf_like.encode("utf-8")


# ── 1. SUPPLIER CRUD ──────────────────────────────────────────────────────────


@suppliers_bp.route("", methods=["GET"])
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


@suppliers_bp.route("", methods=["POST"])
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


@suppliers_bp.route("/<uuid:supplier_id>", methods=["GET"])
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


@suppliers_bp.route("/<uuid:supplier_id>", methods=["PUT"])
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


@suppliers_bp.route("/<uuid:supplier_id>", methods=["DELETE"])
@require_auth
def delete_supplier(supplier_id):
    sid = _store_id()
    s = db.session.query(Supplier).filter_by(id=supplier_id, store_id=sid).first()
    if not s:
        return format_response(error="Supplier not found", status_code=404)

    s.is_active = False
    db.session.commit()
    return format_response(data={"id": str(s.id)}, status_code=200)


@suppliers_bp.route("/<uuid:supplier_id>/products", methods=["POST"])
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


@suppliers_bp.route("/<uuid:supplier_id>/products/<int:product_id>", methods=["PUT", "PATCH"])
@require_auth
def update_supplier_product_link(supplier_id, product_id):
    sid = _store_id()
    supplier = db.session.query(Supplier).filter_by(id=supplier_id, store_id=sid).first()
    if not supplier:
        return format_response(error="Supplier not found", status_code=404)

    supplier_product = (
        db.session.query(SupplierProduct).filter_by(supplier_id=supplier_id, product_id=product_id).first()
    )
    if not supplier_product:
        return format_response(error="Supplier product link not found", status_code=404)

    body = request.get_json() or {}
    if "quoted_price" in body:
        supplier_product.quoted_price = body["quoted_price"]
    if "lead_time_days" in body:
        supplier_product.lead_time_days = body["lead_time_days"]
    if "is_preferred_supplier" in body:
        supplier_product.is_preferred_supplier = body["is_preferred_supplier"]

    db.session.commit()
    return format_response(data={"id": str(supplier_product.id)}, status_code=200)


@suppliers_bp.route("/<uuid:supplier_id>/products/<int:product_id>", methods=["DELETE"])
@require_auth
def delete_supplier_product_link(supplier_id, product_id):
    sid = _store_id()
    supplier = db.session.query(Supplier).filter_by(id=supplier_id, store_id=sid).first()
    if not supplier:
        return format_response(error="Supplier not found", status_code=404)

    supplier_product = (
        db.session.query(SupplierProduct).filter_by(supplier_id=supplier_id, product_id=product_id).first()
    )
    if not supplier_product:
        return format_response(error="Supplier product link not found", status_code=404)

    db.session.delete(supplier_product)
    db.session.commit()
    return format_response(data={"product_id": product_id, "deleted": True}, status_code=200)


# ── 2. PURCHASE ORDERS ────────────────────────────────────────────────────────


@po_bp.route("", methods=["GET"])
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


@po_bp.route("", methods=["POST"])
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


@po_bp.route("/<uuid:po_id>/send", methods=["PUT", "POST"])
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


@po_bp.route("/<uuid:po_id>", methods=["GET"])
@require_auth
def get_purchase_order(po_id):
    sid = _store_id()
    po = db.session.query(PurchaseOrder).filter_by(id=po_id, store_id=sid).first()
    if not po:
        return format_response(error="PO not found", status_code=404)

    items = db.session.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
    return format_response(data=_serialize_po(po, items)), 200


@po_bp.route("/<uuid:po_id>", methods=["PUT", "PATCH"])
@require_auth
def update_purchase_order(po_id):
    sid = _store_id()
    body = request.get_json() or {}
    po, items = _load_po_for_store(po_id, sid)
    if not po:
        return format_response(error="PO not found", status_code=404)

    if po.status != "DRAFT":
        return format_response(error="Only DRAFT POs can be updated", status_code=422)

    if "expected_delivery_date" in body:
        try:
            po.expected_delivery_date = (
                date.fromisoformat(body["expected_delivery_date"]) if body["expected_delivery_date"] else None
            )
        except Exception:
            return format_response(error="invalid date format", status_code=422)
    if "notes" in body:
        po.notes = sanitize_string(body.get("notes"), 500)

    if "items" in body:
        db.session.query(PurchaseOrderItem).filter_by(po_id=po.id).delete()
        for item in body["items"]:
            db.session.add(
                PurchaseOrderItem(
                    po_id=po.id,
                    product_id=item["product_id"],
                    ordered_qty=item["ordered_qty"],
                    unit_price=item["unit_price"],
                )
            )

    db.session.commit()
    po, items = _load_po_for_store(po_id, sid)
    return format_response(data=_serialize_po(po, items)), 200


@po_bp.route("/<uuid:po_id>/receive", methods=["POST"])
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

    if po.status not in ("SENT", "CONFIRMED"):
        return format_response(error="Can only receive SENT or CONFIRMED POs", status_code=422)

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


@po_bp.route("/<uuid:po_id>/confirm", methods=["POST"])
@require_auth
def confirm_purchase_order(po_id):
    sid = _store_id()
    po = db.session.query(PurchaseOrder).filter_by(id=po_id, store_id=sid).first()
    if not po:
        return format_response(error="PO not found", status_code=404)

    if po.status != "SENT":
        return format_response(error="Only SENT POs can be confirmed", status_code=422)

    po.status = "CONFIRMED"
    db.session.commit()
    return format_response(data={"id": str(po.id), "status": po.status}, status_code=200)


@po_bp.route("/<uuid:po_id>/cancel", methods=["PUT"])
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


@po_bp.route("/<uuid:po_id>/pdf", methods=["GET"])
@require_auth
def generate_purchase_order_pdf(po_id):
    sid = _store_id()
    po, items = _load_po_for_store(po_id, sid)
    if not po:
        return format_response(error="PO not found", status_code=404)

    supplier = db.session.get(Supplier, po.supplier_id)
    pdf_bytes = _build_po_pdf_bytes(po, items, supplier)

    export_dir = current_app.config.get("EXPORT_DIR") or tempfile.gettempdir()
    pdf_path = tempfile.NamedTemporaryFile(prefix=f"po-{po.id}-", suffix=".pdf", delete=False, dir=export_dir).name
    with open(pdf_path, "wb") as handle:
        handle.write(pdf_bytes)

    return format_response(
        data={
            "job_id": f"po-pdf-{po.id}",
            "url": f"/api/v1/purchase-orders/{po.id}/pdf/download",
            "path": pdf_path,
        }
    )


@po_bp.route("/<uuid:po_id>/pdf/download", methods=["GET"])
@require_auth
def download_purchase_order_pdf(po_id):
    sid = _store_id()
    po, items = _load_po_for_store(po_id, sid)
    if not po:
        return format_response(error="PO not found", status_code=404)

    supplier = db.session.get(Supplier, po.supplier_id)
    pdf_bytes = _build_po_pdf_bytes(po, items, supplier)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"purchase-order-{po.id}.pdf",
    )


@po_bp.route("/<uuid:po_id>/email", methods=["POST"])
@require_auth
def email_purchase_order(po_id):
    sid = _store_id()
    po, items = _load_po_for_store(po_id, sid)
    if not po:
        return format_response(error="PO not found", status_code=404)

    body = request.get_json() or {}
    to_email = body.get("email")
    if not to_email:
        return format_response(error="email is required", status_code=422)

    supplier = db.session.get(Supplier, po.supplier_id)
    total = sum(float(item.ordered_qty) * float(item.unit_price) for item in items)
    html = f"""
        <h2>Purchase Order {po.id}</h2>
        <p>Supplier: {supplier.name if supplier else po.supplier_id}</p>
        <p>Status: {po.status}</p>
        <p>Total: INR {total:.2f}</p>
        <p>Download PDF: /api/v1/purchase-orders/{po.id}/pdf/download</p>
    """

    sent = _send_raw(to_email, f"RetailIQ Purchase Order {po.id}", html)
    if not sent:
        return format_response(error="Failed to send email", status_code=500)

    return format_response(data={"message": "Purchase order emailed successfully"}, status_code=200)
