"""Storage service abstraction and local filesystem implementation."""

import abc
import contextlib
import os
import shutil
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import BinaryIO

from core.config import settings
from core.exceptions import StorageError, StorageFileNotFoundError, StoragePathTraversalError
from core.logging import logger


class StorageService(abc.ABC):
    """Abstract interface defining required storage operations."""

    @abc.abstractmethod
    def save_bytes(self, relative_path: str, data: bytes) -> str:
        """Atomically persist raw bytes to the relative path and return the stored path."""
        pass

    @abc.abstractmethod
    def save_stream(self, relative_path: str, stream: BinaryIO) -> str:
        """Atomically persist a binary stream to the relative path and return the stored path."""
        pass

    @abc.abstractmethod
    def stream_file(
        self, relative_path: str, chunk_size: int = 65536
    ) -> Generator[bytes, None, None]:
        """Stream file contents in bounded chunks to avoid buffering into memory."""
        pass

    @abc.abstractmethod
    def file_exists(self, relative_path: str) -> bool:
        """Check whether the relative path exists in storage."""
        pass

    @abc.abstractmethod
    def get_file_size(self, relative_path: str) -> int:
        """Return the size in bytes of the stored artifact."""
        pass

    @abc.abstractmethod
    def delete_file(self, relative_path: str) -> bool:
        """Delete the stored artifact if present."""
        pass

    @abc.abstractmethod
    def resolve_secure_path(self, relative_path: str) -> Path:
        """Resolve and validate that the relative path strictly resides inside storage root."""
        pass


class LocalStorageService(StorageService):
    """Local filesystem storage implementation with atomic writes and traversal containment."""

    def __init__(self, root_path: Path | str | None = None):
        self.root_path = Path(root_path or settings.storage_root_path).resolve()
        self.certificates_dir = self.root_path / "certificates"
        self.tmp_dir = self.root_path / "tmp"

        self.certificates_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def resolve_secure_path(self, relative_path: str) -> Path:
        """Resolve path and verify containment within storage root to prevent directory traversal."""
        if not relative_path or not relative_path.strip():
            raise StoragePathTraversalError("Empty storage path")

        raw_path = relative_path.strip()
        # Reject absolute paths or paths starting with leading directory separators
        if raw_path.startswith(("/", "\\")) or Path(raw_path).is_absolute():
            raise StoragePathTraversalError(relative_path)

        clean_rel = raw_path.replace("\\", "/")
        target = (self.root_path / clean_rel).resolve()
        try:
            # os.path.commonpath raises ValueError if on different drives on Windows
            common = Path(os.path.commonpath([str(target), str(self.root_path)])).resolve()
            if common != self.root_path:
                raise StoragePathTraversalError(relative_path) from None
        except ValueError:
            raise StoragePathTraversalError(relative_path) from None

        return target

    def file_exists(self, relative_path: str) -> bool:
        """Check whether the requested artifact exists on disk."""
        target = self.resolve_secure_path(relative_path)
        return target.is_file()

    def get_file_size(self, relative_path: str) -> int:
        """Get size in bytes, raising StorageFileNotFoundError if missing."""
        target = self.resolve_secure_path(relative_path)
        if not target.is_file():
            raise StorageFileNotFoundError(relative_path)
        return target.stat().st_size

    def save_bytes(self, relative_path: str, data: bytes) -> str:
        """Write raw bytes atomically via temporary staging file and atomic rename."""
        target = self.resolve_secure_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        tmp_filename = f"{uuid.uuid4().hex}.tmp"
        tmp_target = self.tmp_dir / tmp_filename

        try:
            with open(tmp_target, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace
            os.replace(tmp_target, target)
            logger.debug(f"Saved artifact atomically to '{relative_path}' ({len(data)} bytes)")
            return relative_path
        except Exception as exc:
            if tmp_target.exists():
                with contextlib.suppress(OSError):
                    tmp_target.unlink()
            logger.error(f"Failed to persist file at '{relative_path}': {exc}")
            raise StorageError(f"Could not save file '{relative_path}': {exc}") from exc

    def save_stream(self, relative_path: str, stream: BinaryIO) -> str:
        """Stream chunks into temporary staging file, then atomically move to target."""
        target = self.resolve_secure_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        tmp_filename = f"{uuid.uuid4().hex}.tmp"
        tmp_target = self.tmp_dir / tmp_filename

        try:
            with open(tmp_target, "wb") as f:
                shutil.copyfileobj(stream, f, length=65536)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_target, target)
            return relative_path
        except Exception as exc:
            if tmp_target.exists():
                with contextlib.suppress(OSError):
                    tmp_target.unlink()
            raise StorageError(f"Could not stream save file '{relative_path}': {exc}") from exc

    def stream_file(
        self, relative_path: str, chunk_size: int = 65536
    ) -> Generator[bytes, None, None]:
        """Yield content chunks from disk without holding entire payload in memory."""
        target = self.resolve_secure_path(relative_path)
        if not target.is_file():
            raise StorageFileNotFoundError(relative_path)

        try:
            with open(target, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk
        except Exception as exc:
            logger.error(f"Error streaming artifact '{relative_path}': {exc}")
            raise StorageError(f"Streaming error on '{relative_path}': {exc}") from exc

    def delete_file(self, relative_path: str) -> bool:
        """Safely delete target file if present."""
        target = self.resolve_secure_path(relative_path)
        if target.is_file():
            try:
                target.unlink()
                return True
            except OSError as exc:
                logger.warning(f"Failed to delete artifact '{relative_path}': {exc}")
                return False
        return False


# Default singleton instance using application settings
storage_service = LocalStorageService()
