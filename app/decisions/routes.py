import time

from flask import Blueprint, jsonify

from app import db
from app.auth.decorators import require_auth
from app.decisions.engine import build_context, evaluate_rules

decisions_bp = Blueprint('decisions', __name__)

@decisions_bp.route('/', methods=['GET'])
@require_auth
def get_decisions():
    from flask import g
    store_id = g.current_user['store_id']

    start = time.time()
    # 1. Build context (pure SQL reads, zero-filling, deterministic rules)
    contexts = build_context(db.session, store_id)

    # 2. Evaluate mathematically bounded rules
    actions = evaluate_rules(contexts)
    duration_ms = (time.time() - start) * 1000

    # Check if WhatsApp is active
    from app.models import WhatsAppConfig
    wa_config = db.session.query(WhatsAppConfig).filter_by(store_id=store_id, is_active=True).first()
    wa_enabled = wa_config is not None and bool(wa_config.access_token_encrypted)

    # 3. Add contextual WhatsApp option
    if wa_enabled:
        for action in actions:
             action["available_actions"] = ["Acknowledge", "Send via WhatsApp"]

    return jsonify({
        "status": "success",
        "data": actions,
        "meta": {
            "execution_time_ms": round(duration_ms, 2),
            "total_recommendations": len(actions),
            "whatsapp_enabled": wa_enabled
        }
    }), 200
