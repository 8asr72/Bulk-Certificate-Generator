"""Certificate generation, querying, downloading, and verification endpoints."""

import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependencies import PaginationParams, get_db, require_api_key
from core.exceptions import (
    JobNotFoundError,
    NotFoundError,
    RecipientNotFoundError,
    ValidationFailedError,
)
from core.security import (
    compute_payload_hash,
    sanitize_csv_cell,
    sanitize_filename,
)
from models import GenerationJob, Recipient, RecipientStatus
from schemas.job import (
    AcceptancePolicy,
    BulkCertificateCreateRequest,
    GenerationJobAcceptedResponse,
    JobDetailResponse,
)
from schemas.recipient import RecipientRead
from schemas.verification import VerificationResponse
from services.import_service import import_service
from services.job_service import job_service
from services.storage_service import storage_service
from services.verification_service import verification_service
from services.zip_service import zip_service
from tasks.certificate_tasks import process_certificate_job

router = APIRouter(prefix="/certificates", tags=["Certificates"])


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerationJobAcceptedResponse,
    dependencies=[Depends(require_api_key)],
    summary="Submit bulk certificate generation request via JSON",
)
def generate_certificates_json(
    payload: BulkCertificateCreateRequest,
    db: Session = Depends(get_db),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> GenerationJobAcceptedResponse:
    """Accept a batch of recipient records asynchronously for certificate generation."""
    if not payload.recipients:
        raise ValidationFailedError("Submission must contain at least one recipient.")

    # Compute deterministic payload hash for idempotency validation
    raw_payload_dict = payload.model_dump(mode="json")
    request_hash = compute_payload_hash(raw_payload_dict)

    # Validate recipients and apply acceptance policy
    raw_records = [r.model_dump(mode="json") for r in payload.recipients]
    validation_result = import_service.process_raw_records(
        raw_rows=raw_records,
        acceptance_policy=payload.acceptance_policy,
    )

    # Persist job and recipients in single transaction
    job = job_service.create_generation_job(
        db=db,
        recipients_data=validation_result.valid_recipients,
        template_id=payload.template_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )

    # Enqueue background Celery task
    process_certificate_job.delay(str(job.id))

    return GenerationJobAcceptedResponse(
        job_id=job.id,
        status=job.status,
        total_records=job.total_records,
        accepted_records=len(validation_result.valid_recipients),
        rejected_records=len(validation_result.errors),
        acceptance_policy=payload.acceptance_policy,
        validation_errors=validation_result.errors,
        status_url=f"/api/v1/certificates/jobs/{job.id}",
    )


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerationJobAcceptedResponse,
    dependencies=[Depends(require_api_key)],
    summary="Upload bulk recipients via CSV or XLSX file",
)
def generate_certificates_upload(
    file: UploadFile = File(..., description="CSV or XLSX file"),
    acceptance_policy: AcceptancePolicy = Form("all_or_nothing"),
    template_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_db),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> GenerationJobAcceptedResponse:
    """Parse CSV/XLSX spreadsheets and schedule asynchronous certificate generation."""
    filename = (file.filename or "").lower()
    file_bytes = file.file.read()

    if filename.endswith(".csv"):
        validation_result = import_service.parse_csv(
            file_bytes, acceptance_policy=acceptance_policy
        )
    elif filename.endswith(".xlsx"):
        validation_result = import_service.parse_xlsx(
            file_bytes, acceptance_policy=acceptance_policy
        )
    else:
        raise ValidationFailedError(
            f"Unsupported file format '{file.filename}'. Please upload a valid .csv or .xlsx file."
        )

    request_hash = compute_payload_hash(file_bytes)

    job = job_service.create_generation_job(
        db=db,
        recipients_data=validation_result.valid_recipients,
        template_id=template_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )

    process_certificate_job.delay(str(job.id))

    return GenerationJobAcceptedResponse(
        job_id=job.id,
        status=job.status,
        total_records=job.total_records,
        accepted_records=len(validation_result.valid_recipients),
        rejected_records=len(validation_result.errors),
        acceptance_policy=acceptance_policy,
        validation_errors=validation_result.errors,
        status_url=f"/api/v1/certificates/jobs/{job.id}",
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobDetailResponse,
    summary="Retrieve bulk generation job status and progress",
)
def get_job_status(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    pagination: PaginationParams = Depends(),
) -> JobDetailResponse:
    """Get live job progress, counts, lifecycle timestamps, and paginated recipient results."""
    job = db.execute(select(GenerationJob).where(GenerationJob.id == job_id)).scalar_one_or_none()

    if not job:
        raise JobNotFoundError(str(job_id))

    # Paginate recipients
    recipients = (
        db.execute(
            select(Recipient)
            .where(Recipient.job_id == job_id)
            .order_by(Recipient.created_at)
            .offset(pagination.skip)
            .limit(pagination.limit)
        )
        .scalars()
        .all()
    )

    recipient_items = [RecipientRead.model_validate(r) for r in recipients]

    return JobDetailResponse(
        id=job.id,
        status=job.status,
        total_records=job.total_records,
        successful_records=job.successful_records,
        failed_records=job.failed_records,
        progress_percentage=job.progress_percentage,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        retry_count=job.retry_count,
        last_error=job.last_error,
        template_id=job.template_id,
        template_version=job.template_version,
        recipients=recipient_items,
    )


