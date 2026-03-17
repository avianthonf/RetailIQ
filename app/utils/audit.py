"""RetailIQ Audit Logging."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def audit_log(
    action: str,
    resource_type: str,
    resource_id: Any = None,
    result: str = "SUCCESS",
    meta_data: dict | None = None,
) -> None:
    """
    Record an audit event.
    Uses request context (g) for actor_id / IP when available.
    """
    try:
        from flask import g, request

        from app import db
        from app.models import AuditLog

        actor_id = None
        ip_address = None
        user_agent = None

        try:
            current_user = getattr(g, "current_user", None)
            if current_user:
                actor_id = current_user.get("user_id")
        except RuntimeError:
            pass  # Outside request context

        try:
            ip_address = request.remote_addr
            user_agent = request.user_agent.string
        except RuntimeError:
            pass

        log_entry = AuditLog(
            actor_id=actor_id,
            actor_type="USER",
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            ip_address=ip_address,
            user_agent=user_agent,
            result=result,
            meta_data=meta_data,
        )
        db.session.add(log_entry)
        db.session.flush()  # Don't commit here; let the caller commit
    except Exception as exc:
        logger.warning("Failed to write audit log: %s", exc)
