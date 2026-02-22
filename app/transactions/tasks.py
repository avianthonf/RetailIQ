from .. import celery_app

@celery_app.task
def rebuild_daily_aggregates(store_id, date_str):
    # Stub for daily aggregates
    print(f"Rebuilding aggregates for store {store_id} on {date_str}")

@celery_app.task
def evaluate_alerts(store_id):
    # Stub for evaluating alerts
    print(f"Evaluating alerts for store {store_id}")
