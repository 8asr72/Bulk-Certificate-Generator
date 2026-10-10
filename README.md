# Bulk Certificate Generation Platform

A production-grade, asynchronous, distributed platform for ingesting recipient datasets, dynamically rendering personalized certificates, isolating processing failures, and providing secure individual and bulk deliverables.

Built for universities, online learning platforms, corporate compliance programs, and conference organizers.

---

## 1. System Architecture & Design Decisions

```
                           +---------------------------+
                           |  Client / Administrator   |
                           +-------------+-------------+
                                         |
                                         | REST / HTTPS (Idempotency-Key, API Key)
                                         v
                           +---------------------------+
                           |        FastAPI App        |
                           |  (Validation, Outbox,     |
                           |   Stream Downloads)       |
                           +----+--------+--------+----+
                                |        |        |
         +----------------------+        |        +---------------------+
         | Transactional Outbox          |                              |
         v                               v                              v
+------------------+           +------------------+           +------------------+
|  PostgreSQL 16   |           |     Redis 7      |           |  Local Storage   |
|  - Jobs          |           |  - Celery Broker |           |  - certificates/ |
|  - Recipients    |           |  - Result Backend|           |  - tmp/ staging  |
|  - Templates     |           +--------+---------+           +--------+---------+
+------------------+                    |                              |
                                        v                              |
                               +------------------+                    |
                               |  Celery Workers  +--------------------+
                               |  - ReportLab PDF | (Atomic Writes)
                               |  - Dynamic Fonts |
                               |  - Skip-Locked   |
                               +------------------+
```

### Key Architectural Decisions

1. **Synchronous SQLAlchemy Sessions for Celery & FastAPI Workers**:
   - Uses SQLAlchemy 2.0 with connection pooling and pre-ping checks.
   - Eliminates async/sync event loop impedance mismatches with conventional distributed Celery task workers.
2. **Transactional Outbox & Safe Ingestion**:
   - Job creation, recipient rows, and task dispatch events persist in a single atomic database transaction.
   - Idempotency keys prevent duplicate jobs; replaying a key with mismatched payload triggers `HTTP 409 Conflict`.
3. **Per-Recipient Failure Isolation**:
   - Each recipient is claimed transactionally (using `SELECT ... FOR UPDATE SKIP LOCKED` on PostgreSQL).
   - If rendering fails for one invalid row (e.g., extreme text length), that recipient is marked `FAILED` with sanitized error diagnostics while remaining batch recipients continue uninterrupted.
4. **Dynamic Font Scaling (ReportLab)**:
   - Measures exact typography width using `pdfmetrics.stringWidth`.
   - Iteratively scales font sizes down to a configurable minimum boundary (`14pt`) to accommodate unusually long names without overflowing borders.
5. **Streaming Downloads & Exploit Mitigation**:
   - Individual PDF downloads stream bounded byte chunks from storage without loading entire files into server memory.
   - Batch ZIP downloads stream on-the-fly with strict ZIP-slip defense (internal filename sanitization).
   - Exported failure reports mitigate CSV formula injection (OWASP CSV Injection) by prepending single quotes to trigger characters (`=`, `+`, `-`, `@`, `\t`, `\r`).

---

## 2. Repository Structure

