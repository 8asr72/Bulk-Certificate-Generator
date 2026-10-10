"""Streaming ZIP archive builder with ZIP-slip exploit defense and memory bounds."""

import contextlib
import os
import tempfile
import uuid
import zipfile
from collections.abc import Generator

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.exceptions import NotFoundError, StorageFileNotFoundError
from core.logging import logger
from core.security import sanitize_filename
from models import GenerationJob, Recipient, RecipientStatus
from services.storage_service import StorageService


class ZipService:
    """Creates streaming ZIP archives of batch certificate deliverables."""

    def build_job_archive_stream(
        self,
        db: Session,
        job_id: uuid.UUID,
        storage: StorageService,
        chunk_size: int = 65536,
    ) -> tuple[Generator[bytes, None, None], int, str]:
        """Create a temporary ZIP file from successful certificates and return a stream generator."""
        job = db.execute(
            select(GenerationJob).where(GenerationJob.id == job_id)
        ).scalar_one_or_none()

        if not job:
            raise NotFoundError(f"Job {job_id} not found.")

        recipients = (
            db.execute(
                select(Recipient).where(
                    Recipient.job_id == job_id,
                    Recipient.status == RecipientStatus.SUCCESS,
                )
            )
            .scalars()
            .all()
        )

        if not recipients:
            raise NotFoundError("No successful certificates available to archive for this job.")

        # Create temporary archive file
        tmp_archive = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp_archive_path = tmp_archive.name
        tmp_archive.close()

        added_count = 0
        try:
            with zipfile.ZipFile(
                tmp_archive_path, mode="w", compression=zipfile.ZIP_DEFLATED
            ) as zf:
                seen_names = set()
                for r in recipients:
                    if not r.certificate_path or not storage.file_exists(r.certificate_path):
                        logger.warning(
                            f"Artifact missing for recipient {r.id} ({r.certificate_path}), skipping from archive."
                        )
                        continue

                    # ZIP-slip defense: sanitize internal filename
                    base_filename = sanitize_filename(f"{r.certificate_number}_{r.name}.pdf")
                    # Ensure uniqueness within archive
                    counter = 1
                    entry_name = base_filename
                    while entry_name in seen_names:
                        entry_name = f"{counter}_{base_filename}"
                        counter += 1
                    seen_names.add(entry_name)

                    # Stream artifact from storage directly into zip archive
                    resolved_file = storage.resolve_secure_path(r.certificate_path)
                    zf.write(resolved_file, arcname=entry_name)
                    added_count += 1

            if added_count == 0:
                raise StorageFileNotFoundError("None of the successful certificates exist on disk.")

            archive_size = os.path.getsize(tmp_archive_path)

            def file_stream_generator() -> Generator[bytes, None, None]:
                """Yield archive chunks and ensure temporary archive is unlinked upon completion."""
                try:
                    with open(tmp_archive_path, "rb") as f:
                        while chunk := f.read(chunk_size):
                            yield chunk
                finally:
                    if os.path.exists(tmp_archive_path):
                        with contextlib.suppress(OSError):
                            os.unlink(tmp_archive_path)

            zip_filename = f"certificates_job_{str(job_id)[:8]}.zip"
            return file_stream_generator(), archive_size, zip_filename

        except Exception:
            if os.path.exists(tmp_archive_path):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_archive_path)
            raise


zip_service = ZipService()
