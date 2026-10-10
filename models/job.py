"""GenerationJob model representing a batch certificate generation request."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import BaseModel

if TYPE_CHECKING:
    from models.recipient import Recipient
    from models.template import CertificateTemplate


class JobStatus(str, enum.Enum):
    """Lifecycle states for a bulk certificate generation job."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


class GenerationJob(BaseModel):
    """Persistent job entity tracking bulk recipient generation."""

    __tablename__ = "generation_jobs"
    __table_args__ = (
        CheckConstraint("total_records >= 0", name="chk_total_records_nonnegative"),
        CheckConstraint("successful_records >= 0", name="chk_successful_records_nonnegative"),
        CheckConstraint("failed_records >= 0", name="chk_failed_records_nonnegative"),
    )

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status_enum"),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )

    total_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("certificate_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    template: Mapped["CertificateTemplate | None"] = relationship(
        "CertificateTemplate",
        back_populates="jobs",
    )
    recipients: Mapped[list["Recipient"]] = relationship(
        "Recipient",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Recipient.created_at",
    )

    @property
    def progress_percentage(self) -> float:
        """Compute safe progress percentage handling zero totals gracefully."""
        if self.total_records <= 0:
            return 0.0
        processed = self.successful_records + self.failed_records
        return round(min(100.0, max(0.0, (processed / self.total_records) * 100.0)), 2)

    @property
    def is_terminal(self) -> bool:
        """Check whether the job has reached a final state."""
        return self.status in {
            JobStatus.COMPLETED,
            JobStatus.PARTIAL_SUCCESS,
            JobStatus.FAILED,
        }
