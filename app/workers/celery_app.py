"""Celery application. One queue for now: ``ingestion``."""

from typing import Any

from celery import Celery
from celery.signals import setup_logging

from app.config import get_settings
from app.core.logging import configure_logging

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


@setup_logging.connect  # type: ignore[untyped-decorator]
def _setup_worker_logging(**kwargs: Any) -> None:
    # same JSON structlog stack as the API; overrides celery's own logging setup
    configure_logging(get_settings().log_level)
