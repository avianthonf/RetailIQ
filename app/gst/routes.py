import contextlib
from datetime import datetime, timezone
from decimal import Decimal

from flask import g, request
from marshmallow import ValidationError
from sqlalchemy import func, or_

from .. import db
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import GSTFilingPeriod, GSTHSNMapping, GSTTransaction, HSNMaster, StoreGSTConfig
from . import gst_bp
from .schemas import GSTConfigUpsertSchema
from .utils import validate_gstin

# ── GST Config ──────────────────────────────────────────────────────


@gst_bp.route("/config", methods=["GET"])
@require_auth
def get_gst_config():
    store_id = g.current_user["store_id"]
    config = db.session.query(StoreGSTConfig).filter_by(store_id=store_id).first()
    if not config:
        return format_response(
            True, data={"gstin": None, "registration_type": "REGULAR", "state_code": None, "is_gst_enabled": False}
        )
    return format_response(
        True,
        data={
            "gstin": config.gstin,
            "registration_type": config.registration_type,
            "state_code": config.state_code,
            "is_gst_enabled": config.is_gst_enabled,
        },
    )


@gst_bp.route("/config", methods=["PUT"])
@require_auth
@require_role("owner")
def update_gst_config():
    try:
        data = GSTConfigUpsertSchema().load(request.json)
    except ValidationError as err:
        return format_response(
            success=False, error={"code": "VALIDATION_ERROR", "message": err.messages}, status_code=400
        )

    store_id = g.current_user["store_id"]

    # Validate GSTIN if provided
    gstin = data.get("gstin")
    if gstin and not validate_gstin(gstin):
        return format_response(False, error={"code": "INVALID_GSTIN", "message": "Invalid GSTIN format or checksum"})

    config = db.session.query(StoreGSTConfig).filter_by(store_id=store_id).first()
    if not config:
        config = StoreGSTConfig(store_id=store_id)
        db.session.add(config)

    for key in ("gstin", "registration_type", "state_code", "is_gst_enabled"):
        if key in data:
            setattr(config, key, data[key])

    db.session.commit()
    return format_response(
        True,
        data={
            "gstin": config.gstin,
            "registration_type": config.registration_type,
            "state_code": config.state_code,
            "is_gst_enabled": config.is_gst_enabled,
        },
    )


# ── HSN Search ──────────────────────────────────────────────────────


@gst_bp.route("/hsn-search", methods=["GET"])
@require_auth
def hsn_search():
    q = request.args.get("q", "").strip()
    if not q:
        return format_response(False, error={"code": "MISSING_QUERY", "message": "Query parameter 'q' is required"})

    results = (
        db.session.query(HSNMaster)
        .filter(or_(HSNMaster.hsn_code.like(f"{q}%"), HSNMaster.description.ilike(f"%{q}%")))
        .limit(10)
        .all()
    )

    data = [
        {
            "hsn_code": r.hsn_code,
            "description": r.description,
            "default_gst_rate": float(r.default_gst_rate) if r.default_gst_rate is not None else None,
        }
        for r in results
    ]

    return format_response(success=True, data=data, status_code=200)


# ── GST Summary ─────────────────────────────────────────────────────


