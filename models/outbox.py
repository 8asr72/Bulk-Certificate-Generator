"""TransactionalOutbox model for guaranteed at-least-once asynchronous task dispatch."""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import BaseModel


class OutboxStatus(str, enum.Enum):
    """Lifecycle states for transactional outbox events."""

    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class TransactionalOutbox(BaseModel):
    """Reliable outbox event persisted inside the primary database transaction."""

    __tablename__ = "transactional_outbox"

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, name="outbox_status_enum"),
        default=OutboxStatus.PENDING,
        nullable=False,
        index=True,
    )

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
