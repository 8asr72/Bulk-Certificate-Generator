"""Master FastAPI application factory with middlewares, error handlers, and routers."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.v1.endpoints import health
from api.v1.router import api_router
from core.config import settings
from core.exceptions import (
    IdempotencyPayloadMismatchError,
    InvalidTemplateError,
    NotFoundError,
    PlatformException,
    RenderingError,
    StoragePathTraversalError,
    UnauthorizedError,
    ValidationFailedError,
)
from core.logging import correlation_id_ctx, logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context managing startup and shutdown routines."""
    setup_logging()
    logger.info(f"Starting {settings.APP_NAME} in '{settings.ENVIRONMENT}' environment.")
    if settings.DATABASE_URL.startswith("sqlite"):
        import models  # noqa: F401
        from core.database import Base, SessionLocal, engine
        from models import DEFAULT_LAYOUT_CONFIG, CertificateTemplate

        Base.metadata.create_all(bind=engine)
        logger.info("Local SQLite database schema initialized.")

        db = SessionLocal()
        try:
            if not db.query(CertificateTemplate).first():
                tpl = CertificateTemplate(
                    name="Executive Leadership",
                    version=1,
                    is_active=True,
                    title="Certificate of Executive Leadership",
                    description_pattern="For demonstrated visionary leadership and organizational excellence",
                    issuer_name="Global Executive Academy",
                    layout_config=DEFAULT_LAYOUT_CONFIG,
                )
                db.add(tpl)
                db.commit()
                logger.info("Default 'Executive Leadership' certificate template seeded.")
        finally:
            db.close()
    yield
    logger.info("Application shutdown initiated.")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Production-Ready Asynchronous Bulk Certificate Generation Platform",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# 1. CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# 2. Correlation ID & Distributed Tracing Middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
    token = correlation_id_ctx.set(cid)
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response
    finally:
        correlation_id_ctx.reset(token)


# 3. Domain Exception Handlers
@app.exception_handler(UnauthorizedError)
async def unauthorized_handler(request: Request, exc: UnauthorizedError):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": exc.code, "message": exc.message},
    )


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": exc.code, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(IdempotencyPayloadMismatchError)
async def idempotency_conflict_handler(request: Request, exc: IdempotencyPayloadMismatchError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": exc.code, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(StoragePathTraversalError)
async def path_traversal_handler(request: Request, exc: StoragePathTraversalError):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": exc.code, "message": exc.message},
    )


@app.exception_handler(ValidationFailedError)
async def validation_failed_handler(request: Request, exc: ValidationFailedError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": exc.code, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(InvalidTemplateError)
async def invalid_template_handler(request: Request, exc: InvalidTemplateError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": exc.code, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(RenderingError)
async def rendering_error_handler(request: Request, exc: RenderingError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": exc.code, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(PlatformException)
async def platform_exception_handler(request: Request, exc: PlatformException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": exc.code, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled system error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred. Please contact support.",
        },
    )


# 4. Attach Routers
app.include_router(health.router)
app.include_router(api_router, prefix=settings.API_V1_STR)

# 5. Static Files & Web Dashboard
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", summary="Web Dashboard UI", include_in_schema=False)
def serve_dashboard():
    """Serve the interactive web studio dashboard."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        content={
            "message": "Bulk Certificate Generation Platform API is active. Visit /docs for Swagger UI."
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
