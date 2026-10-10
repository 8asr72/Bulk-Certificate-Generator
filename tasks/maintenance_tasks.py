"""Maintenance and diagnostic tasks for stalled job recovery, outbox dispatch, and reconciliation."""

import uuid
from typing import Any

from sqlalchemy import func, select

from core.celery_app import celery_app
from core.database import SessionLocal
from core.logging import logger
from models import (
    GenerationJob,
    JobStatus,
    OutboxStatus,
    Recipient,
    RecipientStatus,
    TransactionalOutbox,
)
from services.job_service import job_service
from services.storage_service import storage_service
from tasks.certificate_tasks import process_certificate_job


@celery_app.task(name="tasks.maintenance_tasks.recover_stalled_jobs")
def recover_stalled_jobs(lease_timeout_seconds: int = 600) -> dict[str, Any]:
    """Identify jobs and recipients stuck in PROCESSING and recover them."""
    logger.info(f"Running stalled job recovery check with lease timeout {lease_timeout_seconds}s")
    db = SessionLocal()
    try:
        recovered = job_service.recover_stalled_recipients(
            db=db,
            lease_timeout_seconds=lease_timeout_seconds,
            storage_svc=storage_service,
        )

        # Check for active jobs that can now be finalized
        active_jobs = (
            db.execute(
                select(GenerationJob).where(
                    GenerationJob.status.in_([JobStatus.PENDING, JobStatus.PROCESSING])
                )
            )
            .scalars()
            .all()
        )

        for j in active_jobs:
            job_service.check_and_finalize_job(db=db, job_id=j.id)

        return {"recovered_recipients": recovered}
    finally:
        db.close()


@celery_app.task(name="tasks.maintenance_tasks.dispatch_pending_outbox")
def dispatch_pending_outbox() -> dict[str, Any]:
    """Publish pending transactional outbox events to Celery task queues."""
    db = SessionLocal()
    dispatched_count = 0
    try:
        pending_events = (
            db.execute(
                select(TransactionalOutbox)
                .where(TransactionalOutbox.status == OutboxStatus.PENDING)
                .limit(100)
            )
            .scalars()
            .all()
        )

        for event in pending_events:
            try:
                if event.event_type == "PROCESS_JOB":
                    job_id_str = event.payload.get("job_id")
                    if job_id_str:
                        process_certificate_job.delay(job_id_str)
                event.status = OutboxStatus.PUBLISHED
                dispatched_count += 1
            except Exception as exc:
                event.retry_count += 1
                event.last_error = str(exc)[:500]
                logger.error(f"Failed to dispatch outbox event {event.id}: {exc}")

        db.commit()
        return {"dispatched_events": dispatched_count}
    finally:
        db.close()


@celery_app.task(name="tasks.maintenance_tasks.reconcile_job_counters")
def reconcile_job_counters(job_id_str: str | None = None) -> dict[str, Any]:
    """Reconcile cached job counters against authoritative recipient rows."""
    db = SessionLocal()
    reconciled: list[dict[str, Any]] = []
    try:
        query = select(GenerationJob)
        if job_id_str:
            query = query.where(GenerationJob.id == uuid.UUID(job_id_str))

        jobs = db.execute(query).scalars().all()
        for job in jobs:
            success_count = (
                db.scalar(
                    select(func.count(Recipient.id)).where(
                        Recipient.job_id == job.id,
                        Recipient.status == RecipientStatus.SUCCESS,
                    )
                )
                or 0
            )

            failed_count = (
                db.scalar(
                    select(func.count(Recipient.id)).where(
                        Recipient.job_id == job.id,
                        Recipient.status == RecipientStatus.FAILED,
                    )
                )
                or 0
            )

            total_count = (
                db.scalar(select(func.count(Recipient.id)).where(Recipient.job_id == job.id)) or 0
            )

            discrepancy = (
                job.successful_records != success_count
                or job.failed_records != failed_count
                or job.total_records != total_count
            )

            if discrepancy:
                logger.warning(
                    f"Reconciling job {job.id} counters: DB=(T:{job.total_records}, S:{job.successful_records}, F:{job.failed_records}) -> Real=(T:{total_count}, S:{success_count}, F:{failed_count})"
                )
                job.total_records = total_count
                job.successful_records = success_count
                job.failed_records = failed_count
                reconciled.append(
                    {
                        "job_id": str(job.id),
                        "total": total_count,
                        "success": success_count,
                        "failed": failed_count,
                    }
                )

        db.commit()
        return {"reconciled_jobs": reconciled}
    finally:
        db.close()
