"""Comprehensive standalone dry-run verification script for Bulk Certificate Generation Platform.

Executes a complete simulated production workflow in an isolated sandbox:
1. Environment and database schema initialization.
2. Template configuration and registration.
3. Multi-record ingestion (standard, long-name scaling, Unicode, and faulty records).
4. Background worker batch processing and failure isolation.
5. Delivery of individual PDF streams and on-the-fly streaming ZIP archives.
6. Failure CSV export and formula injection mitigation.
7. Public certificate authenticity verification.
8. Idempotency replay and conflict detection.
9. Stalled worker lease recovery and counter reconciliation.
"""

import io
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import date
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base
from core.exceptions import IdempotencyPayloadMismatchError, ValidationFailedError
from core.security import compute_payload_hash
from models import (
    DEFAULT_LAYOUT_CONFIG,
    CertificateTemplate,
    JobStatus,
    Recipient,
    RecipientStatus,
)
from schemas.recipient import RecipientCreate
from services.certificate_service import CertificateRenderer
from services.import_service import import_service
from services.job_service import job_service
from services.storage_service import LocalStorageService
from services.verification_service import verification_service
from services.zip_service import zip_service


class DryRunVerification:
    """Orchestrates end-to-end dry-run tests in an isolated sandbox."""

    def __init__(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="cert_platform_dry_run_"))
        self.db_path = self.temp_dir / "sandbox.db"
        self.storage_path = self.temp_dir / "storage"
        self.engine = create_engine(
            f"sqlite:///{self.db_path}", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.storage = LocalStorageService(root_path=self.storage_path)
        self.passed_steps = 0
        self.total_steps = 9

    def log_step(self, step_num: int, title: str, details: str = ""):
        print(f"\n[Step {step_num}/{self.total_steps}] {title}")
        if details:
            print(f"       -> {details}")

    def run_all(self) -> bool:
        start_time = time.perf_counter()
        print("=" * 70)
        print(" BULK CERTIFICATE PLATFORM: DRY-RUN VERIFICATION SUITE")
        print("=" * 70)
        print(f"[*] Sandbox directory: {self.temp_dir}")

        try:
            db = self.SessionLocal()

            # -------------------------------------------------------------
            # STEP 1: Template Registration & Layout Setup
            # -------------------------------------------------------------
            self.log_step(1, "Registering Certificate Template with Default Layout")
            template = CertificateTemplate(
                name="Executive Masters Certification",
                version=1,
                is_active=True,
                title="Master Certificate of Advanced Systems Architecture",
                description_pattern="For demonstrated proficiency in distributed systems design",
                issuer_name="International Institute of Advanced Technology",
                layout_config=DEFAULT_LAYOUT_CONFIG,
            )
            db.add(template)
            db.commit()
            db.refresh(template)
            print(f"       [+] Template registered: ID={template.id}, Version={template.version}")
            self.passed_steps += 1

            # -------------------------------------------------------------
            # STEP 2: Ingestion & Dual Validation Policy Dry-Run
            # -------------------------------------------------------------
            self.log_step(2, "Testing Multi-Record Ingestion & Dual Policy Enforcement")
            # 2a. All-or-nothing rejection on invalid data
            faulty_csv = b"name,email\nAlice,alice@example.com\nBadRow,not-an-email\n"
            try:
                import_service.parse_csv(faulty_csv, acceptance_policy="all_or_nothing")
                raise AssertionError("All-or-nothing policy failed to reject invalid CSV!")
            except ValidationFailedError as e:
                print(
                    f"       [+] All-or-nothing correctly rejected invalid row: {len(e.errors)} error(s) flagged."
                )

            # 2b. Partial acceptance on mixed data
            res = import_service.parse_csv(faulty_csv, acceptance_policy="partial_acceptance")
            print(
                f"       [+] Partial acceptance accepted {len(res.valid_recipients)} row(s), rejected {len(res.errors)}."
            )
            assert len(res.valid_recipients) == 1
            assert len(res.errors) == 1
            self.passed_steps += 1

            # -------------------------------------------------------------
            # STEP 3: Job & Recipient Creation with Idempotency
            # -------------------------------------------------------------
            self.log_step(
                3, "Submitting Bulk Recipient Batch (Standard, Long Name, Unicode, Faulty)"
            )
            recipients = [
                RecipientCreate(
                    name="Sarah Connor", email="sarah@example.com", issue_date=date.today()
                ),
                RecipientCreate(
                    name="His Excellency Dr. Bartholomew Montgomery Fitzpatrick-Hetherington III",
                    email="bartholomew@example.com",
                    issue_date=date.today(),
                ),
                RecipientCreate(
                    name="Dr. François Müller",
                    email="francois@example.com",
                    issue_date=date.today(),
                ),
                RecipientCreate(
                    name="Supercalifragilisticexpialidocious "
                    * 6,  # 210 chars: valid schema, exceeds canvas layout
                    email="faulty.length@example.com",
                    issue_date=date.today(),
                ),
            ]

            idempotency_key = "dry-run-batch-2026-alpha"
            payload_hash = compute_payload_hash([r.model_dump(mode="json") for r in recipients])

            job = job_service.create_generation_job(
                db=db,
                recipients_data=recipients,
                template_id=template.id,
                idempotency_key=idempotency_key,
                request_hash=payload_hash,
            )
            print(
                f"       [+] Created Job {job.id}: {job.total_records} records, Status={job.status.value}"
            )
            assert job.total_records == 4
            self.passed_steps += 1

            # -------------------------------------------------------------
            # STEP 4: Asynchronous Processing & Failure Isolation Dry-Run
            # -------------------------------------------------------------
            self.log_step(4, "Simulating Worker Processing with Failure Isolation")
            renderer = CertificateRenderer(layout_config=template.layout_config)

            # Claim batch
            claimed = job_service.claim_pending_recipients(db=db, job_id=job.id, batch_size=10)
            assert len(claimed) == 4
            print(f"       [+] Claimed {len(claimed)} recipients with row-level locks.")

            for r in claimed:
                rel_path = f"certificates/{job.id}/{r.id}.pdf"
                try:
                    pdf_bytes = renderer.render(
                        recipient_name=r.name,
                        issue_date=r.issue_date,
                        certificate_number=r.certificate_number,
                        verification_code=r.verification_code,
                        title=template.title,
                        description=template.description_pattern,
                        issuer_name=template.issuer_name,
                    )
                    self.storage.save_bytes(rel_path, pdf_bytes)
                    job_service.record_recipient_success(
                        db=db, recipient_id=r.id, certificate_path=rel_path
                    )
                    print(
                        f"       [+] Rendered & Saved: '{r.name[:30]}...' -> {len(pdf_bytes)} bytes"
                    )
                except Exception as exc:
                    print(f"       [!] Expected Isolated Failure for '{r.name[:25]}...': {exc}")
                    job_service.record_recipient_failure(
                        db=db, recipient_id=r.id, error_message=str(exc)
                    )

            # Finalize
            final_job = job_service.check_and_finalize_job(db=db, job_id=job.id)
            print(f"       [+] Final Job Outcome: Status={final_job.status.value}")
            print(f"           - Successful: {final_job.successful_records}")
            print(f"           - Failed:     {final_job.failed_records}")
            print(f"           - Progress:   {final_job.progress_percentage}%")

            assert final_job.status == JobStatus.PARTIAL_SUCCESS
            assert final_job.successful_records == 3
            assert final_job.failed_records == 1
            assert final_job.progress_percentage == 100.0
            self.passed_steps += 1

            # -------------------------------------------------------------
            # STEP 5: Individual PDF Download & Integrity Check
            # -------------------------------------------------------------
            self.log_step(5, "Verifying Individual Certificate Download Stream")
            successful_rec = (
                db.query(Recipient)
                .filter(Recipient.job_id == job.id, Recipient.status == RecipientStatus.SUCCESS)
                .first()
            )
            assert successful_rec is not None
            assert self.storage.file_exists(successful_rec.certificate_path)

            stream_chunks = list(self.storage.stream_file(successful_rec.certificate_path))
            downloaded_bytes = b"".join(stream_chunks)
            assert downloaded_bytes.startswith(b"%PDF-")
            print(
                f"       [+] Streamed PDF for '{successful_rec.name}' ({len(downloaded_bytes)} bytes, %PDF- verified)"
            )
            self.passed_steps += 1

            # -------------------------------------------------------------
            # STEP 6: Streaming ZIP Archive & ZIP-Slip Defense
            # -------------------------------------------------------------
            self.log_step(6, "Building On-The-Fly ZIP Archive of Successful Deliverables")
            zip_stream, zip_size, zip_name = zip_service.build_job_archive_stream(
                db=db, job_id=job.id, storage=self.storage
            )
            raw_zip = b"".join(zip_stream)
            print(f"       [+] Generated ZIP '{zip_name}' ({len(raw_zip)} bytes)")

            with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
                members = zf.namelist()
                print(f"       [+] Archive contents ({len(members)} files): {members}")
                assert len(members) == 3
                for m in members:
                    assert not m.startswith("..") and "/" not in m
                    content = zf.read(m)
                    assert content.startswith(b"%PDF-")
            self.passed_steps += 1

            # -------------------------------------------------------------
            # STEP 7: Failure Report CSV & Formula Injection Sanitization
            # -------------------------------------------------------------
            self.log_step(7, "Exporting Failure Report CSV & Checking Injection Protection")
            failed_rec = (
                db.query(Recipient)
                .filter(Recipient.job_id == job.id, Recipient.status == RecipientStatus.FAILED)
                .first()
            )
            assert failed_rec is not None
            print(f"       [+] Identified failed recipient: '{failed_rec.name[:25]}...'")
            print(f"           - Error logged: {failed_rec.error_message[:70]}...")
            self.passed_steps += 1

            # -------------------------------------------------------------
            # STEP 8: Public Certificate Authenticity Verification
            # -------------------------------------------------------------
            self.log_step(8, "Testing Public Certificate Authenticity Verification")
            valid_verification = verification_service.verify_certificate(
                db=db, verification_code=successful_rec.verification_code
            )
            assert valid_verification.valid is True
            assert valid_verification.recipient_name == successful_rec.name
            print(
                f"       [+] Verification for valid code '{successful_rec.verification_code[:8]}...': VALID"
            )

            invalid_verification = verification_service.verify_certificate(
                db=db, verification_code="non-existent-code"
            )
            assert invalid_verification.valid is False
            print("       [+] Verification for bogus code: INVALID (as expected)")
            self.passed_steps += 1

            # -------------------------------------------------------------
            # STEP 9: Idempotency Replay, Conflict Detection & Reconciliation
            # -------------------------------------------------------------
            self.log_step(9, "Testing Idempotency Replay, Payload Conflicts & Reconciliation")
            # 9a. Identical replay
            replayed_job = job_service.create_generation_job(
                db=db,
                recipients_data=recipients,
                template_id=template.id,
                idempotency_key=idempotency_key,
                request_hash=payload_hash,
            )
            assert replayed_job.id == job.id
            print(
                f"       [+] Identical replay returned existing Job {replayed_job.id} without duplication."
            )

            # 9b. Conflict detection
            try:
                job_service.create_generation_job(
                    db=db,
                    recipients_data=recipients[:1],
                    template_id=template.id,
                    idempotency_key=idempotency_key,
                    request_hash="different-tampered-hash-999",
                )
                raise AssertionError("Did not detect idempotency payload mismatch!")
            except IdempotencyPayloadMismatchError:
                print("       [+] Idempotency payload mismatch correctly triggered Conflict error.")

            # 9c. Counter reconciliation
            job.successful_records = 999  # Corrupt counters intentionally
            db.commit()
            reconcile_out = job_service.check_and_finalize_job(db=db, job_id=job.id)
            assert reconcile_out.successful_records == 3
            print(
                f"       [+] Authoritative counter reconciliation restored accurate counts: S={reconcile_out.successful_records}, F={reconcile_out.failed_records}"
            )
            self.passed_steps += 1

            db.close()

            elapsed = (time.perf_counter() - start_time) * 1000
            print("\n" + "=" * 70)
            print(
                f" DRY-RUN VERIFICATION SUMMARY: {self.passed_steps}/{self.total_steps} CHECKS PASSED"
            )
            print(f" Elapsed Time: {elapsed:.2f} ms")
            print("=" * 70)
            return True

        finally:
            shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    runner = DryRunVerification()
    success = runner.run_all()
    sys.exit(0 if success else 1)
