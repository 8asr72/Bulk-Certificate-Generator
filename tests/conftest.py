"""Shared test fixtures for database, test client, storage, and mock background workers."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.dependencies import get_db
from core.config import settings
from core.database import Base
from main import app
from models import DEFAULT_LAYOUT_CONFIG, CertificateTemplate
from services.storage_service import LocalStorageService


@pytest.fixture(scope="session")
def test_engine(tmp_path_factory):
    """Create a persistent SQLite test database for API tests."""
    temp_dir = tmp_path_factory.mktemp("db")
    db_file = temp_dir / "test_api.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db(test_engine) -> Generator[Session, None, None]:
    """Provide a transactional database session rolled back after each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, expire_on_commit=False)
    session = session_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db: Session, test_engine, tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    """Provide a configured TestClient with mocked database and storage."""

    # Override get_db dependency
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Monkeypatch core database engine and check_db_connection
    import core.database

    monkeypatch.setattr(core.database, "engine", test_engine)
    monkeypatch.setattr(core.database, "check_db_connection", lambda: True)

    # Isolate storage service
    test_storage = LocalStorageService(root_path=tmp_path / "test_storage")
    import api.v1.endpoints.certificates
    import services.storage_service

    monkeypatch.setattr(services.storage_service, "storage_service", test_storage)
    monkeypatch.setattr(api.v1.endpoints.certificates, "storage_service", test_storage)

    # Disable eager celery failure so API handles enqueue cleanly
    import tasks.certificate_tasks

    monkeypatch.setattr(
        tasks.certificate_tasks.process_certificate_job,
        "delay",
        lambda *args, **kwargs: None,
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Provide valid authentication headers."""
    return {"X-API-Key": settings.API_KEY}


@pytest.fixture
def seed_default_template(db: Session) -> CertificateTemplate:
    """Seed a default active certificate template into the database."""
    template = CertificateTemplate(
        name="Standard Certificate",
        version=1,
        is_active=True,
        title="Certificate of Achievement",
        description_pattern="For completing all program requirements",
        issuer_name="Accredited Academic Board",
        layout_config=DEFAULT_LAYOUT_CONFIG,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template
