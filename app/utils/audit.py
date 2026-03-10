from datetime import datetime, timezone

from flask import current_app, g, request

from app import db
from app.models import AuditLog


def audit_log(
    action: str,
    resource_type: str,
    resource_id: str = None,
    actor_id: int = None,
    actor_type: str = "USER",
    result: str = "SUCCESS",
    meta_data: dict = None,
):
    """
    Records a security event in the audit log.

    Args:
        action: The action performed (e.g., 'LOGIN', 'DELETE_PRODUCT', 'UPDATE_RBAC')
        resource_type: The type of resource (e.g., 'USER', 'PRODUCT', 'STORE')
        resource_id: The ID of the specific resource
        actor_id: The ID of the user/entity performing the action (defaults to g.current_user)
        actor_type: The type of actor (USER, API_KEY, SYSTEM, ADMIN)
        result: The outcome (SUCCESS, FAILURE, DENIED)
        meta_data: Additional contextual information
    """
    try:
        # Resolve actor from context if not provided
        if actor_id is None and hasattr(g, "current_user") and g.current_user:
            actor_id = g.current_user.get("user_id")
            # Determine actor type from context roles if needed
            role = g.current_user.get("role")
            if role == "owner":
                actor_type = "ADMIN"

        log_entry = AuditLog(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None,
            result=result,
            meta_data=meta_data,
            timestamp=datetime.now(timezone.utc),
        )

        db.session.add(log_entry)
        db.session.commit()

    except Exception as e:
        # Audit logging should not break the main application flow
        # Log the failure but continue
        if current_app:
            current_app.logger.error(f"Audit Logging Failed: {e}")
