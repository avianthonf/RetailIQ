"""
Barcode & Receipt Printing Blueprint — Routes

All endpoints require JWT authentication via @require_auth.
Store scoping is applied by reading store_id from the JWT payload (g.current_user).
"""

import re
import uuid as uuid_module
from datetime import datetime, timezone

from flask import Blueprint, g, request

from .. import db
from ..auth.decorators import require_auth
from ..models import Barcode, PrintJob, Product, ReceiptTemplate, Transaction
from ..utils.responses import standard_json
from . import barcode_bp, receipts_bp
from .formatter import build_receipt_payload

# ---------------------------------------------------------------------------
# Barcode value validation: alphanumeric + hyphens, 4–64 chars
# ---------------------------------------------------------------------------
_BARCODE_RE = re.compile(r"^[A-Za-z0-9\-]{4,64}$")


def _validate_barcode_value(value: str) -> bool:
    return bool(_BARCODE_RE.match(value))


# ===========================================================================
# Receipt Template
# ===========================================================================


@receipts_bp.route("/template", methods=["GET"])
@require_auth
def get_receipt_template():
    """Return the store's receipt template, or sensible defaults if none set."""
    store_id = g.current_user["store_id"]

    template = db.session.query(ReceiptTemplate).filter_by(store_id=store_id).first()

    if template:
        data = {
            "id": template.id,
            "store_id": store_id,
            "header_text": template.header_text or "",
            "footer_text": template.footer_text or "",
            "show_gstin": template.show_gstin,
            "paper_width_mm": template.paper_width_mm,
            "updated_at": template.updated_at.isoformat() if template.updated_at else None,
        }
    else:
        # Sensible defaults
        data = {
            "id": None,
            "store_id": store_id,
            "header_text": "",
            "footer_text": "Thank you for shopping with us!",
            "show_gstin": True,
            "paper_width_mm": 80,
            "updated_at": None,
        }
    return standard_json(True, data=data), 200


@receipts_bp.route("/template", methods=["PUT"])
@require_auth
def upsert_receipt_template():
    """Create or update the store's receipt template."""
    store_id = g.current_user["store_id"]
    body = request.get_json(silent=True) or {}

    template = db.session.query(ReceiptTemplate).filter_by(store_id=store_id).first()
    if not template:
        template = ReceiptTemplate(store_id=store_id)
        db.session.add(template)

    template.header_text = body.get("header_text", template.header_text)
    template.footer_text = body.get("footer_text", template.footer_text)
    template.show_gstin = body.get("show_gstin", template.show_gstin)
    template.paper_width_mm = body.get("paper_width_mm", template.paper_width_mm)
    template.updated_at = datetime.now(timezone.utc)

    db.session.commit()

    data = {
        "id": template.id,
        "store_id": store_id,
        "header_text": template.header_text,
        "footer_text": template.footer_text,
        "show_gstin": template.show_gstin,
        "paper_width_mm": template.paper_width_mm,
        "updated_at": template.updated_at.isoformat(),
    }
    return standard_json(True, data=data), 200


# ===========================================================================
# Print Jobs
# ===========================================================================


