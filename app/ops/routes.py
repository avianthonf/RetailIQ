"""Operations routes for maintenance and system status."""

from datetime import datetime, timezone

from flask import Blueprint, jsonify

ops_bp = Blueprint("ops", __name__)


@ops_bp.route("/maintenance")
def maintenance():
    """Get maintenance schedule information."""
    return jsonify(
        {
            "data": {
                "scheduled_maintenance": [
                    {
                        "id": "maint-001",
                        "title": "System Upgrade",
                        "description": "Database optimization and security patches",
                        "scheduled_start": "2026-03-14T02:00:00Z",
                        "scheduled_end": "2026-03-14T04:00:00Z",
                        "impact": "System will be read-only during maintenance",
                        "status": "scheduled",
                    }
                ],
                "ongoing_incidents": [],
                "system_status": "healthy",
            }
        }
    )
