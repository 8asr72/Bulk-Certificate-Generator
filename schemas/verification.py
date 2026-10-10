"""Pydantic schemas for certificate authenticity verification."""

from datetime import date, datetime

from pydantic import BaseModel


class VerificationResponse(BaseModel):
    """Public certificate verification result payload."""

    valid: bool
    certificate_number: str | None = None
    recipient_name: str | None = None
    issue_date: date | None = None
    issuer_name: str | None = None
    title: str | None = None
    verification_code: str
    verified_at: datetime
