import contextlib
from decimal import Decimal

from flask import g, request
from marshmallow import ValidationError
from sqlalchemy import func

from .. import db
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import GSTFilingPeriod, GSTTransaction, HSNMaster, StoreGSTConfig
from . import gst_bp
from .schemas import GSTConfigUpsertSchema
from .utils import validate_gstin

# ── GST Config ──────────────────────────────────────────────────────

@gst_bp.route('/gst/config', methods=['GET'])
@require_auth
def get_gst_config():
    store_id = g.current_user['store_id']
    config = db.session.query(StoreGSTConfig).filter_by(store_id=store_id).first()
    if not config:
        return format_response(True, data={
            'gstin': None,
            'registration_type': 'REGULAR',
            'state_code': None,
            'is_gst_enabled': False
        }), 200
    return format_response(True, data={
        'gstin': config.gstin,
        'registration_type': config.registration_type,
        'state_code': config.state_code,
        'is_gst_enabled': config.is_gst_enabled
    }), 200


@gst_bp.route('/gst/config', methods=['PUT'])
@require_auth
@require_role('owner')
def update_gst_config():
    try:
        data = GSTConfigUpsertSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400

    store_id = g.current_user['store_id']

    # Validate GSTIN if provided
    gstin = data.get('gstin')
    if gstin and not validate_gstin(gstin):
        return format_response(False, error={"code": "INVALID_GSTIN", "message": "Invalid GSTIN format or checksum"}), 422

    config = db.session.query(StoreGSTConfig).filter_by(store_id=store_id).first()
    if not config:
        config = StoreGSTConfig(store_id=store_id)
        db.session.add(config)

    for key in ('gstin', 'registration_type', 'state_code', 'is_gst_enabled'):
        if key in data:
            setattr(config, key, data[key])

    db.session.commit()
    return format_response(True, data={
        'gstin': config.gstin,
        'registration_type': config.registration_type,
        'state_code': config.state_code,
        'is_gst_enabled': config.is_gst_enabled
    }), 200


# ── HSN Search ──────────────────────────────────────────────────────

@gst_bp.route('/gst/hsn-search', methods=['GET'])
@require_auth
def hsn_search():
    q = request.args.get('q', '').strip()
    if not q:
        return format_response(False, error={"code": "MISSING_QUERY", "message": "Query parameter 'q' is required"}), 400

    results = db.session.query(HSNMaster).filter(
        db.or_(
            HSNMaster.hsn_code.like(f'{q}%'),
            HSNMaster.description.ilike(f'%{q}%')
        )
    ).limit(10).all()

    data = [{
        'hsn_code': r.hsn_code,
        'description': r.description,
        'default_gst_rate': float(r.default_gst_rate) if r.default_gst_rate is not None else None
    } for r in results]

    return format_response(True, data=data), 200


# ── GST Summary ─────────────────────────────────────────────────────

@gst_bp.route('/gst/summary', methods=['GET'])
@require_auth
def gst_summary():
    store_id = g.current_user['store_id']
    period = request.args.get('period')
    if not period:
        return format_response(False, error={"code": "MISSING_PERIOD", "message": "Query parameter 'period' (YYYY-MM) is required"}), 400

    filing = db.session.query(GSTFilingPeriod).filter_by(store_id=store_id, period=period).first()
    if filing:
        return format_response(True, data={
            'period': filing.period,
            'total_taxable': float(filing.total_taxable) if filing.total_taxable else 0,
            'total_cgst': float(filing.total_cgst) if filing.total_cgst else 0,
            'total_sgst': float(filing.total_sgst) if filing.total_sgst else 0,
            'total_igst': float(filing.total_igst) if filing.total_igst else 0,
            'invoice_count': filing.invoice_count or 0,
            'status': filing.status,
            'compiled_at': filing.compiled_at.isoformat() if filing.compiled_at else None
        }), 200

    # Trigger compilation if missing
    from app.tasks.tasks import compile_monthly_gst
    with contextlib.suppress(Exception):
        compile_monthly_gst.delay(store_id, period)

    # Build on-the-fly summary from gst_transactions
    rows = db.session.query(
        func.sum(GSTTransaction.taxable_amount),
        func.sum(GSTTransaction.cgst_amount),
        func.sum(GSTTransaction.sgst_amount),
        func.sum(GSTTransaction.igst_amount),
        func.count(GSTTransaction.id)
    ).filter_by(store_id=store_id, period=period).first()

    return format_response(True, data={
        'period': period,
        'total_taxable': float(rows[0] or 0),
        'total_cgst': float(rows[1] or 0),
        'total_sgst': float(rows[2] or 0),
        'total_igst': float(rows[3] or 0),
        'invoice_count': rows[4] or 0,
        'status': 'PENDING',
        'compiled_at': None
    }), 200


# ── GSTR-1 JSON ─────────────────────────────────────────────────────

@gst_bp.route('/gst/gstr1', methods=['GET'])
@require_auth
def get_gstr1():
    store_id = g.current_user['store_id']
    period = request.args.get('period')
    if not period:
        return format_response(False, error={"code": "MISSING_PERIOD", "message": "Query parameter 'period' (YYYY-MM) is required"}), 400

    filing = db.session.query(GSTFilingPeriod).filter_by(store_id=store_id, period=period).first()
    if not filing or not filing.gstr1_json_path:
        return format_response(False, error={"code": "NOT_FOUND", "message": f"GSTR-1 not compiled for period {period}"}), 404

    import json
    import os
    if os.path.exists(filing.gstr1_json_path):
        with open(filing.gstr1_json_path) as f:
            gstr1_data = json.load(f)
        return format_response(True, data=gstr1_data), 200

    return format_response(False, error={"code": "NOT_FOUND", "message": "GSTR-1 JSON file not found"}), 404


# ── Liability Slabs ──────────────────────────────────────────────────

@gst_bp.route('/gst/liability-slabs', methods=['GET'])
@require_auth
def liability_slabs():
    store_id = g.current_user['store_id']
    period = request.args.get('period')
    if not period:
        return format_response(False, error={"code": "MISSING_PERIOD", "message": "Query parameter 'period' (YYYY-MM) is required"}), 400

    gst_txns = db.session.query(GSTTransaction).filter_by(store_id=store_id, period=period).all()

    slab_map = {}
    for gt in gst_txns:
        if not gt.hsn_breakdown:
            continue
        breakdown = gt.hsn_breakdown if isinstance(gt.hsn_breakdown, dict) else {}
        for _hsn_code, detail in breakdown.items():
            rate = detail.get('rate', 0)
            rate_key = float(rate)
            if rate_key not in slab_map:
                slab_map[rate_key] = {'rate': rate_key, 'taxable_value': 0, 'tax_amount': 0}
            slab_map[rate_key]['taxable_value'] += float(detail.get('taxable', 0))
            slab_map[rate_key]['tax_amount'] += (
                float(detail.get('cgst', 0)) +
                float(detail.get('sgst', 0)) +
                float(detail.get('igst', 0))
            )

    slabs = sorted(slab_map.values(), key=lambda x: x['rate'])
    return format_response(True, data=slabs), 200