@router.get(
    "/{recipient_id}/download",
    summary="Download an individual recipient's generated certificate PDF",
)
def download_individual_certificate(
    recipient_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream an individual PDF certificate safely with header containment checks."""
    recipient = db.execute(
        select(Recipient).where(Recipient.id == recipient_id)
    ).scalar_one_or_none()

    if not recipient:
        raise RecipientNotFoundError(str(recipient_id))

    if recipient.status != RecipientStatus.SUCCESS or not recipient.certificate_path:
        raise NotFoundError(
            f"Certificate is not available for download. Current status is {recipient.status.value}."
        )

    if not storage_service.file_exists(recipient.certificate_path):
        raise NotFoundError("The certificate artifact is missing from persistent storage.")

    safe_filename = sanitize_filename(f"{recipient.certificate_number}_{recipient.name}.pdf")

    return StreamingResponse(
        storage_service.stream_file(recipient.certificate_path),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "Cache-Control": "no-cache",
        },
    )


@router.get(
    "/jobs/{job_id}/download-all",
    summary="Download streaming ZIP archive containing all successful certificates",
)
def download_all_certificates(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream on-the-fly ZIP archive containing successful certificates for a job."""
    stream_generator, total_size, zip_filename = zip_service.build_job_archive_stream(
        db=db,
        job_id=job_id,
        storage=storage_service,
    )

    return StreamingResponse(
        stream_generator,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
            "Content-Length": str(total_size),
        },
    )


@router.get(
    "/jobs/{job_id}/failures.csv",
    summary="Export CSV failure report for unsuccessful recipients",
)
def export_job_failures_csv(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Response:
    """Export failure report CSV with formula injection sanitization."""
    job = db.execute(select(GenerationJob).where(GenerationJob.id == job_id)).scalar_one_or_none()

    if not job:
        raise JobNotFoundError(str(job_id))

    failures = (
        db.execute(
            select(Recipient).where(
                Recipient.job_id == job_id,
                Recipient.status == RecipientStatus.FAILED,
            )
        )
        .scalars()
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Recipient ID", "Name", "Email", "Error Message", "Last Attempt"])

    for r in failures:
        # Sanitize against CSV formula injection
        writer.writerow(
            [
                sanitize_csv_cell(str(r.id)),
                sanitize_csv_cell(r.name),
                sanitize_csv_cell(r.email),
                sanitize_csv_cell(r.error_message or "Unknown failure"),
                sanitize_csv_cell(str(r.last_attempt_at or "")),
            ]
        )

    csv_data = output.getvalue().encode("utf-8")
    filename = f"failures_job_{str(job_id)[:8]}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/jobs/{job_id}/retry-failed",
    dependencies=[Depends(require_api_key)],
    summary="Retry all failed recipients for a job",
)
def retry_failed_job_recipients_endpoint(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Reset failed recipients and schedule processing retry."""
    reset_count = job_service.retry_failed_recipients(db=db, job_id=job_id)
    if reset_count > 0:
        process_certificate_job.delay(str(job_id))

    return {
        "job_id": str(job_id),
        "status": "PROCESSING",
        "retried_records": reset_count,
        "message": f"Enqueued retry for {reset_count} failed recipients.",
    }


@router.post(
    "/jobs/{job_id}/retry-stalled",
    dependencies=[Depends(require_api_key)],
    summary="Recover and retry abandoned or stalled recipients for a job",
)
def retry_stalled_job_recipients_endpoint(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Inspect and recover stalled processing claims for a job."""
    recovered = job_service.recover_stalled_recipients(
        db=db, lease_timeout_seconds=600, storage_svc=storage_service
    )
    if recovered > 0:
        process_certificate_job.delay(str(job_id))

    return {
        "job_id": str(job_id),
        "recovered_records": recovered,
        "message": f"Recovered {recovered} stalled recipient claims.",
    }


@router.get(
    "/verify/{verification_code}",
    response_model=VerificationResponse,
    summary="Verify certificate authenticity by verification code",
)
def verify_certificate_endpoint(
    verification_code: str,
    db: Session = Depends(get_db),
) -> VerificationResponse:
    """Public verification lookup for certificate authenticity and issue details."""
    return verification_service.verify_certificate(db=db, verification_code=verification_code)
