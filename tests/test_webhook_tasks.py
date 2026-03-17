import contextlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models import APIUsageRecord, DeveloperApplication, WebhookEvent
from app.models.missing_models import Developer
from app.tasks.webhook_tasks import deliver_webhook, sync_api_usage


@pytest.fixture(autouse=True)
def mock_task_session(app):
    from app import db

    @contextlib.contextmanager
    def _mock_session(**kwargs):
        try:
            yield db.session
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    with patch("app.tasks.webhook_tasks.task_session", new=_mock_session):
        yield


@pytest.fixture
def test_app_and_event(app, test_store, test_owner):
    from app import db

    dev = Developer(
        user_id=test_owner.user_id,
        name="Test Dev",
        email="dev@test.com",
    )
    db.session.add(dev)
    db.session.flush()

    dev_app = DeveloperApplication(
        developer_id=dev.id,
        name="Test App",
        client_id="test_client_id",
        client_secret_hash="fake_hash",
        app_type="BACKEND",
        webhook_url="https://example.com/webhook",
    )
    db.session.add(dev_app)
    db.session.commit()

    event = WebhookEvent(
        app_id=dev_app.id,
        event_type="inventory.update",
        payload={"item": "apple"},
        delivery_url="https://example.com/webhook",
        status="PENDING",
    )
    db.session.add(event)
    db.session.commit()

    return dev_app, event


def test_deliver_webhook_not_found(app):
    with patch("app.tasks.webhook_tasks.logger") as mock_logger:
        deliver_webhook(9999)
        mock_logger.error.assert_called_once_with("Webhook event 9999 not found")


def test_deliver_webhook_already_delivered(app, test_app_and_event):
    from app import db

    _, event = test_app_and_event
    event.status = "DELIVERED"
    db.session.commit()

    with patch("app.tasks.webhook_tasks.requests.post") as mock_post:
        deliver_webhook(event.id)
        mock_post.assert_not_called()


def test_deliver_webhook_no_url(app, test_app_and_event):
    from app import db

    dev_app, event = test_app_and_event
    dev_app.webhook_url = None
    db.session.commit()

    with patch("app.tasks.webhook_tasks.requests.post") as mock_post:
        deliver_webhook(event.id)
        from app import db

        # Ensure we refresh from the database to see the change from the task session
        db.session.expire_all()
        event = db.session.get(WebhookEvent, event.id)
        mock_post.assert_not_called()
        assert event.status == "FAILED"


def test_deliver_webhook_success(app, test_app_and_event):
    from app import db

    dev_app, event = test_app_and_event

    with patch("app.tasks.webhook_tasks.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "OK"

        deliver_webhook(event.id)

        # We need to refresh the event from the DB to see the status change
        # after the task_session context manager commits it.
        event = db.session.get(WebhookEvent, event.id)

        mock_post.assert_called_once()
        assert event.status == "DELIVERED"
        assert event.last_response_code == 200
        assert event.attempt_count == 1


def test_deliver_webhook_failure_retries(app, test_app_and_event):
    _, event = test_app_and_event

    with (
        patch("app.tasks.webhook_tasks.requests.post") as mock_post,
        patch("app.tasks.webhook_tasks.deliver_webhook.retry") as mock_retry,
    ):
        mock_post.return_value.status_code = 500
        mock_retry.side_effect = Exception("Retry Triggered")

        with pytest.raises(Exception, match="Retry Triggered"):
            deliver_webhook(event.id)

        assert event.status == "FAILED"
        assert event.last_response_code == 500
        mock_retry.assert_called_once()


def test_deliver_webhook_request_exception(app, test_app_and_event):
    import requests

    _, event = test_app_and_event

    with (
        patch("app.tasks.webhook_tasks.requests.post") as mock_post,
        patch("app.tasks.webhook_tasks.deliver_webhook.retry") as mock_retry,
    ):
        mock_post.side_effect = requests.exceptions.Timeout("Timeout occurred")
        mock_retry.side_effect = Exception("Retry Triggered: Timeout occurred")

        with pytest.raises(Exception):
            deliver_webhook(event.id)

        assert event.status == "FAILED"
        mock_retry.assert_called_once()


def test_sync_api_usage_no_keys():
    with patch("app.auth.utils.get_redis_client") as mock_get_redis:
        mock_redis = MagicMock()
        mock_redis.keys.return_value = []
        mock_get_redis.return_value = mock_redis

        sync_api_usage()

        mock_redis.hgetall.assert_not_called()


def test_sync_api_usage_success(app, test_owner):
    from app import db

    dev = Developer(
        user_id=test_owner.user_id,
        name="Usage Dev",
        email="usage@test.com",
    )
    db.session.add(dev)
    db.session.flush()

    dev_app = DeveloperApplication(
        developer_id=dev.id,
        name="Usage App",
        client_id="usage_client",
        client_secret_hash="fake",
        app_type="BACKEND",
    )
    db.session.add(dev_app)
    db.session.commit()
    dev_app_id = dev_app.id

    with patch("app.tasks.webhook_tasks.get_redis_client") as mock_get_redis:
        mock_redis = MagicMock()
        dt = datetime.now(timezone.utc)
        key = f"usage:{dev_app_id}:/api/test:GET:{dt.isoformat()}"
        mock_redis.keys.return_value = [key]
        mock_redis.hgetall.return_value = {
            "request_count": "10",
            "error_count": "1",
            "total_latency_ms": "500",
            "bytes_transferred": "2048",
        }
        mock_get_redis.return_value = mock_redis

        sync_api_usage()

        record = db.session.query(APIUsageRecord).filter_by(app_id=dev_app_id).first()
        assert record is not None
        assert record.request_count == 10
        assert record.error_count == 1
        assert int(record.avg_latency_ms) == 50
        assert record.bytes_transferred == 2048

        mock_redis.delete.assert_called_once_with(key)


def test_sync_api_usage_existing_record(app, test_owner):
    from app import db

    dev = Developer(
        user_id=test_owner.user_id,
        name="Usage Dev 2",
        email="usage2@test.com",
    )
    db.session.add(dev)
    db.session.flush()

    dev_app = DeveloperApplication(
        developer_id=dev.id,
        name="Usage App 2",
        client_id="usage_client_2",
        client_secret_hash="fake",
        app_type="BACKEND",
    )
    db.session.add(dev_app)
    db.session.commit()
    dev_app_id = dev_app.id

    # Use naive datetime for SQLite compatibility in tests
    dt = datetime(2023, 1, 1, 12, 0)

    existing = APIUsageRecord(
        app_id=dev_app_id,
        endpoint="/api/test",
        method="GET",
        minute_bucket=dt,
        request_count=5,
        error_count=0,
        avg_latency_ms=40.0,
        bytes_transferred=1024,
    )
    db.session.add(existing)
    db.session.commit()

    with patch("app.tasks.webhook_tasks.get_redis_client") as mock_get_redis:
        mock_redis = MagicMock()
        key = f"usage:{dev_app_id}:/api/test:GET:{dt.isoformat()}"
        mock_redis.keys.return_value = [key]
        # Ensure it returns a real dict so .get() works as expected
        usage_data = {"request_count": "5", "error_count": "1", "total_latency_ms": "300", "bytes_transferred": "1024"}
        mock_redis.hgetall.return_value = usage_data
        mock_get_redis.return_value = mock_redis

        sync_api_usage()

        record = db.session.query(APIUsageRecord).filter_by(app_id=dev_app_id).first()
        assert record is not None
        assert record.request_count == 10
        assert record.error_count == 1
        assert record.bytes_transferred == 2048
        mock_redis.delete.assert_called_once_with(key)
