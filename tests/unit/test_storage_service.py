"""Unit tests for storage service abstraction, atomic writes, and containment checks."""

import io

import pytest

from core.exceptions import StorageFileNotFoundError, StoragePathTraversalError
from services.storage_service import LocalStorageService


@pytest.fixture
def temp_storage(tmp_path):
    """Create an isolated LocalStorageService instance anchored in a temporary test directory."""
    return LocalStorageService(root_path=tmp_path)


def test_storage_save_and_read_bytes(temp_storage: LocalStorageService):
    """Verify atomic saving and chunked streaming of raw byte artifacts."""
    content = b"PDF-SAMPLE-DATA-STREAM"
    rel_path = "certificates/job-1/cert-1.pdf"

    saved_path = temp_storage.save_bytes(rel_path, content)
    assert saved_path == rel_path
    assert temp_storage.file_exists(rel_path) is True
    assert temp_storage.get_file_size(rel_path) == len(content)

    chunks = list(temp_storage.stream_file(rel_path, chunk_size=8))
    assert b"".join(chunks) == content


def test_storage_save_stream(temp_storage: LocalStorageService):
    """Verify streaming file write and atomic move."""
    stream = io.BytesIO(b"STREAMED-CERTIFICATE-BYTES-12345")
    rel_path = "certificates/job-2/cert-2.pdf"

    temp_storage.save_stream(rel_path, stream)
    assert temp_storage.file_exists(rel_path) is True
    assert temp_storage.get_file_size(rel_path) == 32


def test_storage_delete_file(temp_storage: LocalStorageService):
    """Verify deletion of artifacts."""
    rel_path = "certificates/delete_me.pdf"
    temp_storage.save_bytes(rel_path, b"TO-BE-DELETED")
    assert temp_storage.file_exists(rel_path) is True

    deleted = temp_storage.delete_file(rel_path)
    assert deleted is True
    assert temp_storage.file_exists(rel_path) is False

    # Deleting nonexistent file returns False without raising
    assert temp_storage.delete_file(rel_path) is False


def test_storage_path_traversal_prevention(temp_storage: LocalStorageService):
    """Verify strict containment within storage root and rejection of path traversal."""
    malicious_paths = [
        "../outside.txt",
        "../../etc/passwd",
        "/etc/shadow",
        "certificates/../../secret.env",
        "..\\..\\windows\\system32",
    ]

    for path in malicious_paths:
        with pytest.raises(StoragePathTraversalError):
            temp_storage.resolve_secure_path(path)

        with pytest.raises(StoragePathTraversalError):
            temp_storage.save_bytes(path, b"danger")


def test_storage_missing_file_error(temp_storage: LocalStorageService):
    """Verify missing files raise StorageFileNotFoundError."""
    with pytest.raises(StorageFileNotFoundError):
        temp_storage.get_file_size("certificates/missing.pdf")

    with pytest.raises(StorageFileNotFoundError):
        list(temp_storage.stream_file("certificates/missing.pdf"))
