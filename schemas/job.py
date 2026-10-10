"""Pydantic models for bulk generation jobs, requests, and status queries."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from models.job import JobStatus
from schemas.recipient import RecipientCreate, RecipientRead

AcceptancePolicy = Literal["all_or_nothing", "partial_acceptance"]


class BulkCertificateCreateRequest(BaseModel):
    """Schema for direct JSON bulk recipient generation submission."""

    template_id: uuid.UUID | None = Field(default=None, description="Optional target template UUID")
    acceptance_policy: AcceptancePolicy = Field(
        default="all_or_nothing",
        description="Whether to reject entire batch on single invalid row or accept valid ones",
    )
    recipients: list[RecipientCreate] = Field(
        ...,
        min_length=1,
        description="List of recipient records to process",
    )


class GenerationJobAcceptedResponse(BaseModel):
    """Response returned upon successful acceptance of asynchronous generation job."""

    job_id: uuid.UUID
    status: JobStatus
    total_records: int
    accepted_records: int
    rejected_records: int
    acceptance_policy: AcceptancePolicy
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    status_url: str


class JobDetailResponse(BaseModel):
    """Full lifecycle view of a bulk generation job."""

    id: uuid.UUID
    status: JobStatus
    total_records: int
    successful_records: int
    failed_records: int
    progress_percentage: float
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    last_error: str | None = None
    template_id: uuid.UUID | None = None
    template_version: int | None = None
    recipients: list[RecipientRead] = Field(default_factory=list)
