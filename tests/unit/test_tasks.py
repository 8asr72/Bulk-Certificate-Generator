"""Unit and integration tests for Celery certificate tasks, failure isolation, and recovery."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.database
from core.database import Base
from models import GenerationJob, JobStatus, Recipient, RecipientStatus
from services.storage_service import LocalStorageService
from tasks.certificate_tasks import process_certificate_job
from tasks.maintenance_tasks import reconcile_job_counters, recover_stalled_jobs


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Setup isolated database and storage environment for task testing."""
    test_db_url = f"sqlite:///{tmp_path}/test_tasks.db"
    engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Monkeypatch database sessionmaker and storage service
    monkeypatch.setattr(core.database, "SessionLocal", test_session_local)
    import tasks.certificate_tasks
    import tasks.maintenance_tasks

    monkeypatch.setattr(tasks.certificate_tasks, "SessionLocal", test_session_local)
    monkeypatch.setattr(tasks.maintenance_tasks, "SessionLocal", test_session_local)

    test_storage = LocalStorageService(root_path=tmp_path / "storage")
    monkeypatch.setattr(tasks.certificate_tasks, "storage_service", test_storage)
    monkeypatch.setattr(tasks.maintenance_tasks, "storage_service", test_storage)

    db = test_session_local()
    yield {"db": db, "storage": test_storage}
    db.close()


def test_process_certificate_job_full_success(isolated_env):
    """Verify end-to-end successful processing of all recipients in a job."""
    db = isolated_env["db"]
    storage = isolated_env["storage"]

    # 1. Create job with 2 valid recipients
    job = GenerationJob(
        status=JobStatus.PENDING,
        total_records=2,
    )
    db.add(job)
    db.flush()

    r1 = Recipient(
        job_id=job.id,
        name="Diana Ross",
        email="diana@example.com",
        normalized_email="diana@example.com",
        issue_date=date.today(),
        certificate_number="CERT-TASK-001",
        verification_code="token-task-001",
    )
    r2 = Recipient(
        job_id=job.id,
        name="Bruce Wayne",
        email="bruce@example.com",
        normalized_email="bruce@example.com",
        issue_date=date.today(),
        certificate_number="CERT-TASK-002",
        verification_code="token-task-002",
    )
    db.add_all([r1, r2])
    db.commit()

    # 2. Run the task
    result = process_certificate_job(str(job.id))

    assert result["status"] == "COMPLETED"
    assert result["successful_records"] == 2
    assert result["failed_records"] == 0

    # 3. Verify artifacts exist in storage
    db.refresh(job)
    db.refresh(r1)
    db.refresh(r2)

    assert job.status == JobStatus.COMPLETED
    assert r1.status == RecipientStatus.SUCCESS
    assert r2.status == RecipientStatus.SUCCESS
    assert storage.file_exists(r1.certificate_path) is True
    assert storage.file_exists(r2.certificate_path) is True


def test_failure_isolation_per_recipient(isolated_env):
    """Verify a faulty recipient does not crash the batch and isolates failure."""
    db = isolated_env["db"]
    storage = isolated_env["storage"]

    job = GenerationJob(status=JobStatus.PENDING, total_records=2)
    db.add(job)
    db.flush()

    valid_recipient = Recipient(
        job_id=job.id,
        name="Valid Attendee",
        email="valid@example.com",
        normalized_email="valid@example.com",
        issue_date=date.today(),
        certificate_number="CERT-VALID-01",
        verification_code="token-valid-01",
    )
    faulty_recipient = Recipient(
        job_id=job.id,
        name="WayTooLong " * 30,  # Will trigger RenderingError on canvas bounds
        email="faulty@example.com",
        normalized_email="faulty@example.com",
        issue_date=date.today(),
        certificate_number="CERT-FAULT-01",
        verification_code="token-fault-01",
    )
    db.add_all([valid_recipient, faulty_recipient])
    db.commit()

    result = process_certificate_job(str(job.id))

    assert result["status"] == "PARTIAL_SUCCESS"
    assert result["successful_records"] == 1
    assert result["failed_records"] == 1

    db.refresh(valid_recipient)
    db.refresh(faulty_recipient)

    assert valid_recipient.status == RecipientStatus.SUCCESS
    assert storage.file_exists(valid_recipient.certificate_path) is True

    assert faulty_recipient.status == RecipientStatus.FAILED
    assert "Rendering error" in faulty_recipient.error_message


def test_idempotent_task_replay(isolated_env):
    """Verify running the task twice does not corrupt counters or duplicates."""
    db = isolated_env["db"]

    job = GenerationJob(status=JobStatus.PENDING, total_records=1)
    db.add(job)
    db.flush()

    recipient = Recipient(
        job_id=job.id,
        name="Replay Test",
        email="replay@example.com",
        normalized_email="replay@example.com",
        issue_date=date.today(),
        certificate_number="CERT-REPLAY-01",
        verification_code="token-replay-01",
    )
    db.add(recipient)
    db.commit()

    # First run
    process_certificate_job(str(job.id))
    db.refresh(job)
    assert job.successful_records == 1
    assert job.status == JobStatus.COMPLETED

    # Second run (simulating duplicate Celery delivery)
    process_certificate_job(str(job.id))
    db.refresh(job)
    assert job.successful_records == 1  # Not incremented to 2!
    assert job.status == JobStatus.COMPLETED


def test_stalled_job_recovery(isolated_env):
    """Verify abandoned PROCESSING records are safely recovered."""
    db = isolated_env["db"]

    job = GenerationJob(status=JobStatus.PROCESSING, total_records=1)
    db.add(job)
    db.flush()

    stalled_recipient = Recipient(
        job_id=job.id,
        name="Stalled User",
        email="stalled@example.com",
        normalized_email="stalled@example.com",
        issue_date=date.today(),
        status=RecipientStatus.PROCESSING,
        processing_started_at=datetime.now(UTC) - timedelta(minutes=15),
        certificate_number="CERT-STALL-01",
        verification_code="token-stall-01",
        retry_count=0,
    )
    db.add(stalled_recipient)
    db.commit()

    outcome = recover_stalled_jobs(lease_timeout_seconds=600)
    assert outcome["recovered_recipients"] == 1

    db.refresh(stalled_recipient)
    assert stalled_recipient.status == RecipientStatus.PENDING
    assert stalled_recipient.retry_count == 1


def test_reconcile_job_counters(isolated_env):
    """Verify reconcile_job_counters repairs counter discrepancies."""
    db = isolated_env["db"]

    # Artificially create corrupted counters on job
    job = GenerationJob(
        status=JobStatus.COMPLETED,
        total_records=5,
        successful_records=0,  # Corrupted: should be 2
        failed_records=0,
    )
    db.add(job)
    db.flush()

    r1 = Recipient(
        job_id=job.id,
        name="Rec 1",
        email="r1@example.com",
        normalized_email="r1@example.com",
        issue_date=date.today(),
        status=RecipientStatus.SUCCESS,
        certificate_number="CERT-R-1",
        verification_code="code-r-1",
    )
    r2 = Recipient(
        job_id=job.id,
        name="Rec 2",
        email="r2@example.com",
        normalized_email="r2@example.com",
        issue_date=date.today(),
        status=RecipientStatus.SUCCESS,
        certificate_number="CERT-R-2",
        verification_code="code-r-2",
    )
    db.add_all([r1, r2])
    db.commit()

    outcome = reconcile_job_counters(str(job.id))
    assert len(outcome["reconciled_jobs"]) == 1

    db.refresh(job)
    assert job.total_records == 2
    assert job.successful_records == 2
    assert job.failed_records == 0