@gst_bp.route("/summary", methods=["GET"])
@require_auth
def gst_summary():
    store_id = g.current_user["store_id"]
    period = request.args.get("period")
    if not period:
        return format_response(
            False,
            error={
                "code": "MISSING_PERIOD",
                "message": "Query parameter 'period' (YYYY-MM, status_code=400) is required",
            },
        )

    filing = db.session.query(GSTFilingPeriod).filter_by(store_id=store_id, period=period).first()
    if filing:
        return format_response(
            True,
            data={
                "period": filing.period,
                "total_taxable": float(filing.total_taxable) if filing.total_taxable else 0,
                "total_cgst": float(filing.total_cgst) if filing.total_cgst else 0,
                "total_sgst": float(filing.total_sgst) if filing.total_sgst else 0,
                "total_igst": float(filing.total_igst) if filing.total_igst else 0,
                "invoice_count": filing.invoice_count or 0,
                "status": filing.status,
                "compiled_at": filing.compiled_at.isoformat() if filing.compiled_at else None,
            },
        )
    # Trigger compilation if missing
    from app.tasks.tasks import compile_monthly_gst

    with contextlib.suppress(Exception):
        compile_monthly_gst.delay(store_id, period)

    # Build on-the-fly summary from gst_transactions
    rows = (
        db.session.query(
            func.sum(GSTTransaction.taxable_amount),
            func.sum(GSTTransaction.cgst_amount),
            func.sum(GSTTransaction.sgst_amount),
            func.sum(GSTTransaction.igst_amount),
            func.count(GSTTransaction.id),
        )
        .filter_by(store_id=store_id, period=period)
        .first()
    )

    return format_response(
        True,
        data={
            "period": period,
            "total_taxable": float(rows[0] or 0),
            "total_cgst": float(rows[1] or 0),
            "total_sgst": float(rows[2] or 0),
            "total_igst": float(rows[3] or 0),
            "invoice_count": rows[4] or 0,
            "status": "PENDING",
            "compiled_at": None,
        },
    )


# ── GSTR-1 JSON ─────────────────────────────────────────────────────


@gst_bp.route("/gstr1", methods=["GET"])
@require_auth
def get_gstr1():
    store_id = g.current_user["store_id"]
    period = request.args.get("period")
    if not period:
        return format_response(
            False,
            error={
                "code": "MISSING_PERIOD",
                "message": "Query parameter 'period' (YYYY-MM, status_code=400) is required",
            },
        )

    filing = db.session.query(GSTFilingPeriod).filter_by(store_id=store_id, period=period).first()
    if not filing or not filing.gstr1_json_path:
        return format_response(
            False, error={"code": "NOT_FOUND", "message": f"GSTR-1 not compiled for period {period}"}
        )

    import json
    import os

    if os.path.exists(filing.gstr1_json_path):
        with open(filing.gstr1_json_path) as f:
            gstr1_data = json.load(f)
        return format_response(success=True, data=gstr1_data, status_code=200)

    return format_response(
        success=False, error={"code": "NOT_FOUND", "message": "GSTR-1 JSON file not found"}, status_code=404
    )


@gst_bp.route("/gstr1/file", methods=["POST"])
@require_auth
@require_role("owner")
def file_gstr1():
    store_id = g.current_user["store_id"]
    body = request.get_json() or {}
    period = body.get("period")
    if not period:
        return format_response(
            False,
            error={"code": "MISSING_PERIOD", "message": "period is required"},
            status_code=400,
        )

    filing = db.session.query(GSTFilingPeriod).filter_by(store_id=store_id, period=period).first()
    if not filing:
        filing = GSTFilingPeriod(store_id=store_id, period=period, status="READY")
        db.session.add(filing)
        db.session.flush()

    now = datetime.now(timezone.utc)
    filing.status = "FILED"
    filing.compiled_at = filing.compiled_at or now
    acknowledgement_number = f"GST-{store_id}-{period.replace('-', '')}"

    if filing.gstr1_json_path:
        import json
        import os

        if os.path.exists(filing.gstr1_json_path):
            with open(filing.gstr1_json_path, encoding="utf-8") as handle:
                gstr1_data = json.load(handle)
            gstr1_data["filed_on"] = now.isoformat()
            gstr1_data["acknowledgement_number"] = acknowledgement_number
            with open(filing.gstr1_json_path, "w", encoding="utf-8") as handle:
                json.dump(gstr1_data, handle)

    db.session.commit()
    return format_response(
        True,
        data={
            "period": period,
            "status": "FILED",
            "acknowledgement_number": acknowledgement_number,
            "filed_on": now.isoformat(),
        },
    )


# ── Liability Slabs ──────────────────────────────────────────────────