```
Bulk-Certificate-Generator/
├── api/
│   ├── dependencies.py             # Database session, API key auth, pagination
│   └── v1/
│       ├── router.py               # Assembled API v1 router
│       └── endpoints/
│           ├── certificates.py     # Generation, job status, downloads, verification
│           ├── templates.py        # Versioned certificate templates
│           └── health.py           # /health/live and /health/ready probes
├── core/
│   ├── config.py                   # Pydantic Settings and environment configuration
│   ├── database.py                 # SQLAlchemy engine, sessionmaker, and connectivity
│   ├── celery_app.py               # Celery app with JSON serialization and task routing
│   ├── logging.py                  # Structured JSON logging and PII/secret redaction
│   ├── security.py                 # Constant-time auth, token generation, sanitizers
│   └── exceptions.py               # Unified domain exceptions hierarchy
├── models/
│   ├── base.py                     # Declarative BaseModel with UUID and timestamps
│   ├── job.py                      # GenerationJob model and non-negative counter checks
│   ├── recipient.py                # Recipient model with unique serials and verification codes
│   ├── template.py                 # CertificateTemplate model with default layout JSON
│   └── outbox.py                   # TransactionalOutbox model for persistent task events
├── schemas/
│   ├── job.py                      # Request/response schemas for jobs and progress
│   ├── recipient.py                # Recipient ingestion and status serialization
│   ├── template.py                 # Template registration schemas
│   └── verification.py             # Public certificate authenticity response
├── services/
│   ├── certificate_service.py      # ReportLab canvas renderer with dynamic typography
│   ├── storage_service.py          # Local filesystem storage with atomic writes & containment
│   ├── import_service.py           # CSV, XLSX, and JSON parsers with validation policies
│   ├── job_service.py              # Transactional claiming, status reconciliation, and retries
│   ├── verification_service.py     # Public credential verification logic
│   └── zip_service.py              # Streaming ZIP builder with ZIP-slip prevention
├── tasks/
│   ├── certificate_tasks.py        # Celery batch rendering tasks with per-row isolation
│   └── maintenance_tasks.py        # Stalled worker lease recovery and counter reconciliation
├── scripts/
│   ├── generate_demo_pdf.py        # Standalone PDF generation script
│   ├── verify_environment.py       # Comprehensive environment diagnostic script
│   ├── seed_demo_data.py           # Sample fixture generator
│   └── entrypoint.sh               # Container migration and startup script
├── alembic/
│   ├── env.py                      # Alembic migration environment
│   └── versions/                   # Versioned database migration scripts
├── examples/
│   ├── recipients_sample.csv       # Sample CSV template
│   └── recipients_sample.xlsx      # Sample XLSX template
├── tests/
│   ├── conftest.py                 # Pytest fixtures and test isolation
│   ├── unit/                       # Unit tests for models, storage, rendering, import, tasks
│   ├── api/                        # API endpoint and authentication tests
│   ├── security/                   # Security tests (traversal, ZIP-slip, CSV injection)
│   └── e2e/                        # Full lifecycle end-to-end integration test
├── Dockerfile                      # Multi-stage container definition with non-root appuser
├── docker-compose.yml              # Complete orchestrator for API, Worker, Postgres, Redis
├── requirements.txt                # Pinned dependencies
├── pyproject.toml                  # Build metadata, Ruff, and Pytest configuration
├── pytest.ini                      # Pytest runner settings
├── alembic.ini                     # Alembic configuration
├── PROJECT_TRACKER.md              # Real-time task tracker and verification log
└── README.md                       # Complete documentation
```

---

## 3. Getting Started & Deployment

### Prerequisites

- **Python**: 3.11+ (Python 3.11.9 recommended)
- **Docker & Docker Compose** (for containerized deployment) or local PostgreSQL 16 & Redis 7

### Quickstart with Docker Compose

1. Clone repository and initialize environment configuration:
   ```bash
   cp .env.example .env
   ```
2. Build and launch all services:
   ```bash
   docker compose up --build -d
   ```
3. Check container status:
   ```bash
   docker compose ps
   ```
4. Access interactive API documentation:
   - OpenAPI Swagger UI: `http://localhost:8000/docs`
   - ReDoc: `http://localhost:8000/redoc`

To shut down services:
```bash
docker compose down
```

---

### Local Development Setup

1. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   # Windows (Powershell):
   .\.venv\Scripts\Activate.ps1
   # Linux / macOS:
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Verify local environment health:
   ```bash
   python scripts/verify_environment.py
   ```
4. Generate a standalone demo PDF certificate:
   ```bash
   python scripts/generate_demo_pdf.py --output demo_cert.pdf
   ```
5. Apply database migrations:
   ```bash
   alembic upgrade head
   ```
6. Start the API server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
7. Start the Celery worker (in a separate terminal):
   ```bash
   celery -A core.celery_app.celery_app worker --loglevel=INFO -c 4 -Q certificates
   ```

---

## 4. API Reference & cURL Examples

All endpoints (except health probes and public verification) require the `X-API-Key` header if configured.

### 1. Submit Generation Job (JSON)

**Endpoint**: `POST /api/v1/certificates/generate`  
**Headers**:
- `X-API-Key: dev-test-api-key-bulk-cert-platform`
- `Idempotency-Key: job-2026-batch-001` (optional, recommended)
- `Content-Type: application/json`

**cURL Request**:
```bash
curl -X POST "http://localhost:8000/api/v1/certificates/generate" \
  -H "X-API-Key: dev-test-api-key-bulk-cert-platform" \
  -H "Idempotency-Key: job-2026-batch-001" \
  -H "Content-Type: application/json" \
  -d '{
    "acceptance_policy": "all_or_nothing",
    "recipients": [
      {
        "name": "Jane Cooper",
        "email": "jane.cooper@example.com",
        "issue_date": "2026-06-15",
        "external_reference": "STU-001"
      },
      {
        "name": "Prof. Alexander Montgomery Featherstone-Smythe III",
        "email": "alexander.featherstone@example.com",
        "issue_date": "2026-06-15",
        "external_reference": "STU-002"
      }
    ]
  }'
```

**Response (HTTP 202 Accepted)**:
```json
{
  "job_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "status": "PENDING",
  "total_records": 2,
  "accepted_records": 2,
  "rejected_records": 0,
  "acceptance_policy": "all_or_nothing",
  "validation_errors": [],
  "status_url": "/api/v1/certificates/jobs/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
}
```

---

### 2. Upload Recipients via CSV / XLSX

**Endpoint**: `POST /api/v1/certificates/upload`

