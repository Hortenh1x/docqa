"""Celery application. One queue for now: ``ingestion``."""

from celery import Celery

from app.config import get_settings

celery_app = Celery("docqa", broker=get_settings().redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="ingestion",
    broker_connection_retry_on_startup=True,
    imports=("app.ingestion.tasks",),
)
