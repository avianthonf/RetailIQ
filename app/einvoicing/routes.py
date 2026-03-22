"""
Multi-Country E-Invoicing API Routes
"""

from datetime import datetime, timezone

from flask import g, request

from .. import db
from ..auth.decorators import require_auth
from ..auth.utils import format_response
from ..models import Transaction
from ..models.expansion_models import EInvoice
from . import einvoicing_bp
from .engine import get_einvoice_adapter


def _resolved_qr_code_url(invoice: EInvoice) -> str | None:
    if invoice.qr_code_data:
        return invoice.qr_code_data

    try:
        adapter = get_einvoice_adapter(invoice.country_code, invoice.store_id)
        return adapter.build_qr_code_url(
            {
                "invoice_number": invoice.invoice_number,
                "transaction_id": str(invoice.transaction_id),
                "format": invoice.invoice_format,
            },
            invoice.authority_ref or invoice.invoice_number or str(invoice.id),
        )
    except Exception:
        return None


@einvoicing_bp.route("/generate", methods=["POST"])
@require_auth
def generate_einvoice():
    """Generate and submit an e-invoice for a completed transaction."""
    try:
        data = request.json
        transaction_id = data["transaction_id"]
        country_code = data.get("country_code", "IN").upper()
    except KeyError as e:
        return format_response(
            success=False, status_code=400, error={"code": "VALIDATION_ERROR", "message": f"Missing field {e}"}
        )
    store_id = g.current_user["store_id"]

    txn = None
    try:
        import uuid

        parsed_txn_id = uuid.UUID(transaction_id)
        txn = db.session.query(Transaction).filter_by(transaction_id=parsed_txn_id, store_id=store_id).first()
    except ValueError:
        pass  # Invalid UUID

    if not txn:
        return format_response(
            success=False, status_code=404, error={"code": "NOT_FOUND", "message": "Transaction not found"}
        )
    # Check if invoice already exists
    existing = db.session.query(EInvoice).filter_by(transaction_id=parsed_txn_id, country_code=country_code).first()

    if existing and existing.status in ("SUBMITTED", "ACCEPTED"):
        return format_response(
            True,
            data={
                "invoice_id": str(existing.id),
                "transaction_id": str(existing.transaction_id),
                "country_code": existing.country_code,
                "status": existing.status,
                "invoice_number": existing.invoice_number,
                "authority_ref": existing.authority_ref,
                "qr_code_url": _resolved_qr_code_url(existing),
                "submitted_at": existing.submitted_at.isoformat() if existing.submitted_at else None,
                "invoice_format": existing.invoice_format,
            },
        )
    try:
        adapter = get_einvoice_adapter(country_code, store_id)

        # Step 1: Generate Payload
        payload = adapter.generate_invoice(txn)

        # Create record
        invoice = EInvoice(
            transaction_id=txn.transaction_id,
            store_id=store_id,
            country_code=country_code,
            invoice_format=payload.get("format", "STANDARD"),
            xml_payload=payload.get("xml_payload"),
            invoice_number=payload.get("invoice_number")
            or payload.get("chave_acesso")
            or payload.get("irn")
            or payload.get("uuid"),
            digital_signature=payload.get("digital_signature"),
            status="DRAFT",
        )
        db.session.add(invoice)
        db.session.commit()

        # Step 2: Submit to Authority
        response = adapter.submit_invoice(payload)

        # Update record
        invoice.status = response.get("status", "SUBMITTED")
        invoice.authority_ref = (
            response.get("authority_ref")
            or response.get("protocol")
            or response.get("sat_seal")
            or response.get("faktur_pajak_no")
        )
        invoice.qr_code_data = response.get("qr_code_url")
        invoice.submission_response = response
        invoice.submitted_at = datetime.now(timezone.utc)

        db.session.commit()

        return format_response(
            True,
            data={
                "invoice_id": str(invoice.id),
                "transaction_id": str(invoice.transaction_id),
                "country_code": invoice.country_code,
                "status": invoice.status,
                "invoice_number": invoice.invoice_number,
                "authority_ref": invoice.authority_ref,
                "qr_code_url": _resolved_qr_code_url(invoice),
                "submitted_at": invoice.submitted_at.isoformat() if invoice.submitted_at else None,
                "invoice_format": invoice.invoice_format,
            },
        )
    except ValueError as e:
        return format_response(success=False, error={"code": "ADAPTER_ERROR", "message": str(e)})
    except Exception as e:
        db.session.rollback()
        return format_response(success=False, status_code=500, error={"code": "SERVER_ERROR", "message": str(e)})


@einvoicing_bp.route("/status/<invoice_id>", methods=["GET"])
@require_auth
def get_einvoice_status(invoice_id):
    store_id = g.current_user["store_id"]

    try:
        import uuid

        parsed_inv_id = uuid.UUID(invoice_id)
        invoice = db.session.query(EInvoice).filter_by(id=parsed_inv_id, store_id=store_id).first()
    except ValueError:
        invoice = None

    if not invoice:
        return format_response(
            success=False, status_code=404, error={"code": "NOT_FOUND", "message": "E-Invoice not found"}
        )
    return format_response(
        True,
        data={
            "invoice_id": str(invoice.id),
            "transaction_id": str(invoice.transaction_id),
            "country_code": invoice.country_code,
            "invoice_format": invoice.invoice_format,
            "invoice_number": invoice.invoice_number,
            "authority_ref": invoice.authority_ref,
            "status": invoice.status,
            "submitted_at": invoice.submitted_at.isoformat() if invoice.submitted_at else None,
            "qr_code_url": _resolved_qr_code_url(invoice),
        },
    )