**cURL Request**:
```bash
curl -X POST "http://localhost:8000/api/v1/certificates/upload" \
  -H "X-API-Key: dev-test-api-key-bulk-cert-platform" \
  -F "file=@examples/recipients_sample.csv" \
  -F "acceptance_policy=partial_acceptance"
```

---

### 3. Check Job Status & Live Progress

**Endpoint**: `GET /api/v1/certificates/jobs/{job_id}?skip=0&limit=50`

**cURL Request**:
```bash
curl -X GET "http://localhost:8000/api/v1/certificates/jobs/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
```

**Response (HTTP 200 OK)**:
```json
{
  "id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "status": "COMPLETED",
  "total_records": 2,
  "successful_records": 2,
  "failed_records": 0,
  "progress_percentage": 100.0,
  "created_at": "2026-10-10T14:00:00Z",
  "updated_at": "2026-10-10T14:00:02Z",
  "completed_at": "2026-10-10T14:00:02Z",
  "recipients": [
    {
      "id": "11111111-2222-3333-4444-555555555555",
      "job_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
      "name": "Jane Cooper",
      "email": "jane.cooper@example.com",
      "normalized_email": "jane.cooper@example.com",
      "issue_date": "2026-06-15",
      "status": "SUCCESS",
      "certificate_number": "CERT-2026-A1B2C3D4",
      "verification_code": "k9L1mN2oP3qR4sT5",
      "certificate_path": "certificates/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d/11111111-2222-3333-4444-555555555555.pdf"
    }
  ]
}
```

---

### 4. Download Individual Certificate PDF

**Endpoint**: `GET /api/v1/certificates/{recipient_id}/download`

```bash
curl -X GET "http://localhost:8000/api/v1/certificates/11111111-2222-3333-4444-555555555555/download" \
  -o "my_certificate.pdf"
```

---

### 5. Download Streaming ZIP Archive

**Endpoint**: `GET /api/v1/certificates/jobs/{job_id}/download-all`

```bash
curl -X GET "http://localhost:8000/api/v1/certificates/jobs/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d/download-all" \
  -o "all_certificates.zip"
```

---

### 6. Export Failure Report CSV

**Endpoint**: `GET /api/v1/certificates/jobs/{job_id}/failures.csv`

```bash
curl -X GET "http://localhost:8000/api/v1/certificates/jobs/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d/failures.csv" \
  -o "failed_recipients.csv"
```

---

### 7. Public Authenticity Verification

**Endpoint**: `GET /api/v1/certificates/verify/{verification_code}`  
*(No API Key required)*

```bash
curl -X GET "http://localhost:8000/api/v1/certificates/verify/k9L1mN2oP3qR4sT5"
```

**Response (HTTP 200 OK)**:
```json
{
  "valid": true,
  "certificate_number": "CERT-2026-A1B2C3D4",
  "recipient_name": "Jane Cooper",
  "issue_date": "2026-06-15",
  "issuer_name": "Accredited Certification Authority",
  "title": "Certificate of Completion",
  "verification_code": "k9L1mN2oP3qR4sT5",
  "verified_at": "2026-10-10T14:05:00Z"
}
```

---

### 8. Operational Health Checks

```bash
# Liveness probe
curl -i http://localhost:8000/health/live

# Readiness probe
curl -i http://localhost:8000/health/ready
```

---

## 5. Security & Reliability Assurances

| Threat / Risk | Mitigation Mechanism | Verification Test |
| :--- | :--- | :--- |
| **Timing Attacks on API Keys** | `secrets.compare_digest` constant-time comparison in `verify_api_key`. | `test_constant_time_api_key_verification` |
| **Directory Traversal (`../`)** | Canonical path resolution with `os.path.commonpath` verification strictly bound to `STORAGE_ROOT`. | `test_path_traversal_defense` |
| **ZIP-Slip File Overwrite** | Stripping directory path components and sanitizing archive member names (`sanitize_filename`). | `test_zip_slip_prevention` |
| **CSV Formula Injection** | Prepends `'` to cells beginning with `=`, `+`, `-`, `@`, `\t`, `\r` (`sanitize_csv_cell`). | `test_csv_formula_injection_defense` |
| **Credential Leakage in Logs** | Redacting API keys, passwords, and tokens with `***` before writing log output. | `test_secret_redaction_in_structured_logs` |
| **Duplicate Delivery / Replay** | Idempotency key tracking, deterministic SHA-256 request hashing, and skip-locked queries. | `test_idempotent_duplicate_request` |
| **Abandoned / Stalled Claims** | Background recovery leases identifying orphaned `PROCESSING` claims older than 10 minutes. | `test_stalled_job_recovery` |

---

## 6. Automated Testing & Quality Checks

Run all unit, integration, API, security, and end-to-end tests with test coverage:

```bash
pytest --cov=core --cov=models --cov=schemas --cov=services --cov=tasks --cov=api tests/ -v
```

Execute Ruff linting and formatting verification:

```bash
ruff check .
ruff format --check .
```
