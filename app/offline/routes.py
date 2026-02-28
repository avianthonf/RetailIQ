import logging
from flask import g
from . import offline_bp
from ..auth.decorators import require_auth
from ..auth.utils import format_response
from ..models import AnalyticsSnapshot
from .. import db
from ..tasks.tasks import build_analytics_snapshot

logger = logging.getLogger(__name__)

@offline_bp.route('/snapshot', methods=['GET'])
@require_auth
def get_snapshot():
    """
    Returns the latest offline analytics snapshot for the store.
    If no snapshot exists yet, triggers a build and returns 202.
    """
    store_id = g.current_user['store_id']
    
    snapshot = db.session.query(AnalyticsSnapshot).filter_by(store_id=store_id).first()
    
    if not snapshot:
        # Trigger background generation if it doesn't exist
        build_analytics_snapshot.delay(store_id)
        return format_response(False, error={"message": "Snapshot is currently building"}), 202
        
    return format_response(True, data={
        "built_at": snapshot.built_at.isoformat() if snapshot.built_at else None,
        "size_bytes": snapshot.size_bytes,
        "snapshot": snapshot.snapshot_data
    }), 200
