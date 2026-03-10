from datetime import datetime, timezone

from app import db
from app.models import DeveloperApplication, WebhookEvent
from app.tasks.webhook_tasks import deliver_webhook


def queue_webhook_event(app_id, event_type, payload):
    """
    Creates a WebhookEvent and queues it for delivery.
    """
    app = db.session.get(DeveloperApplication, app_id)
    if not app or not app.webhook_url:
        return None

    new_event = WebhookEvent(
        app_id=app_id,
        event_type=event_type,
        payload=payload,
        delivery_url=app.webhook_url,
        status="PENDING",
        attempt_count=0,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(new_event)
    db.session.flush()  # Get ID

    # Queue task
    deliver_webhook.delay(new_event.id)

    return new_event.id


def broadcast_event(event_type, payload, required_scope=None):
    """
    Broadcasts an event to all apps that have the required scope and a webhook URL.
    """
    # This is a simplified version. In a real app, we'd filter apps by scope.
    apps = db.session.query(DeveloperApplication).filter(DeveloperApplication.webhook_url.isnot(None)).all()

    queued_ids = []
    for app in apps:
        # Simple scope check if required
        if required_scope and required_scope not in (app.scopes or []):
            continue

        eid = queue_webhook_event(app.id, event_type, payload)
        if eid:
            queued_ids.append(eid)

    return queued_ids
