import os
from celery.schedules import crontab
from app import create_app, celery_app

# Important: load tasks so celery recognizes them
from app.tasks import tasks

app = create_app()
app.app_context().push()

celery_app.conf.timezone = 'Asia/Kolkata' 

celery_app.conf.beat_schedule = {
    'rebuild_every_15_min': {
        'task': 'tasks.rebuild_daily_aggregates_all_stores',
        'schedule': crontab(minute='*/15'),
    },
    'alerts_every_15_min': {
        'task': 'tasks.evaluate_alerts_all_stores',
        'schedule': crontab(minute='*/15'),
    },
    'forecasting_daily': {
        'task': 'tasks.run_batch_forecasting',
        'schedule': crontab(hour=2, minute=0),
    },
    'slow_movers_weekly': {
        'task': 'tasks.detect_slow_movers',
        'schedule': crontab(day_of_week='monday', hour=6, minute=0),
    },
    'weekly_digest': {
        'task': 'tasks.send_weekly_digest',
        'schedule': crontab(day_of_week='monday', hour=8, minute=0),
    },
}

if __name__ == '__main__':
    celery_app.worker_main()