@gst_bp.route("/liability-slabs", methods=["GET"])
@require_auth
def liability_slabs():
    store_id = g.current_user["store_id"]
    period = request.args.get("period")
    if not period:
        return format_response(
            False,
            error={
                "code": "MISSING_PERIOD",
                "message": "Query parameter 'period' (YYYY-MM, status_code=400) is required",
            },
        )

    gst_txns = db.session.query(GSTTransaction).filter_by(store_id=store_id, period=period).all()

    slab_map = {}
    for gt in gst_txns:
        if not gt.hsn_breakdown:
            continue
        breakdown = gt.hsn_breakdown if isinstance(gt.hsn_breakdown, dict) else {}
        for _hsn_code, detail in breakdown.items():
            rate = detail.get("rate", 0)
            rate_key = float(rate)
            if rate_key not in slab_map:
                slab_map[rate_key] = {"rate": rate_key, "taxable_value": 0, "tax_amount": 0}
            slab_map[rate_key]["taxable_value"] += float(detail.get("taxable", 0))
            slab_map[rate_key]["tax_amount"] += (
                float(detail.get("cgst", 0)) + float(detail.get("sgst", 0)) + float(detail.get("igst", 0))
            )

    slabs = sorted(slab_map.values(), key=lambda x: x["rate"])
    return format_response(success=True, data=slabs, status_code=200)


@gst_bp.route("/hsn-mappings", methods=["GET"])
@require_auth
def list_hsn_mappings():
    store_id = g.current_user["store_id"]
    mappings = db.session.query(GSTHSNMapping).filter_by(store_id=store_id).order_by(GSTHSNMapping.hsn_code.asc()).all()
    data = [
        {
            "hsn_code": mapping.hsn_code,
            "category_id": str(mapping.category_id),
            "tax_rate": float(mapping.tax_rate or 0),
            "description": mapping.description or "",
        }
        for mapping in mappings
    ]
    return format_response(True, data=data)


@gst_bp.route("/hsn-mappings", methods=["POST"])
@require_auth
@require_role("owner")
def create_hsn_mapping():
    store_id = g.current_user["store_id"]
    body = request.get_json() or {}
    if not body.get("hsn_code") or not body.get("category_id"):
        return format_response(
            success=False,
            error={"code": "VALIDATION_ERROR", "message": "hsn_code and category_id are required"},
            status_code=400,
        )

    mapping = GSTHSNMapping(
        store_id=store_id,
        category_id=body["category_id"],
        hsn_code=body["hsn_code"],
        description=body.get("description"),
        tax_rate=body.get("tax_rate"),
    )
    db.session.add(mapping)
    db.session.commit()
    return format_response(
        True,
        data={
            "hsn_code": mapping.hsn_code,
            "category_id": str(mapping.category_id),
            "tax_rate": float(mapping.tax_rate or 0),
            "description": mapping.description or "",
        },
        status_code=201,
    )


@gst_bp.route("/hsn-mappings/<string:hsn_code>", methods=["PUT", "PATCH"])
@require_auth
@require_role("owner")
def update_hsn_mapping(hsn_code):
    store_id = g.current_user["store_id"]
    mapping = db.session.query(GSTHSNMapping).filter_by(store_id=store_id, hsn_code=hsn_code).first()
    if not mapping:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "HSN mapping not found"}, status_code=404
        )

    body = request.get_json() or {}
    if "category_id" in body:
        mapping.category_id = body["category_id"]
    if "tax_rate" in body:
        mapping.tax_rate = body["tax_rate"]
    if "description" in body:
        mapping.description = body["description"]

    db.session.commit()
    return format_response(
        True,
        data={
            "hsn_code": mapping.hsn_code,
            "category_id": str(mapping.category_id),
            "tax_rate": float(mapping.tax_rate or 0),
            "description": mapping.description or "",
        },
    )


@gst_bp.route("/hsn-mappings/<string:hsn_code>", methods=["DELETE"])
@require_auth
@require_role("owner")
def delete_hsn_mapping(hsn_code):
    store_id = g.current_user["store_id"]
    mapping = db.session.query(GSTHSNMapping).filter_by(store_id=store_id, hsn_code=hsn_code).first()
    if not mapping:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "HSN mapping not found"}, status_code=404
        )

    db.session.delete(mapping)
    db.session.commit()
    return format_response(True, data={"hsn_code": hsn_code, "deleted": True})
