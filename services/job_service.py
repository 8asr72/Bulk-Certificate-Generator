"""Job service managing transaction boundaries, concurrency claiming, and counter reconciliation."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import settings
from core.exceptions import (
    IdempotencyPayloadMismatchError,
    JobNotFoundError,
    TemplateNotFoundError,
)
from core.logging import logger
from core.security import generate_certificate_number, generate_verification_code
from models import (
    CertificateTemplate,
    GenerationJob,
    JobStatus,
    OutboxStatus,
    Recipient,
    RecipientStatus,
    TransactionalOutbox,
)
from schemas.recipient import RecipientCreate


def utc_now() -> datetime:
    return datetime.now(UTC)


class JobService:
    """Service handling generation job lifecycle and concurrent batch processing."""

    def create_generation_job(
        self,
        db: Session,
        recipients_data: list[RecipientCreate],
        template_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> GenerationJob:
        """Create and persist a bulk generation job and its recipients in a single transaction."""
        # 1. Idempotency Check
        if idempotency_key:
            existing_job = db.execute(
                select(GenerationJob).where(GenerationJob.idempotency_key == idempotency_key)
            ).scalar_one_or_none()

            if existing_job:
                if existing_job.request_hash and existing_job.request_hash != request_hash:
                    raise IdempotencyPayloadMismatchError(idempotency_key)
                logger.info(
                    f"Idempotent replay detected for key '{idempotency_key}': returning job {existing_job.id}"
                )
                return existing_job

        # 2. Template Resolution
        template_version = None
        if template_id:
            template = db.execute(
                select(CertificateTemplate).where(CertificateTemplate.id == template_id)
            ).scalar_one_or_none()
            if not template:
                raise TemplateNotFoundError(str(template_id))
            template_version = template.version
        else:
            # Fetch active default template
            active_template = (
                db.execute(
                    select(CertificateTemplate)
                    .where(CertificateTemplate.is_active.is_(True))
                    .order_by(CertificateTemplate.created_at.desc())
                )
                .scalars()
                .first()
            )
            if active_template:
                template_id = active_template.id
                template_version = active_template.version

        # 3. Create GenerationJob
        job = GenerationJob(
            status=JobStatus.PENDING,
            total_records=len(recipients_data),
            successful_records=0,
            failed_records=0,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            template_id=template_id,
            template_version=template_version,
        )
        db.add(job)
        db.flush()  # Populates job.id

        # 4. Create Recipient records
        for item in recipients_data:
            recipient = Recipient(
                job_id=job.id,
                name=item.name,
                email=item.email,
                normalized_email=item.email.strip().lower(),
                issue_date=item.issue_date or utc_now().date(),
                status=RecipientStatus.PENDING,
                certificate_number=generate_certificate_number(),
                verification_code=generate_verification_code(),
                external_reference=item.external_reference,
            )
            db.add(recipient)

        # 5. Persist Transactional Outbox Event
        outbox_event = TransactionalOutbox(
            event_type="PROCESS_JOB",
            payload={"job_id": str(job.id)},
            status=OutboxStatus.PENDING,
        )
        db.add(outbox_event)

        db.commit()
        db.refresh(job)
        logger.info(f"Created generation job {job.id} with {job.total_records} recipients.")
        return job

    def claim_pending_recipients(
        self,
        db: Session,
        job_id: uuid.UUID,
        batch_size: int = 50,
    ) -> list[Recipient]:
        """Claim a batch of pending recipients safely using row locking."""
        query = (
            select(Recipient)
            .where(Recipient.job_id == job_id, Recipient.status == RecipientStatus.PENDING)
            .limit(batch_size)
        )

        # Apply skip locked for PostgreSQL if supported by dialect
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)

        recipients = db.execute(query).scalars().all()
        if not recipients:
            return []

        now = utc_now()
        for r in recipients:
            r.status = RecipientStatus.PROCESSING
            r.processing_started_at = now
            r.last_attempt_at = now

        db.commit()
        return list(recipients)

    def record_recipient_success(
        self,
        db: Session,
        recipient_id: uuid.UUID,
        certificate_path: str,
    ) -> None:
        """Mark recipient as SUCCESS, update certificate path, and increment job counters."""
        recipient = db.execute(
            select(Recipient).where(Recipient.id == recipient_id)
        ).scalar_one_or_none()

        if not recipient:
            return

        if recipient.status == RecipientStatus.SUCCESS:
            return  # Idempotent skip if already marked success

        recipient.status = RecipientStatus.SUCCESS
        recipient.certificate_path = certificate_path
        recipient.completed_at = utc_now()
        recipient.error_message = None

        job = db.execute(
            select(GenerationJob).where(GenerationJob.id == recipient.job_id)
        ).scalar_one_or_none()

        if job:
            job.successful_records += 1

        db.commit()

    def record_recipient_failure(
        self,
        db: Session,
        recipient_id: uuid.UUID,
        error_message: str,
        is_retryable: bool = False,
    ) -> None:
        """Mark recipient outcome, isolating failures and incrementing job counters."""
        recipient = db.execute(
            select(Recipient).where(Recipient.id == recipient_id)
        ).scalar_one_or_none()

        if not recipient:
            return

        sanitized_error = error_message[:1000]

        if is_retryable and recipient.retry_count < settings.MAX_RETRIES:
            recipient.status = RecipientStatus.PENDING
            recipient.retry_count += 1
            recipient.error_message = f"Retryable error: {sanitized_error}"
        else:
            if recipient.status != RecipientStatus.FAILED:
                recipient.status = RecipientStatus.FAILED
                recipient.completed_at = utc_now()
                recipient.error_message = sanitized_error

                job = db.execute(
                    select(GenerationJob).where(GenerationJob.id == recipient.job_id)
                ).scalar_one_or_none()
                if job:
                    job.failed_records += 1

        db.commit()

    def check_and_finalize_job(self, db: Session, job_id: uuid.UUID) -> GenerationJob:
        """Evaluate job completion and reconcile counters if all recipients are processed."""
        job = db.execute(
            select(GenerationJob).where(GenerationJob.id == job_id)
        ).scalar_one_or_none()

        if not job:
            raise JobNotFoundError(str(job_id))

        # Check pending or currently processing counts
        active_count = (
            db.scalar(
                select(func.count(Recipient.id)).where(
                    Recipient.job_id == job_id,
                    Recipient.status.in_([RecipientStatus.PENDING, RecipientStatus.PROCESSING]),
                )
            )
            or 0
        )

        if active_count == 0:
            # Reconcile authoritative counts from recipient table
            success_count = (
                db.scalar(
                    select(func.count(Recipient.id)).where(
                        Recipient.job_id == job_id,
                        Recipient.status == RecipientStatus.SUCCESS,
                    )
                )
                or 0
            )

            failed_count = (
                db.scalar(
                    select(func.count(Recipient.id)).where(
                        Recipient.job_id == job_id,
                        Recipient.status == RecipientStatus.FAILED,
                    )
                )
                or 0
            )

            job.successful_records = success_count
            job.failed_records = failed_count
            job.completed_at = utc_now()

            if failed_count == 0:
                job.status = JobStatus.COMPLETED
            elif success_count > 0 and failed_count > 0:
                job.status = JobStatus.PARTIAL_SUCCESS
            else:
                job.status = JobStatus.FAILED

            db.commit()
            db.refresh(job)
            logger.info(
                f"Finalized job {job.id}: status={job.status.value}, success={success_count}, failed={failed_count}"
            )

        return job

    def recover_stalled_recipients(
        self,
        db: Session,
        lease_timeout_seconds: int = 600,
        storage_svc: Any = None,
    ) -> int:
        """Find recipients stranded in PROCESSING beyond lease threshold and recover them."""
        cutoff = utc_now() - timedelta(seconds=lease_timeout_seconds)
        stalled = (
            db.execute(
                select(Recipient).where(
                    Recipient.status == RecipientStatus.PROCESSING,
                    Recipient.processing_started_at < cutoff,
                )
            )
            .scalars()
            .all()
        )

        recovered_count = 0
        for r in stalled:
            # Check if artifact was already written
            expected_path = f"certificates/{r.job_id}/{r.id}.pdf"
            if storage_svc and storage_svc.file_exists(expected_path):
                self.record_recipient_success(db, r.id, expected_path)
            elif r.retry_count < settings.MAX_RETRIES:
                r.status = RecipientStatus.PENDING
                r.retry_count += 1
                r.error_message = "Recovered from stalled processing lease expiration."
                db.commit()
            else:
                self.record_recipient_failure(
                    db, r.id, "Processing lease expired and maximum retries exceeded."
                )
            recovered_count += 1

        return recovered_count

    def retry_failed_recipients(self, db: Session, job_id: uuid.UUID) -> int:
        """Reset failed recipients in a job back to PENDING and restart job processing."""
        job = db.execute(
            select(GenerationJob).where(GenerationJob.id == job_id)
        ).scalar_one_or_none()

        if not job:
            raise JobNotFoundError(str(job_id))

        failed_records = (
            db.execute(
                select(Recipient).where(
                    Recipient.job_id == job_id,
                    Recipient.status == RecipientStatus.FAILED,
                )
            )
            .scalars()
            .all()
        )

        if not failed_records:
            return 0

        for r in failed_records:
            r.status = RecipientStatus.PENDING
            r.error_message = None
            r.retry_count += 1

        job.status = JobStatus.PROCESSING
        job.failed_records = 0
        job.completed_at = None

        db.commit()
        logger.info(f"Reset {len(failed_records)} failed recipients for job {job_id} for retry.")
        return len(failed_records)


job_service = JobService()
