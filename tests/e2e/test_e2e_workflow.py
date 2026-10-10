"""End-to-end workflow test verifying complete bulk certificate lifecycle."""

import io
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.storage_service import LocalStorageService
from tasks.certificate_tasks import process_certificate_job


def test_full_e2e_lifecycle(
    client: TestClient, db: Session, auth_headers: dict[str, str], tmp_path, monkeypatch
):
    """Verify complete lifecycle: submission, background rendering, status, download, zip, and verification."""
    # 1. Setup isolated storage and database sessionmaker
    storage = LocalStorageService(root_path=tmp_path / "e2e_storage")
    import api.v1.endpoints.certificates
    import services.storage_service
    import tasks.certificate_tasks

    monkeypatch.setattr(services.storage_service, "storage_service", storage)
    monkeypatch.setattr(api.v1.endpoints.certificates, "storage_service", storage)
    monkeypatch.setattr(tasks.certificate_tasks, "storage_service", storage)

    # Ensure background task uses the test database session factory
    def test_sessionmaker():
        return db

    monkeypatch.setattr(tasks.certificate_tasks, "SessionLocal", test_sessionmaker)

    # 2. Submit Bulk Generation Job with valid and edge-case names
    submission_payload = {
        "recipients": [
            {
                "name": "Jane Cooper",
                "email": "jane.cooper@example.com",
                "issue_date": "2026-08-10",
                "external_reference": "STU-001",
            },
            {
                "name": "Alexander Maximillian Montgomery-Featherstone",  # Long name triggers font scaling
                "email": "alexander@example.com",
                "issue_date": "2026-08-10",
                "external_reference": "STU-002",
            },
        ],
        "acceptance_policy": "all_or_nothing",
    }

    create_resp = client.post(
        "/api/v1/certificates/generate",
        json=submission_payload,
        headers=auth_headers,
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["job_id"]

    # 3. Execute background processing task
    task_result = process_certificate_job(job_id)
    assert task_result["status"] == "COMPLETED"
    assert task_result["successful_records"] == 2
    assert task_result["failed_records"] == 0

    # 4. Query Job Status Endpoint
    status_resp = client.get(f"/api/v1/certificates/jobs/{job_id}")
    assert status_resp.status_code == 200
    job_data = status_resp.json()
    assert job_data["status"] == "COMPLETED"
    assert job_data["progress_percentage"] == 100.0
    assert len(job_data["recipients"]) == 2

    first_recipient = job_data["recipients"][0]
    rec_id = first_recipient["id"]
    verification_code = first_recipient["verification_code"]
    cert_number = first_recipient["certificate_number"]

    # 5. Download Individual Certificate PDF
    dl_resp = client.get(f"/api/v1/certificates/{rec_id}/download")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["Content-Type"] == "application/pdf"
    assert dl_resp.content.startswith(b"%PDF-")

    # 6. Download Streaming ZIP Archive of All Certificates
    zip_resp = client.get(f"/api/v1/certificates/jobs/{job_id}/download-all")
    assert zip_resp.status_code == 200
    assert zip_resp.headers["Content-Type"] == "application/zip"

    # Verify ZIP structure and member integrity
    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        namelist = zf.namelist()
        assert len(namelist) == 2
        for name in namelist:
            assert name.endswith(".pdf")
            member_bytes = zf.read(name)
            assert member_bytes.startswith(b"%PDF-")

    # 7. Public Certificate Verification Endpoint
    verify_resp = client.get(f"/api/v1/certificates/verify/{verification_code}")
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["valid"] is True
    assert verify_data["certificate_number"] == cert_number
    assert verify_data["recipient_name"] == "Jane Cooper"
