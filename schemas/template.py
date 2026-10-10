"""Pydantic models for certificate template configuration."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TemplateCreate(BaseModel):
    """Schema for registering a new certificate template."""

    name: str = Field(..., min_length=2, max_length=128, description="Template identifier name")
    title: str = Field(default="Certificate of Completion", max_length=255)
    description_pattern: str = Field(
        default="For successfully completing the certification requirements",
    )
    issuer_name: str = Field(default="Accredited Certification Authority", max_length=255)
    layout_config: dict[str, Any] | None = Field(
        default=None,
        description="Optional custom layout configuration dictionary",
    )


class TemplateRead(BaseModel):
    """Schema for reading certificate template details."""

    id: uuid.UUID
    name: str
    version: int
    is_active: bool
    title: str
    description_pattern: str
    issuer_name: str
    background_asset_path: str | None = None
    layout_config: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