@receipts_bp.route("/print", methods=["POST"])
@require_auth
def create_print_job():
    """
    Create a print job record.

    Body: { transaction_id (optional), printer_mac_address (optional) }
    Returns: 201 + { job_id }
    """
    store_id = g.current_user["store_id"]
    body = request.get_json(silent=True) or {}

    transaction_id = body.get("transaction_id")
    printer_mac = body.get("printer_mac_address")

    # Validate and coerce transaction_id if provided
    if transaction_id:
        try:
            transaction_id = uuid_module.UUID(str(transaction_id))
        except (ValueError, AttributeError):
            return standard_json(
                False, error={"code": "VALIDATION_ERROR", "message": "transaction_id must be a valid UUID"}
            ), 422

        txn = db.session.query(Transaction).filter_by(transaction_id=transaction_id, store_id=store_id).first()
        if not txn:
            return standard_json(False, error={"code": "NOT_FOUND", "message": "Transaction not found"}), 404

    # Build receipt payload if transaction_id provided
    receipt_payload = None
    if transaction_id:
        try:
            receipt_payload = build_receipt_payload(transaction_id, store_id, db.session)
        except ValueError as e:
            return standard_json(False, error={"code": "NOT_FOUND", "message": str(e)}), 404

    job = PrintJob(
        store_id=store_id,
        transaction_id=transaction_id,
        job_type="RECEIPT" if transaction_id else "BARCODE",
        status="PENDING",
        payload={
            "printer_mac_address": printer_mac,
            "receipt": receipt_payload,
        },
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(job)
    db.session.commit()

    return standard_json(True, data={"job_id": job.id}), 201


@receipts_bp.route("/print/<int:job_id>", methods=["GET"])
@require_auth
def get_print_job_status(job_id):
    """Poll the status of a print job."""
    store_id = g.current_user["store_id"]

    job = db.session.query(PrintJob).filter_by(id=job_id, store_id=store_id).first()
    if not job:
        return standard_json(False, error={"code": "NOT_FOUND", "message": "Print job not found"}), 404

    data = {
        "job_id": job.id,
        "store_id": job.store_id,
        "transaction_id": str(job.transaction_id) if job.transaction_id else None,
        "job_type": job.job_type,
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    return standard_json(True, data=data), 200


# ===========================================================================
# Barcodes
# ===========================================================================


@barcode_bp.route("/lookup", methods=["GET"])
@require_auth
def barcode_lookup():
    """
    Resolve a barcode value to product details.
    GET /api/v1/barcodes/lookup?value=<barcode_value>
    """
    store_id = g.current_user["store_id"]
    barcode_value = request.args.get("value", "").strip()

    if not barcode_value:
        return standard_json(
            False, error={"code": "VALIDATION_ERROR", "message": "Query param 'value' is required"}
        ), 422

    row = (
        db.session.query(Barcode, Product)
        .join(Product, Barcode.product_id == Product.product_id)
        .filter(Barcode.barcode_value == barcode_value, Barcode.store_id == store_id)
        .first()
    )

    if not row:
        return standard_json(False, error={"code": "NOT_FOUND", "message": "Barcode not found"}), 404

    barcode, product = row
    data = {
        "barcode_value": barcode.barcode_value,
        "barcode_type": barcode.barcode_type,
        "product_id": product.product_id,
        "product_name": product.name,
        "current_stock": float(product.current_stock) if product.current_stock is not None else 0.0,
        "price": float(product.selling_price) if product.selling_price is not None else 0.0,
    }
    return standard_json(True, data=data), 200


@barcode_bp.route("/register", methods=["POST"])
@require_auth
def register_barcode():
    """
    Register a barcode for a product.
    Body: { product_id, barcode_value, barcode_type (optional) }
    """
    store_id = g.current_user["store_id"]
    body = request.get_json(silent=True) or {}

    product_id = body.get("product_id")
    barcode_value = body.get("barcode_value", "")
    barcode_type = body.get("barcode_type", "EAN13")

    # Validate required fields
    if not product_id:
        return standard_json(False, error={"code": "VALIDATION_ERROR", "message": "product_id is required"}), 422

    if not barcode_value or not _validate_barcode_value(str(barcode_value)):
        return standard_json(
            False,
            error={
                "code": "VALIDATION_ERROR",
                "message": "barcode_value must be alphanumeric + hyphens, 4–64 characters",
            },
        ), 422

    # Verify product belongs to the store
    product = db.session.query(Product).filter_by(product_id=product_id, store_id=store_id).first()
    if not product:
        return standard_json(False, error={"code": "NOT_FOUND", "message": "Product not found in this store"}), 404

    # Check for duplicate barcode_value
    existing = db.session.query(Barcode).filter_by(barcode_value=barcode_value).first()
    if existing:
        return standard_json(False, error={"code": "CONFLICT", "message": "Barcode value already registered"}), 409

    barcode = Barcode(
        product_id=product_id,
        store_id=store_id,
        barcode_value=barcode_value,
        barcode_type=barcode_type,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(barcode)
    db.session.commit()

    return standard_json(
        True,
        data={
            "id": barcode.id,
            "product_id": barcode.product_id,
            "store_id": barcode.store_id,
            "barcode_value": barcode.barcode_value,
            "barcode_type": barcode.barcode_type,
            "created_at": barcode.created_at.isoformat() if barcode.created_at else None,
        },
    ), 201


@barcode_bp.route("/list", methods=["GET"])
@require_auth
def list_barcodes():
    """
    List all barcodes for a specific product.
    GET /api/v1/barcodes?product_id=<uuid>
    """
    store_id = g.current_user["store_id"]
    product_id = request.args.get("product_id")

    if not product_id:
        return standard_json(
            False, error={"code": "VALIDATION_ERROR", "message": "Query param 'product_id' is required"}
        ), 422

    # Verify product belongs to the store
    product = db.session.query(Product).filter_by(product_id=product_id, store_id=store_id).first()
    if not product:
        return standard_json(False, error={"code": "NOT_FOUND", "message": "Product not found in this store"}), 404

    barcodes = db.session.query(Barcode).filter_by(product_id=product_id, store_id=store_id).all()

    data = [
        {
            "id": b.id,
            "barcode_value": b.barcode_value,
            "barcode_type": b.barcode_type,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in barcodes
    ]
    return standard_json(True, data=data), 200
