from flask import Blueprint, jsonify
from app import db
from app.auth.decorators import require_auth
from app.decisions.engine import build_context, evaluate_rules
import time

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
    
    return jsonify({
        "status": "success",
        "data": actions,
        "meta": {
            "execution_time_ms": round(duration_ms, 2),
            "total_recommendations": len(actions)
        }
    }), 200
