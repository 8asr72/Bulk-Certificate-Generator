"""Security utilities including constant-time authentication, hashing, and sanitization."""

import datetime
import hashlib
import json
import re
import secrets
from typing import Any

from core.config import settings


def verify_api_key(provided_key: str | None) -> bool:
    """Validate an API key using constant-time comparison to prevent timing attacks."""
    if not settings.REQUIRE_API_KEY:
        return True
    if not provided_key:
        return False
    return secrets.compare_digest(provided_key.strip(), settings.API_KEY.strip())


def generate_certificate_number(prefix: str = "CERT") -> str:
    """Generate a unique human-readable certificate number with timestamp entropy."""
    year = datetime.datetime.now(datetime.UTC).year
    random_entropy = secrets.token_hex(4).upper()
    return f"{prefix}-{year}-{random_entropy}"


def generate_verification_code() -> str:
    """Generate a high-entropy URL-safe verification token."""
    return secrets.token_urlsafe(16)


def compute_payload_hash(payload: Any) -> str:
    """Compute a deterministic SHA-256 digest of request payloads for idempotency verification."""
    if isinstance(payload, bytes):
        raw_bytes = payload
    elif isinstance(payload, str):
        raw_bytes = payload.encode("utf-8")
    else:
        # Sort keys to ensure deterministic serialization
        raw_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw_bytes).hexdigest()


def sanitize_csv_cell(value: Any) -> str:
    """Protect against CSV formula injection (CVE-2014-3524 / OWASP CSV Injection).

    If an exported value starts with formula trigger characters (=, +, -, @, \t, \r),
    prepend a single quote to force spreadsheet parsers to treat it as plain text.
    """
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{text}"
    return text


def sanitize_filename(filename: str, fallback: str = "certificate.pdf") -> str:
    """Sanitize user- or system-supplied filenames to prevent path traversal and ZIP slip."""
    # Strip any directory path components
    cleaned = re.sub(r"[\\/]", "_", filename)
    # Remove null bytes and non-printable control characters
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)
    # Strip dangerous characters
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\. ]", "", cleaned).strip()
    # Avoid reserved Windows device names or empty output
    if not cleaned or cleaned.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}:
        return fallback
    # Limit length safely
    return cleaned[:100]


def mask_secret(secret: str | None, visible_prefix: int = 4, visible_suffix: int = 2) -> str:
    """Mask credentials or sensitive data for structured logging."""
    if not secret:
        return "<EMPTY>"
    if len(secret) <= visible_prefix + visible_suffix:
        return "***"
    return f"{secret[:visible_prefix]}***{secret[-visible_suffix:]}"
