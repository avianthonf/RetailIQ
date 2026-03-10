"""
Payment API Routes
"""

from flask import g, request

from .. import db
from ..auth.decorators import require_auth
from ..auth.utils import format_response
from ..models import Transaction
from ..models.expansion_models import PaymentProvider, PaymentRecord, StorePaymentMethod
from . import payments_bp
from .engine import get_payment_adapter


@payments_bp.route("/payments/providers", methods=["GET"])
@require_auth
def list_providers():
    country_code = request.args.get("country_code", "IN")
    providers = db.session.query(PaymentProvider).filter_by(
        country_code=country_code, is_active=True
    ).all()

    data = [
        {
            "code": p.code,
            "name": p.name,
            "type": p.provider_type,
            "supported_methods": p.supported_methods
        }
        for p in providers
    ]

    return format_response(True, data=data)


@payments_bp.route("/payments/intent", methods=["POST"])
@require_auth
def create_intent():
    try:
        data = request.json
        transaction_id = data["transaction_id"]
        provider_code = data["provider_code"]
    except KeyError as e:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": f"Missing field {e}"}), 400

    store_id = g.current_user["store_id"]

    txn = db.session.query(Transaction).filter_by(
        transaction_id=transaction_id, store_id=store_id
    ).first()

    if not txn:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Transaction not found"}), 404

    try:
        adapter = get_payment_adapter(provider_code, store_id)

        # In a real app we'd fetch the configured currency for the store
        intent_response = adapter.create_payment_intent(
            amount=float(txn.total_amount),
            currency="USD",
            txn_id=str(txn.transaction_id),
            phone_number=data.get("phone_number")
        )

        # Record the attempt
        provider = db.session.query(PaymentProvider).filter_by(code=provider_code).first()
        if provider:
            record = PaymentRecord(
                transaction_id=txn.transaction_id,
                store_id=store_id,
                provider_id=provider.id,
                payment_method=data.get("method", "DEFAULT"),
                amount=txn.total_amount,
                currency_code="USD",
                status="PENDING"
            )
            db.session.add(record)
            db.session.commit()

        return format_response(True, data=intent_response), 200

    except ValueError as e:
        return format_response(False, error={"code": "ADAPTER_ERROR", "message": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return format_response(False, error={"code": "SERVER_ERROR", "message": str(e)}), 500
