"""
Multi-Country Tax Engine API Routes
"""

from flask import g, request
from marshmallow import ValidationError

from .. import db
from ..auth.decorators import require_auth
from ..auth.utils import format_response
from ..models.expansion_models import CountryTaxConfig, StoreTaxRegistration
from . import tax_engine_bp
from .engine import get_tax_calculator


@tax_engine_bp.route("/tax/config", methods=["GET"])
@require_auth
def get_tax_config():
    store_id = g.current_user["store_id"]
    country_code = request.args.get("country_code", "IN")

    config = db.session.query(StoreTaxRegistration).filter_by(
        store_id=store_id, country_code=country_code
    ).first()

    if not config:
        return format_response(
            True, data={"tax_id": None, "registration_type": "STANDARD", "is_tax_enabled": False}
        ), 200

    return format_response(
        True,
        data={
            "tax_id": config.tax_id,
            "registration_type": config.registration_type,
            "state_province": config.state_province,
            "is_tax_enabled": config.is_tax_enabled,
        },
    ), 200


@tax_engine_bp.route("/tax/calculate", methods=["POST"])
@require_auth
def calculate_tax():
    """Preview tax calculation for a set of items."""
    try:
        data = request.json
        items = data.get("items", [])
        country_code = data.get("country_code", "IN")
    except Exception as e:
        return format_response(False, error={"code": "BAD_REQUEST", "message": str(e)}), 422

    store_id = g.current_user["store_id"]

    calculator = get_tax_calculator(store_id, country_code)
    try:
        result = calculator.calculate_tax(items)
        return format_response(
            True,
            data={
                "taxable_amount": float(result.taxable_amount),
                "tax_amount": float(result.tax_amount),
                "breakdown": {k: float(v) for k, v in result.breakdown.items()}
            }
        ), 200
    except Exception as e:
        return format_response(False, error={"code": "CALCULATION_ERROR", "message": str(e)}), 500


@tax_engine_bp.route("/tax/filing-summary", methods=["GET"])
@require_auth
def tax_summary():
    """Multi-country tax filing summary."""
    store_id = g.current_user["store_id"]
    period = request.args.get("period")
    country_code = request.args.get("country_code", "IN")

    if not period:
        return format_response(
            False, error={"code": "MISSING_PERIOD", "message": "Query parameter 'period' (YYYY-MM) is required"}
        ), 422

    from sqlalchemy import func

    from ..models.expansion_models import TaxTransaction

    # Build on-the-fly summary from tax_transactions
    rows = (
        db.session.query(
            func.sum(TaxTransaction.taxable_amount),
            func.sum(TaxTransaction.tax_amount),
            func.count(TaxTransaction.id),
        )
        .filter_by(store_id=store_id, country_code=country_code, period=period)
        .first()
    )

    return format_response(
        True,
        data={
            "period": period,
            "country_code": country_code,
            "total_taxable": float(rows[0] or 0),
            "total_tax": float(rows[1] or 0),
            "invoice_count": rows[2] or 0,
            "status": "PENDING",
            "compiled_at": None,
        },
    ), 200
