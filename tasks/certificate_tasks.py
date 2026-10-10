"""Celery background tasks for asynchronous certificate generation and failure isolation."""

import uuid
from typing import Any

from sqlalchemy import select

from core.celery_app import celery_app
from core.database import SessionLocal
from core.exceptions import RenderingError
from core.logging import job_id_ctx, logger, recipient_id_ctx
from models import CertificateTemplate, GenerationJob, JobStatus
from services.certificate_service import CertificateRenderer
from services.job_service import job_service
from services.storage_service import storage_service


@celery_app.task(
    bind=True,
    name="tasks.certificate_tasks.process_certificate_job",
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
)
def process_certificate_job(self: Any, job_id_str: str) -> dict[str, Any]:
    """Process all pending recipients for a generation job in bounded batches."""
    job_id = uuid.UUID(job_id_str)
    job_id_token = job_id_ctx.set(str(job_id))

    logger.info(f"Initiating certificate processing for job {job_id}")

    db = SessionLocal()
    try:
        # 1. Update job state to PROCESSING if PENDING
        job = db.execute(
            select(GenerationJob).where(GenerationJob.id == job_id)
        ).scalar_one_or_none()

        if not job:
            logger.error(f"Job {job_id} not found for task processing.")
            return {"status": "NOT_FOUND", "job_id": str(job_id)}

        if job.status == JobStatus.PENDING:
            job.status = JobStatus.PROCESSING
            db.commit()

        # 2. Resolve template layout
        layout_config = None
        title = "Certificate of Completion"
        description = "For demonstrating proficiency and meeting all certification criteria"
        issuer_name = "Accredited Certification Authority"

        if job.template_id:
            template = db.execute(
                select(CertificateTemplate).where(CertificateTemplate.id == job.template_id)
            ).scalar_one_or_none()
            if template:
                layout_config = template.layout_config
                title = template.title
                description = template.description_pattern
                issuer_name = template.issuer_name

        renderer = CertificateRenderer(layout_config=layout_config)

        # 3. Process recipients in bounded batches
        batch_size = 50
        while True:
            claimed_recipients = job_service.claim_pending_recipients(
                db=db, job_id=job_id, batch_size=batch_size
            )
            if not claimed_recipients:
                break

            logger.info(
                f"Processing claimed batch of {len(claimed_recipients)} recipients for job {job_id}"
            )

            for recipient in claimed_recipients:
                recipient_token = recipient_id_ctx.set(str(recipient.id))
                try:
                    # Deterministic artifact path: certificates/{job_id}/{recipient_id}.pdf
                    artifact_path = f"certificates/{job_id}/{recipient.id}.pdf"

                    # Check if file already exists (idempotent replay)
                    if not storage_service.file_exists(artifact_path):
                        # Render certificate outside long-lived DB transaction
                        pdf_bytes = renderer.render(
                            recipient_name=recipient.name,
                            issue_date=recipient.issue_date,
                            certificate_number=recipient.certificate_number,
                            verification_code=recipient.verification_code,
                            title=title,
                            description=description,
                            issuer_name=issuer_name,
                        )
                        # Persist atomically to disk
                        storage_service.save_bytes(artifact_path, pdf_bytes)

                    # Update recipient status transactionally
                    job_service.record_recipient_success(
                        db=db, recipient_id=recipient.id, certificate_path=artifact_path
                    )
                except RenderingError as r_err:
                    logger.warning(
                        f"Rendering failure for recipient {recipient.id} ('{recipient.name}'): {r_err}"
                    )
                    job_service.record_recipient_failure(
                        db=db,
                        recipient_id=recipient.id,
                        error_message=f"Rendering error: {r_err}",
                        is_retryable=False,
                    )
                except Exception as exc:
                    logger.error(
                        f"Unexpected error processing recipient {recipient.id}: {exc}",
                        exc_info=True,
                    )
                    job_service.record_recipient_failure(
                        db=db,
                        recipient_id=recipient.id,
                        error_message=f"Processing exception: {exc}",
                        is_retryable=False,
                    )
                finally:
                    recipient_id_ctx.reset(recipient_token)

        # 4. Check completion and finalize job status
        finalized_job = job_service.check_and_finalize_job(db=db, job_id=job_id)
        return {
            "job_id": str(finalized_job.id),
            "status": finalized_job.status.value,
            "successful_records": finalized_job.successful_records,
            "failed_records": finalized_job.failed_records,
        }
    except Exception as exc:
        logger.error(f"Job processing task failed for job {job_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc) from exc
    finally:
        db.close()
        job_id_ctx.reset(job_id_token)


@celery_app.task(name="tasks.certificate_tasks.retry_failed_job_recipients")
def retry_failed_job_recipients(job_id_str: str) -> dict[str, Any]:
    """Reset failed recipients in a job and enqueue reprocessing."""
    job_id = uuid.UUID(job_id_str)
    db = SessionLocal()
    try:
        reset_count = job_service.retry_failed_recipients(db=db, job_id=job_id)
        if reset_count > 0:
            process_certificate_job.delay(job_id_str)
        return {"job_id": job_id_str, "reset_recipients": reset_count}
    finally:
        db.close()
