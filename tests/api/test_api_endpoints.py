"""API endpoint tests covering creation, idempotency, querying, downloads, and errors."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import GenerationJob, JobStatus, Recipient, RecipientStatus
from services.storage_service import LocalStorageService


def test_health_endpoints(client: TestClient):
    """Verify liveness and readiness probes return 200."""
    live_resp = client.get("/health/live")
    assert live_resp.status_code == 200
    assert live_resp.json() == {"status": "live"}

    ready_resp = client.get("/health/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "ready"


def test_docs_and_openapi(client: TestClient):
    """Verify OpenAPI specification and interactive Swagger docs are exposed."""
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200

    openapi_resp = client.get("/openapi.json")
    assert openapi_resp.status_code == 200
    assert "paths" in openapi_resp.json()


def test_generate_certificates_authentication(client: TestClient):
    """Verify endpoints require X-API-Key and reject invalid keys."""
    payload = {"recipients": [{"name": "No Auth User", "email": "noauth@example.com"}]}

    # Missing API key
    unauth_resp = client.post("/api/v1/certificates/generate", json=payload)
    assert unauth_resp.status_code == 401

    # Invalid API key
    bad_key_resp = client.post(
        "/api/v1/certificates/generate",
        json=payload,
        headers={"X-API-Key": "invalid-secret-key"},
    )
    assert bad_key_resp.status_code == 401


def test_generate_certificates_json_success(
    client: TestClient, auth_headers: dict[str, str], seed_default_template
):
    """Verify successful submission of bulk JSON recipients returns HTTP 202."""
    payload = {
        "recipients": [
            {"name": "Alice Wonderland", "email": "alice@example.com"},
            {"name": "Bob Builder", "email": "bob@example.com"},
        ],
        "acceptance_policy": "all_or_nothing",
    }

    resp = client.post(
        "/api/v1/certificates/generate",
        json=payload,
        headers=auth_headers,
    )

    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "PENDING"
    assert data["total_records"] == 2
    assert data["accepted_records"] == 2
    assert data["rejected_records"] == 0
    assert data["status_url"].startswith("/api/v1/certificates/jobs/")


def test_idempotent_duplicate_request(
    client: TestClient, auth_headers: dict[str, str], seed_default_template
):
    """Verify repeating identical request with same Idempotency-Key returns existing job."""
    idempotency_key = "unique-client-key-12345"
    headers = {**auth_headers, "Idempotency-Key": idempotency_key}

    payload = {"recipients": [{"name": "Clara Oswald", "email": "clara@example.com"}]}

    # First submission
    resp1 = client.post("/api/v1/certificates/generate", json=payload, headers=headers)
    assert resp1.status_code == 202
    job_id_1 = resp1.json()["job_id"]

    # Identical replay
    resp2 = client.post("/api/v1/certificates/generate", json=payload, headers=headers)
    assert resp2.status_code == 202
    assert resp2.json()["job_id"] == job_id_1


def test_idempotency_payload_mismatch_conflict(
    client: TestClient, auth_headers: dict[str, str], seed_default_template
):
    """Verify reusing Idempotency-Key with different payload triggers HTTP 409 Conflict."""
    idempotency_key = "conflict-test-key-999"
    headers = {**auth_headers, "Idempotency-Key": idempotency_key}

    payload1 = {"recipients": [{"name": "Original Name", "email": "original@example.com"}]}
    payload2 = {"recipients": [{"name": "Tampered Name", "email": "tampered@example.com"}]}

    resp1 = client.post("/api/v1/certificates/generate", json=payload1, headers=headers)
    assert resp1.status_code == 202

    # Second submission with different payload
    resp2 = client.post("/api/v1/certificates/generate", json=payload2, headers=headers)
    assert resp2.status_code == 409
    assert resp2.json()["error"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"


def test_get_job_status_and_pagination(client: TestClient, db: Session):
    """Verify retrieving job status, progress percentage, and recipient list."""
    job = GenerationJob(
        status=JobStatus.COMPLETED,
        total_records=10,
        successful_records=8,
        failed_records=2,
    )
    db.add(job)
    db.flush()

    for i in range(5):
        r = Recipient(
            job_id=job.id,
            name=f"Student {i}",
            email=f"student{i}@example.com",
            normalized_email=f"student{i}@example.com",
            issue_date=date.today(),
            status=RecipientStatus.SUCCESS if i < 4 else RecipientStatus.FAILED,
            certificate_number=f"CERT-PAGE-{i}",
            verification_code=f"code-page-{i}",
        )
        db.add(r)
    db.commit()

    resp = client.get(f"/api/v1/certificates/jobs/{job.id}?skip=0&limit=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(job.id)
    assert data["total_records"] == 10
    assert data["progress_percentage"] == 100.0
    assert len(data["recipients"]) == 3


def test_download_individual_certificate(client: TestClient, db: Session, monkeypatch):
    """Verify downloading generated PDF certificate stream."""
    import services.storage_service

    storage: LocalStorageService = services.storage_service.storage_service

    rel_path = "certificates/download_job/cert_download.pdf"
    storage.save_bytes(rel_path, b"%PDF-1.4 Mock PDF Content")

    job = GenerationJob(status=JobStatus.COMPLETED, total_records=1, successful_records=1)
    db.add(job)
    db.flush()

    recipient = Recipient(
        job_id=job.id,
        name="Download Tester",
        email="download@example.com",
        normalized_email="download@example.com",
        issue_date=date.today(),
        status=RecipientStatus.SUCCESS,
        certificate_path=rel_path,
        certificate_number="CERT-DL-001",
        verification_code="token-dl-001",
    )
    db.add(recipient)
    db.commit()

    resp = client.get(f"/api/v1/certificates/{recipient.id}/download")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert resp.content == b"%PDF-1.4 Mock PDF Content"


def test_download_pending_certificate_returns_404(client: TestClient, db: Session):
    """Verify downloading pending certificate returns 404."""
    job = GenerationJob(status=JobStatus.PROCESSING, total_records=1)
    db.add(job)
    db.flush()

    recipient = Recipient(
        job_id=job.id,
        name="Pending User",
        email="pending@example.com",
        normalized_email="pending@example.com",
        issue_date=date.today(),
        status=RecipientStatus.PENDING,
        certificate_number="CERT-PEND-01",
        verification_code="token-pend-01",
    )
    db.add(recipient)
    db.commit()

    resp = client.get(f"/api/v1/certificates/{recipient.id}/download")
    assert resp.status_code == 404


def test_verify_certificate_endpoint(client: TestClient, db: Session):
    """Verify public verification endpoint returns authentic certificate details."""
    job = GenerationJob(status=JobStatus.COMPLETED, total_records=1, successful_records=1)
    db.add(job)
    db.flush()

    recipient = Recipient(
        job_id=job.id,
        name="Verified Graduate",
        email="grad@example.com",
        normalized_email="grad@example.com",
        issue_date=date(2026, 3, 15),
        status=RecipientStatus.SUCCESS,
        certificate_number="CERT-VERIFY-100",
        verification_code="public-code-xyz123",
    )
    db.add(recipient)
    db.commit()

    # Valid code
    resp = client.get("/api/v1/certificates/verify/public-code-xyz123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["certificate_number"] == "CERT-VERIFY-100"
    assert data["recipient_name"] == "Verified Graduate"

    # Invalid code
    bad_resp = client.get("/api/v1/certificates/verify/nonexistent-code")
    assert bad_resp.status_code == 200
    assert bad_resp.json()["valid"] is False


def test_template_crud_endpoints(client: TestClient, auth_headers: dict[str, str]):
    """Verify creating, listing, and retrieving templates."""
    create_payload = {
        "name": "Honors Diploma",
        "title": "Diploma of Highest Honors",
        "issuer_name": "State University",
    }

    create_resp = client.post("/api/v1/templates", json=create_payload, headers=auth_headers)
    assert create_resp.status_code == 201
    tpl_data = create_resp.json()
    assert tpl_data["name"] == "Honors Diploma"
    assert tpl_data["version"] == 1
    tpl_id = tpl_data["id"]

    # List templates
    list_resp = client.get("/api/v1/templates")
    assert list_resp.status_code == 200
    assert any(t["id"] == tpl_id for t in list_resp.json())

    # Get single template
    get_resp = client.get(f"/api/v1/templates/{tpl_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Diploma of Highest Honors"

    # Activate template
    act_resp = client.put(f"/api/v1/templates/{tpl_id}/activate", headers=auth_headers)
    assert act_resp.status_code == 200
    assert act_resp.json()["is_active"] is True


def test_upload_certificates_csv(
    client: TestClient, auth_headers: dict[str, str], seed_default_template
):
    """Verify CSV file upload endpoint."""
    csv_bytes = b"name,email\nSam Winchester,sam@example.com\nDean Winchester,dean@example.com\n"
    files = {"file": ("students.csv", csv_bytes, "text/csv")}

    resp = client.post(
        "/api/v1/certificates/upload",
        files=files,
        data={"acceptance_policy": "all_or_nothing"},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    assert resp.json()["total_records"] == 2
    assert resp.json()["status"] == "PENDING"


def test_upload_invalid_extension(client: TestClient, auth_headers: dict[str, str]):
    """Verify uploading an unsupported file format returns 422."""
    files = {"file": ("unsupported.txt", b"plain text", "text/plain")}
    resp = client.post(
        "/api/v1/certificates/upload",
        files=files,
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "Unsupported file format" in resp.json()["message"]


def test_download_all_empty_job_returns_404(client: TestClient, db: Session):
    """Verify downloading archive for job with no successful certificates returns 404."""
    job = GenerationJob(status=JobStatus.FAILED, total_records=1, failed_records=1)
    db.add(job)
    db.commit()

    resp = client.get(f"/api/v1/certificates/jobs/{job.id}/download-all")
    assert resp.status_code == 404


def test_retry_failed_and_stalled_endpoints(
    client: TestClient, db: Session, auth_headers: dict[str, str]
):
    """Verify retry-failed and retry-stalled operational endpoints."""
    job = GenerationJob(status=JobStatus.FAILED, total_records=1, failed_records=1)
    db.add(job)
    db.flush()

    recipient = Recipient(
        job_id=job.id,
        name="Failed Person",
        email="failed@example.com",
        normalized_email="failed@example.com",
        issue_date=date.today(),
        status=RecipientStatus.FAILED,
        certificate_number="CERT-RET-01",
        verification_code="token-ret-01",
    )
    db.add(recipient)
    db.commit()

    # Retry failed
    retry_resp = client.post(
        f"/api/v1/certificates/jobs/{job.id}/retry-failed",
        headers=auth_headers,
    )
    assert retry_resp.status_code == 200
    assert retry_resp.json()["retried_records"] == 1

    # Retry stalled
    stall_resp = client.post(
        f"/api/v1/certificates/jobs/{job.id}/retry-stalled",
        headers=auth_headers,
    )
    assert stall_resp.status_code == 200
