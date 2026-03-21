"""Operations routes for maintenance and system status."""

from datetime import datetime, timezone

from flask import Blueprint, jsonify

ops_bp = Blueprint("ops", __name__)


@ops_bp.route("/maintenance")
def maintenance():
    """Get maintenance schedule information.

    Returns an empty schedule when no maintenance is planned.
    A future admin panel can POST maintenance windows to a dedicated table;
    until then this endpoint truthfully reports "nothing scheduled".
    """
    return jsonify(
        {
            "data": {
                "scheduled_maintenance": [],
                "ongoing_incidents": [],
                "system_status": "healthy",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        }
    )
