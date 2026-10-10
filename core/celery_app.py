"""Celery application configuration with JSON serialization and strict routing."""

from celery import Celery

from core.config import settings

celery_app = Celery(
    "bulk_certificate_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "tasks.certificate_tasks",
        "tasks.maintenance_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_default_queue=settings.CELERY_TASK_DEFAULT_QUEUE,
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
)
