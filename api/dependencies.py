"""FastAPI endpoint dependencies for database sessions, authentication, and pagination."""

from collections.abc import Generator

from fastapi import Header
from sqlalchemy.orm import Session

from core.config import settings
from core.database import SessionLocal
from core.exceptions import UnauthorizedError
from core.security import verify_api_key


def get_db() -> Generator[Session, None, None]:
    """Dependency yielding a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Dependency enforcing API key authentication via constant-time comparison."""
    if not settings.REQUIRE_API_KEY:
        return
    if not verify_api_key(x_api_key):
        raise UnauthorizedError("Invalid or missing API key in 'X-API-Key' header.")


class PaginationParams:
    """Standard pagination parameter bounds."""

    def __init__(self, skip: int = 0, limit: int = 50):
        self.skip = max(0, skip)
        self.limit = min(settings.MAX_PAGE_SIZE, max(1, limit))
