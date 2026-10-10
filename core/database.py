"""Database engine, session management, and connectivity helpers."""

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from core.config import settings

logger = logging.getLogger("bulk_certificate_platform.database")

# Build engine with connection pooling
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        echo=settings.DEBUG,
    )
else:
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    connect_args["connect_timeout"] = 3
    engine = create_engine(
        db_url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,
        connect_args=connect_args,
        echo=settings.DEBUG,
    )


@event.listens_for(Engine, "connect")
def configure_sqlite_pragmas(dbapi_connection, connection_record):
    """Enable foreign key constraints and WAL journal for SQLite test databases."""
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding an isolated transactional database session."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_db_connection() -> bool:
    """Verify active database connectivity with a lightweight ping query."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"Database connectivity check failed: {exc}")
        return False
