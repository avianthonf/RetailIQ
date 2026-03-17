"""Celery worker and beat entry point."""

import os

from celery import Celery

from app import create_app

flask_app = create_app()

celery_app = Celery(
    flask_app.name,
    broker=flask_app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/1"),
    backend=flask_app.config.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    include=["app.tasks.tasks"],
)
celery_app.conf.update(flask_app.config)


# Push app context so tasks can use db, etc.
class ContextTask(celery_app.Task):
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)


celery_app.Task = ContextTask
