"""Application configuration management using Pydantic Settings."""

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors_origins(v: Any) -> list[str]:
    """Parse CORS origins whether supplied as JSON array or comma-separated string."""
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in v.split(",") if item.strip()]
    return ["http://localhost:3000", "http://localhost:8000"]


class Settings(BaseSettings):
    """Platform configuration settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # General App Config
    ENVIRONMENT: Literal["development", "staging", "production", "testing"] = "development"
    DEBUG: bool = False
    APP_NAME: str = "Bulk Certificate Generation Platform"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = Field(
        default="dev-secret-key-change-in-production-only-placeholder-32chars",
        description="Cryptographic secret key for signing tokens and hashes",
    )
    API_KEY: str = Field(
        default="dev-test-api-key-bulk-cert-platform",
        description="Master API Key for privileged management operations",
    )
    REQUIRE_API_KEY: bool = True

    # Database Configuration
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/certificate_db",
        description="PostgreSQL connection string or SQLite for tests",
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Celery & Distributed Task Queue
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_DEFAULT_QUEUE: str = "certificates"
    CELERY_WORKER_CONCURRENCY: int = 4
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # Storage Management
    STORAGE_ROOT: Path = Path("./storage")
    MAX_BATCH_SIZE: int = 5000
    MAX_UPLOAD_SIZE_MB: int = 15

    # Operational Parameters
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 200
    PROCESSING_LEASE_TIMEOUT_SECONDS: int = 600
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_BASE_SECONDS: float = 2.0

    # CORS
    CORS_ORIGINS: Annotated[list[str], BeforeValidator(_parse_cors_origins)] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    @property
    def storage_root_path(self) -> Path:
        """Return the resolved absolute storage root path, creating it if needed."""
        path = self.STORAGE_ROOT.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def certificates_dir(self) -> Path:
        """Directory dedicated to permanently stored certificates."""
        path = self.storage_root_path / "certificates"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def tmp_dir(self) -> Path:
        """Directory dedicated to staging atomic temporary file writes."""
        path = self.storage_root_path / "tmp"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
