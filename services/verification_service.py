"""Public certificate authenticity verification service."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import CertificateTemplate, GenerationJob, Recipient, RecipientStatus
from schemas.verification import VerificationResponse


def utc_now() -> datetime:
    return datetime.now(UTC)


class VerificationService:
    """Validates public authenticity and credentials of issued certificates."""

    def verify_certificate(self, db: Session, verification_code: str) -> VerificationResponse:
        """Lookup certificate by public verification code and return verified metadata."""
        clean_code = verification_code.strip()
        recipient = db.execute(
            select(Recipient).where(Recipient.verification_code == clean_code)
        ).scalar_one_or_none()

        if not recipient or recipient.status != RecipientStatus.SUCCESS:
            return VerificationResponse(
                valid=False,
                verification_code=clean_code,
                verified_at=utc_now(),
            )

        title = "Certificate of Completion"
        issuer_name = "Accredited Certification Authority"

        # Check associated job and template
        job = db.execute(
            select(GenerationJob).where(GenerationJob.id == recipient.job_id)
        ).scalar_one_or_none()

        if job and job.template_id:
            template = db.execute(
                select(CertificateTemplate).where(CertificateTemplate.id == job.template_id)
            ).scalar_one_or_none()
            if template:
                title = template.title
                issuer_name = template.issuer_name

        return VerificationResponse(
            valid=True,
            certificate_number=recipient.certificate_number,
            recipient_name=recipient.name,
            issue_date=recipient.issue_date,
            issuer_name=issuer_name,
            title=title,
            verification_code=clean_code,
            verified_at=utc_now(),
        )


verification_service = VerificationService()
