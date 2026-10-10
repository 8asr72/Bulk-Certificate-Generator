"""Recipient model representing an individual certificate target."""

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import BaseModel

if TYPE_CHECKING:
    from models.job import GenerationJob


class RecipientStatus(str, enum.Enum):
    """Lifecycle states for an individual certificate generation attempt."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Recipient(BaseModel):
    """Persistent entity representing an individual certificate recipient."""

    __tablename__ = "recipients"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus, name="recipient_status_enum"),
        default=RecipientStatus.PENDING,
        nullable=False,
        index=True,
    )

    certificate_number: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    verification_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    certificate_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Relationships
    job: Mapped["GenerationJob"] = relationship(
        "GenerationJob",
        back_populates="recipients",
    )
