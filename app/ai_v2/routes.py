from flask import g, jsonify, request

from .. import db
from ..auth.decorators import require_auth
from ..auth.utils import format_response
from . import ai_v2_bp


@ai_v2_bp.route("/forecast", methods=["POST"])
@require_auth
def forecast_v2():
    data = request.json or {}
    product_id = data.get("product_id")
    if not product_id:
        return jsonify({"message": "product_id is required"})
    from ..forecasting.engine import generate_demand_forecast

    result = generate_demand_forecast(g.current_user["store_id"], product_id, db.session)
    return format_response(data=result)


@ai_v2_bp.route("/vision/shelf-scan", methods=["POST"])
@require_auth
def shelf_scan_v2():
    data = request.json or {}
    image_url = data.get("image_url")
    if not image_url:
        return format_response(success=False, error={"code": "MISSING_PARAM", "message": "image_url is required"})
    from ..vision.shelf import process_shelf_scan

    analysis = process_shelf_scan(image_url)
    return format_response(data={"analysis": analysis})


@ai_v2_bp.route("/vision/receipt", methods=["POST"])
@require_auth
def receipt_v2():
    data = request.json or {}
    image_url = data.get("image_url")
    if not image_url:
        return format_response(success=False, error={"code": "MISSING_PARAM", "message": "image_url is required"})
    from ..vision.receipt import digitize_receipt

    result = digitize_receipt(image_url)
    return format_response(data=result)


@ai_v2_bp.route("/nlp/query", methods=["POST"])
@require_auth
def nlp_query_v2():
    data = request.json or {}
    query_text = data.get("query")
    if not query_text:
        return jsonify({"message": "query is required"})
    from ..nlp.assistant import handle_assistant_query

    response = handle_assistant_query(query_text, g.current_user["store_id"])
    return jsonify({"response": response})


@ai_v2_bp.route("/recommend", methods=["POST"])
@require_auth
def recommend_v2():
    data = request.json or {}
    user_id = data.get("user_id")

    from ..nlp.recommender import get_ai_recommendations

    recs = get_ai_recommendations(user_id, g.current_user["store_id"])
    return jsonify({"recommendations": recs})


@ai_v2_bp.route("/pricing/optimize", methods=["POST"])
@require_auth
def pricing_optimize_v2():
    data = request.json or {}
    product_ids = data.get("product_ids")
    if not product_ids:
        return format_response(
            success=False, error={"code": "MISSING_PARAM", "message": "product_ids list is required"}
        )
    from ..pricing.engine import generate_optimal_price

    results = generate_optimal_price(g.current_user["store_id"], product_ids, db.session)
    return format_response(data=results)
