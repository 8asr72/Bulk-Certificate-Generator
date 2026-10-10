"""Pydantic models for recipient records, validation, and serialization."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.recipient import RecipientStatus


class RecipientBase(BaseModel):
    """Base fields for certificate recipients."""

    name: str = Field(..., min_length=1, max_length=255, description="Full name of recipient")
    email: EmailStr = Field(..., description="Valid recipient email address")
    issue_date: date | None = Field(
        default=None, description="Issue date (defaults to current date)"
    )
    external_reference: str | None = Field(
        default=None, max_length=255, description="External student/attendee identifier"
    )


class RecipientCreate(RecipientBase):
    """Schema for submitting a single recipient within bulk submission."""

    pass


class RecipientRead(RecipientBase):
    """Detailed view schema for recipient generation outcomes."""

    id: uuid.UUID
    job_id: uuid.UUID
    normalized_email: str
    issue_date: date
    status: RecipientStatus
    certificate_number: str
    verification_code: str
    certificate_path: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
