import hashlib
import hmac
import json
from datetime import datetime, timezone

import requests
from celery import shared_task
from celery.utils.log import get_task_logger

from app import db
from app.models import DeveloperApplication, WebhookEvent

from .db_session import task_session

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    name="tasks.deliver_webhook",
    max_retries=6,
    default_retry_delay=30,  # Initial delay
    retry_backoff=True,  # Exponential backoff: 30s, 60s, 120s...
)
def deliver_webhook(self, event_id):
    """
    Delivers a webhook event to the specified delivery_url.
    """
    with task_session() as session:
        event = session.get(WebhookEvent, event_id)
        if not event:
            logger.error(f"Webhook event {event_id} not found")
            return

        if event.status in ("DELIVERED", "DEAD_LETTERED"):
            return

        app = session.get(DeveloperApplication, event.app_id)
        if not app or not app.webhook_url:
            event.status = "FAILED"
            session.commit()
            return

        payload_json = json.dumps(event.payload)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "RetailIQ-Webhook/1.0",
            "X-RetailIQ-Event": event.event_type,
            "X-RetailIQ-Delivery-ID": str(event.id),
        }

        # Sign the payload if a secret is provided
        if app.webhook_secret:
            signature = hmac.new(app.webhook_secret.encode(), payload_json.encode(), hashlib.sha256).hexdigest()
            headers["X-RetailIQ-Signature"] = signature

        try:
            response = requests.post(
                event.delivery_url,
                data=payload_json,
                headers=headers,
                timeout=30,  # As per requirements
            )

            event.last_response_code = response.status_code
            event.last_attempt_at = datetime.now(timezone.utc)
            event.attempt_count += 1

            if 200 <= response.status_code < 300:
                event.status = "DELIVERED"
                session.commit()
                logger.info(f"Webhook {event_id} delivered successfully to {event.delivery_url}")
            else:
                event.status = "FAILED"
                session.commit()
                logger.warning(f"Webhook {event_id} failed with status {response.status_code}")
                # Retry for non-2xx codes
                raise self.retry(exc=Exception(f"HTTP {response.status_code}"))

        except requests.exceptions.RequestException as exc:
            event.last_attempt_at = datetime.now(timezone.utc)
            event.attempt_count += 1
            event.status = "FAILED"
            session.commit()
            logger.error(f"Webhook {event_id} request failed: {exc}")
            raise self.retry(exc=exc)

        except Exception as exc:
            # For max retries exceeded, Celery will handle it, but we should mark it as DEAD_LETTERED
            # We'll use a custom block for that if needed, or check self.request.retries
            if self.request.retries >= self.max_retries:
                event.status = "DEAD_LETTERED"
                session.commit()
            raise exc


@shared_task(name="tasks.sync_api_usage")
def sync_api_usage():
    """
    Periodic task to sync API usage from Redis to PostgreSQL.
    """
    from app.auth.utils import get_redis_client
    from app.models import APIUsageRecord

    redis_client = get_redis_client()
    # Find all usage keys: usage:app_id:path:method:minute_bucket
    keys = redis_client.keys("usage:*")

    if not keys:
        return

    with task_session() as session:
        for key in keys:
            data = redis_client.hgetall(key)
            if not data:
                continue

            # Parse key
            parts = key.split(":")
            if len(parts) < 5:
                continue

            app_id = int(parts[1])
            endpoint = parts[2]
            method = parts[3]
            minute_bucket_str = ":".join(parts[4:])
            minute_bucket = datetime.fromisoformat(minute_bucket_str)

            # Upsert into DB
            # Note: For high scale, use a faster upsert or batch
            record = (
                session.query(APIUsageRecord)
                .filter_by(app_id=app_id, endpoint=endpoint, method=method, minute_bucket=minute_bucket)
                .first()
            )

            req_count = int(data.get("request_count", 0))
            err_count = int(data.get("error_count", 0))
            total_lat = int(data.get("total_latency_ms", 0))
            bytes_tx = int(data.get("bytes_transferred", 0))

            if record:
                record.request_count += req_count
                record.error_count += err_count
                # Approximate new avg latency
                total_reqs = record.request_count
                record.avg_latency_ms = (
                    float(record.avg_latency_ms or 0) * (total_reqs - req_count) + total_lat
                ) / total_reqs
                record.bytes_transferred += bytes_tx
            else:
                record = APIUsageRecord(
                    app_id=app_id,
                    endpoint=endpoint,
                    method=method,
                    minute_bucket=minute_bucket,
                    request_count=req_count,
                    error_count=err_count,
                    avg_latency_ms=total_lat / req_count if req_count > 0 else 0,
                    bytes_transferred=bytes_tx,
                )
                session.add(record)

            # Delete from Redis after successful sync
            redis_client.delete(key)

        session.commit()

    logger.info(f"Synced {len(keys)} usage records from Redis to DB")
