"""
RetailIQ Flask Application Factory
=====================================
Creates and configures the Flask application.
"""

import logging
import os

from flask import Flask, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# ── Extension singletons ──────────────────────────────────────────────────────
db = SQLAlchemy()
limiter = Limiter(key_func=get_remote_address)


# ── App Factory ───────────────────────────────────────────────────────────────


def _register_blueprints(app: Flask):
    """Register all API blueprints under /api/v1."""
    # ── Imports ────────────────────────────────────────────────────────────
    from app.ai_v2 import ai_v2_bp
    from app.analytics import analytics_bp
    from app.api_v2 import api_v2_bp
    from app.auth import auth_bp
    from app.auth.oauth_routes import oauth_bp
    from app.chain import chain_bp
    from app.customers import customers_bp
    from app.dashboard import dashboard_bp
    from app.decisions import decisions_bp
    from app.developer import developer_bp
    from app.einvoicing import einvoicing_bp
    from app.events import events_bp
    from app.finance import finance_bp
    from app.forecasting import forecasting_bp
    from app.gst import gst_bp
    from app.i18n import i18n_bp
    from app.inventory import inventory_bp
    from app.kyc import kyc_bp
    from app.loyalty import credit_bp, loyalty_bp
    from app.market_intelligence import market_intelligence_bp
    from app.marketplace import marketplace_bp
    from app.nlp import nlp_bp
    from app.offline import offline_bp
    from app.ops import ops_bp
    from app.payments import payments_bp
    from app.pricing import pricing_bp
    from app.receipts import barcode_bp, receipts_bp
    from app.staff_performance import staff_performance_bp
    from app.store import store_bp
    from app.suppliers import po_bp, suppliers_bp
    from app.tax_engine import tax_engine_bp
    from app.team import team_bp
    from app.transactions import transactions_bp
    from app.vision import vision_bp
    from app.whatsapp import whatsapp_bp

    # ── Configuration ──────────────────────────────────────────────────────
    prefix = "/api/v1"

    # ── V1 API Registrations ───────────────────────────────────────────────
    app.register_blueprint(ai_v2_bp, url_prefix="/api/v2/ai")
    app.register_blueprint(analytics_bp, url_prefix=f"{prefix}/analytics")
    app.register_blueprint(auth_bp, url_prefix=f"{prefix}/auth")
    app.register_blueprint(barcode_bp, url_prefix=f"{prefix}/barcodes")
    app.register_blueprint(chain_bp, url_prefix=f"{prefix}/chain")
    app.register_blueprint(customers_bp, url_prefix=f"{prefix}/customers")
    app.register_blueprint(dashboard_bp, url_prefix=f"{prefix}/dashboard")
    app.register_blueprint(decisions_bp, url_prefix=f"{prefix}/decisions")
    app.register_blueprint(developer_bp, url_prefix=f"{prefix}/developer")
    app.register_blueprint(einvoicing_bp, url_prefix="/api/v2/einvoice")
    app.register_blueprint(events_bp, url_prefix=f"{prefix}/events")
    app.register_blueprint(finance_bp, url_prefix="/api/v2/finance")
    app.register_blueprint(forecasting_bp, url_prefix=f"{prefix}/forecasting")
    app.register_blueprint(gst_bp, url_prefix=f"{prefix}/gst")
    app.register_blueprint(i18n_bp, url_prefix=f"{prefix}/i18n")
    app.register_blueprint(inventory_bp, url_prefix=f"{prefix}/inventory")
    app.register_blueprint(kyc_bp, url_prefix=f"{prefix}/kyc")
    app.register_blueprint(loyalty_bp, url_prefix=f"{prefix}/loyalty")
    app.register_blueprint(credit_bp, url_prefix=f"{prefix}/credit")
    app.register_blueprint(market_intelligence_bp, url_prefix=f"{prefix}/market")
    app.register_blueprint(marketplace_bp, url_prefix=f"{prefix}/marketplace")
    app.register_blueprint(nlp_bp, url_prefix=f"{prefix}/nlp")
    app.register_blueprint(oauth_bp, url_prefix="/oauth")
    app.register_blueprint(offline_bp, url_prefix=f"{prefix}/offline")
    app.register_blueprint(ops_bp, url_prefix=f"{prefix}/ops")
    app.register_blueprint(payments_bp, url_prefix=f"{prefix}/payments")
    app.register_blueprint(po_bp, url_prefix=f"{prefix}/purchase-orders")
    app.register_blueprint(pricing_bp, url_prefix=f"{prefix}/pricing")
    app.register_blueprint(receipts_bp, url_prefix=f"{prefix}/receipts")
    app.register_blueprint(staff_performance_bp, url_prefix=f"{prefix}/staff")
    app.register_blueprint(store_bp, url_prefix=f"{prefix}/store")
    app.register_blueprint(suppliers_bp, url_prefix=f"{prefix}/suppliers")
    app.register_blueprint(tax_engine_bp, url_prefix=f"{prefix}/tax")
    app.register_blueprint(team_bp, url_prefix=f"{prefix}/team")
    app.register_blueprint(transactions_bp, url_prefix=f"{prefix}/transactions")
    app.register_blueprint(vision_bp, url_prefix=f"{prefix}/vision")
    app.register_blueprint(whatsapp_bp, url_prefix=f"{prefix}/whatsapp")

    # ── V2 / Other API Registrations ──────────────────────────────────────
    app.register_blueprint(api_v2_bp, url_prefix="/api/v2")


def _register_error_handlers(app: Flask):
    from flask import jsonify

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"success": False, "error": {"code": "BAD_REQUEST", "message": str(e)}}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"success": False, "error": {"code": "UNAUTHORIZED", "message": "Authentication required"}}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied"}}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "Resource not found"}}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"success": False, "error": {"code": "METHOD_NOT_ALLOWED", "message": str(e)}}), 405

    @app.errorhandler(422)
    def unprocessable(e):
        return jsonify({"success": False, "error": {"code": "UNPROCESSABLE_ENTITY", "message": str(e)}}), 422

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({"success": False, "error": {"code": "RATE_LIMITED", "message": "Too many requests"}}), 429

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception("Unhandled exception: %s", e)
        db.session.rollback()
        return jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": "Internal server error"}}), 500

    return app


from .factory import create_app
