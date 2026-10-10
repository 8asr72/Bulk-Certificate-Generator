"""Operational health and readiness diagnostics endpoints."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from core.database import check_db_connection

router = APIRouter(tags=["Health"])


@router.get("/health/live", summary="Liveness probe")
def health_live() -> dict[str, str]:
    """Lightweight liveness check verifying the application process is running."""
    return {"status": "live"}


@router.get("/health/ready", summary="Readiness probe")
def health_ready() -> JSONResponse:
    """Readiness probe checking database connectivity without leaking configuration secrets."""
    db_healthy = check_db_connection()

    if not db_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unready",
                "database": "unavailable",
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "ready",
            "database": "healthy",
        },
    )
