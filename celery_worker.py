import os

from celery.schedules import crontab

from app import celery_app, create_app

# Important: load tasks so celery recognizes them
from app.tasks import (
    tasks,
    webhook_tasks,  # noqa: F401
)
from app.tasks.tasks import run_weekly_pricing_analysis  # noqa: F401

app = create_app()
app.app_context().push()

celery_app.conf.timezone = "Asia/Kolkata"

celery_app.conf.beat_schedule = {
    "rebuild_every_15_min": {
        "task": "tasks.rebuild_daily_aggregates_all_stores",
        "schedule": crontab(minute="*/15"),
    },
    "alerts_every_15_min": {
        "task": "tasks.evaluate_alerts_all_stores",
        "schedule": crontab(minute="*/15"),
    },
    "forecasting_daily": {
        "task": "tasks.run_batch_forecasting",
        "schedule": crontab(hour=2, minute=0),
    },
    "slow_movers_weekly": {
        "task": "tasks.detect_slow_movers",
        "schedule": crontab(day_of_week="monday", hour=6, minute=0),
    },
    "weekly_digest": {
        "task": "tasks.send_weekly_digest",
        "schedule": crontab(day_of_week="monday", hour=8, minute=0),
    },
    "overdue_po_daily": {
        "task": "tasks.check_overdue_purchase_orders",
        "schedule": crontab(hour=8, minute=0),
    },
    "auto_close_staff_sessions": {
        "task": "tasks.auto_close_open_sessions",
        "schedule": crontab(hour=23, minute=45),
    },
    "generate_staff_daily_summary": {
        "task": "tasks.generate_staff_daily_summary",
        "schedule": crontab(hour=0, minute=15),
    },
    "build_all_analytics_snapshots": {
        "task": "tasks.build_all_analytics_snapshots",
        "schedule": crontab(hour=6, minute=0),
    },
    "chain_aggregation_daily": {
        "task": "tasks.aggregate_chain_daily_all_groups",
        "schedule": crontab(hour=1, minute=0),
    },
    "chain_transfer_detection_weekly": {
        "task": "tasks.detect_transfer_opportunities_all_groups",
        "schedule": crontab(day_of_week="monday", hour=5, minute=0),
    },
    "weekly_pricing_analysis": {
        "task": "tasks.run_weekly_pricing_analysis",
        "schedule": crontab(day_of_week="sunday", hour=3, minute=0),
    },
    "sync_api_usage_5_min": {
        "task": "tasks.sync_api_usage",
        "schedule": crontab(minute="*/5"),
    },
}

if __name__ == "__main__":
    celery_app.worker_main()
