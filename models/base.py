"""Base SQLAlchemy model with timestamping and identifier mixins."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


class BaseModel(Base):
    """Abstract declarative base with UUID primary key and audit timestamps."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
        nullable=False,
    )

    def to_dict(self) -> dict:
        """Convert model attributes to a plain dictionary."""
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}
