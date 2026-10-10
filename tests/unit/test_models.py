"""Unit tests for SQLAlchemy models, constraints, and relationships."""

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from core.database import Base
from models import (
    DEFAULT_LAYOUT_CONFIG,
    CertificateTemplate,
    GenerationJob,
    JobStatus,
    OutboxStatus,
    Recipient,
    RecipientStatus,
    TransactionalOutbox,
)


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session for unit tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_certificate_template_defaults_and_creation(db_session: Session):
    """Verify CertificateTemplate creation with defaults and layout JSON."""
    template = CertificateTemplate(
        name="Graduate Degree",
        version=1,
        title="Bachelor of Science",
        issuer_name="Global University",
        layout_config=DEFAULT_LAYOUT_CONFIG,
    )
    db_session.add(template)
    db_session.commit()

    assert template.id is not None
    assert template.is_active is True
    assert template.layout_config["page_size"] == "A4_LANDSCAPE"
    assert template.created_at is not None


def test_generation_job_progress_calculation(db_session: Session):
    """Verify GenerationJob progress calculation handles zero and active counts safely."""
    job = GenerationJob(
        status=JobStatus.PENDING,
        total_records=0,
        successful_records=0,
        failed_records=0,
    )
    assert job.progress_percentage == 0.0

    job.total_records = 100
    job.successful_records = 25
    job.failed_records = 5
    assert job.progress_percentage == 30.0

    job.successful_records = 95
    job.failed_records = 5
    assert job.progress_percentage == 100.0


def test_recipient_relationship_and_uniqueness(db_session: Session):
    """Verify Recipient relationships, unique certificate numbers, and verification codes."""
    job = GenerationJob(
        status=JobStatus.PROCESSING,
        total_records=1,
    )
    db_session.add(job)
    db_session.commit()

    recipient = Recipient(
        job_id=job.id,
        name="Jane Doe",
        email="jane.doe@example.com",
        normalized_email="jane.doe@example.com",
        issue_date=date(2026, 5, 20),
        status=RecipientStatus.PENDING,
        certificate_number="CERT-2026-TEST-001",
        verification_code="token-safe-12345",
    )
    db_session.add(recipient)
    db_session.commit()

    assert recipient.id is not None
    assert recipient.job.id == job.id
    assert len(job.recipients) == 1

    # Verify duplicate certificate number raises IntegrityError
    duplicate_recipient = Recipient(
        job_id=job.id,
        name="Another Person",
        email="another@example.com",
        normalized_email="another@example.com",
        issue_date=date(2026, 5, 20),
        certificate_number="CERT-2026-TEST-001",
        verification_code="token-safe-99999",
    )
    db_session.add(duplicate_recipient)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_transactional_outbox_event(db_session: Session):
    """Verify TransactionalOutbox event lifecycle attributes."""
    outbox = TransactionalOutbox(
        event_type="PROCESS_JOB",
        payload={"job_id": str(uuid.uuid4())},
        status=OutboxStatus.PENDING,
    )
    db_session.add(outbox)
    db_session.commit()

    assert outbox.id is not None
    assert outbox.status == OutboxStatus.PENDING
    assert outbox.retry_count == 0
