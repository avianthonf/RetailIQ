"""
KYC API Routes
"""

from datetime import datetime, timezone

from flask import g, request

from .. import db
from ..auth.decorators import require_auth
from ..auth.utils import format_response
from ..models.expansion_models import KYCProvider, KYCRecord
from . import kyc_bp
from .engine import get_kyc_adapter, hash_id_number


@kyc_bp.route("/kyc/providers", methods=["GET"])
@require_auth
def list_kyc_providers():
    country_code = request.args.get("country_code", "IN")
    providers = db.session.query(KYCProvider).filter_by(
        country_code=country_code, is_active=True
    ).all()

    data = [
        {
            "code": p.code,
            "name": p.name,
            "type": p.verification_type,
            "id_label": p.id_label,
            "required_fields": p.required_fields,
            "is_mandatory": p.is_mandatory
        }
        for p in providers
    ]
    return format_response(True, data=data)


@kyc_bp.route("/kyc/verify", methods=["POST"])
@require_auth
def verify_kyc():
    try:
        data = request.json
        provider_code = data["provider_code"]
        id_number = data["id_number"]
        country_code = data.get("country_code", "IN")
    except KeyError as e:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": f"Missing field {e}"}), 400

    store_id = g.current_user["store_id"]
    user_id = g.current_user["user_id"]

    provider = db.session.query(KYCProvider).filter_by(code=provider_code).first()
    if not provider:
        return format_response(False, error={"code": "NOT_FOUND", "message": "KYC provider not found"}), 404

    try:
        adapter = get_kyc_adapter(provider_code, store_id)
        result = adapter.verify_identity(user_id=user_id, id_number=id_number, **data)

        # Record outcome
        record = KYCRecord(
            store_id=store_id,
            user_id=user_id,
            provider_id=provider.id,
            country_code=country_code,
            id_number_hash=hash_id_number(id_number),
            verification_status=result.get("status", "PENDING"),
            verification_data=result,
            verified_at=datetime.now(timezone.utc) if result.get("status") == "VERIFIED" else None
        )
        db.session.add(record)
        db.session.commit()

        return format_response(True, data={"status": record.verification_status, "details": result}), 200

    except ValueError as e:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return format_response(False, error={"code": "SERVER_ERROR", "message": str(e)}), 500


@kyc_bp.route("/kyc/status", methods=["GET"])
@require_auth
def kyc_status():
    store_id = g.current_user["store_id"]

    records = db.session.query(KYCRecord, KYCProvider.name).join(
        KYCProvider, KYCProvider.id == KYCRecord.provider_id
    ).filter(KYCRecord.store_id == store_id).all()

    data = [
        {
            "provider_name": provider_name,
            "status": record.verification_status,
            "country_code": record.country_code,
            "verified_at": record.verified_at.isoformat() if record.verified_at else None
        }
        for record, provider_name in records
    ]

    return format_response(True, data=data)
