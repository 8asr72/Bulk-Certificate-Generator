"""Security tests covering authentication, path traversal, ZIP-slip, CSV injection, and log redaction."""

import io
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.exceptions import StoragePathTraversalError
from core.logging import redact_sensitive_text
from core.security import sanitize_csv_cell, verify_api_key
from models import GenerationJob, JobStatus, Recipient, RecipientStatus
from services.storage_service import LocalStorageService
from services.zip_service import zip_service


def test_constant_time_api_key_verification():
    """Verify constant-time verification accepts exact key and rejects invalid/empty keys."""
    assert verify_api_key("dev-test-api-key-bulk-cert-platform") is True
    assert verify_api_key("wrong-key") is False
    assert verify_api_key("") is False
    assert verify_api_key(None) is False
    assert verify_api_key("dev-test-api-key-bulk-cert-platform ") is True  # Strips whitespace


def test_path_traversal_defense(tmp_path):
    """Verify storage abstraction blocks any path attempting to escape storage root."""
    storage = LocalStorageService(root_path=tmp_path)

    traversal_payloads = [
        "../secret.txt",
        "..\\..\\system.ini",
        "/etc/shadow",
        "certificates/../../../boot.ini",
        "certificates/..\\..\\windows\\win.ini",
    ]

    for payload in traversal_payloads:
        with pytest.raises(StoragePathTraversalError):
            storage.resolve_secure_path(payload)


def test_zip_slip_prevention(tmp_path, db: Session):
    """Verify that filenames added to ZIP archives are sanitized to prevent directory traversal."""
    storage = LocalStorageService(root_path=tmp_path)
    cert_path = "certificates/zip_test/cert1.pdf"
    storage.save_bytes(cert_path, b"%PDF-1.4 Data")

    job = GenerationJob(status=JobStatus.COMPLETED, total_records=1, successful_records=1)
    db.add(job)
    db.flush()

    # Recipient with malicious path characters in name
    malicious_name = "../../etc/passwd"
    recipient = Recipient(
        job_id=job.id,
        name=malicious_name,
        email="bad@example.com",
        normalized_email="bad@example.com",
        issue_date=date.today(),
        status=RecipientStatus.SUCCESS,
        certificate_path=cert_path,
        certificate_number="CERT-SLIP-01",
        verification_code="code-slip-01",
    )
    db.add(recipient)
    db.commit()

    stream_gen, _, _ = zip_service.build_job_archive_stream(db=db, job_id=job.id, storage=storage)
    zip_bytes = b"".join(stream_gen)

    # Read archive and inspect internal member names
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member_name in zf.namelist():
            assert not member_name.startswith("..")
            assert "/" not in member_name
            assert "\\" not in member_name


def test_csv_formula_injection_defense():
    """Verify cells starting with spreadsheet formula triggers are escaped with single quote."""
    dangerous_inputs = [
        "=CMD|' /C calc'!A0",
        "+SUM(A1:A10)",
        "-2+3+cmd|' /C calc'!A0",
        "@SUM(1,2)",
        "\t=1+1",
        "\r=1+1",
    ]

    for input_val in dangerous_inputs:
        sanitized = sanitize_csv_cell(input_val)
        assert sanitized.startswith("'"), f"Formula '{input_val}' was not escaped: '{sanitized}'"

    # Safe inputs must not be modified
    assert sanitize_csv_cell("John Doe") == "John Doe"
    assert sanitize_csv_cell("student@example.com") == "student@example.com"


def test_csv_failure_report_endpoint_escapes_formulas(client: TestClient, db: Session):
    """Verify failures.csv endpoint mitigates formula injection in error reports."""
    job = GenerationJob(status=JobStatus.PARTIAL_SUCCESS, total_records=1, failed_records=1)
    db.add(job)
    db.flush()

    # Injected recipient
    recipient = Recipient(
        job_id=job.id,
        name="=1+1",
        email="+hack@example.com",
        normalized_email="hack@example.com",
        issue_date=date.today(),
        status=RecipientStatus.FAILED,
        error_message="@SUM(error)",
        certificate_number="CERT-INJ-01",
        verification_code="code-inj-01",
    )
    db.add(recipient)
    db.commit()

    resp = client.get(f"/api/v1/certificates/jobs/{job.id}/failures.csv")
    assert resp.status_code == 200
    content = resp.text

    assert "'=1+1" in content
    assert "'+hack@example.com" in content
    assert "'@SUM(error)" in content


def test_secret_redaction_in_structured_logs():
    """Verify credentials and API keys are redacted from log messages."""
    raw_log = 'Generated job with api_key="secret-key-12345" and password=SuperSecretPassword'
    redacted = redact_sensitive_text(raw_log)

    assert "secret-key-12345" not in redacted
    assert "SuperSecretPassword" not in redacted
    assert "***" in redacted
