"""Domain exceptions for the Bulk Certificate Generation Platform."""

from typing import Any


class PlatformException(Exception):
    """Base exception for all domain and platform errors."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", details: Any = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class NotFoundError(PlatformException):
    """Base exception for missing resources."""

    def __init__(self, message: str, code: str = "NOT_FOUND", details: Any = None):
        super().__init__(message, code=code, details=details)


class JobNotFoundError(NotFoundError):
    """Raised when a generation job cannot be located."""

    def __init__(self, job_id: str):
        super().__init__(
            f"Generation job '{job_id}' was not found.",
            code="JOB_NOT_FOUND",
            details={"job_id": job_id},
        )


class RecipientNotFoundError(NotFoundError):
    """Raised when a recipient record cannot be located."""

    def __init__(self, recipient_id: str):
        super().__init__(
            f"Recipient record '{recipient_id}' was not found.",
            code="RECIPIENT_NOT_FOUND",
            details={"recipient_id": recipient_id},
        )


class TemplateNotFoundError(NotFoundError):
    """Raised when a certificate template cannot be located."""

    def __init__(self, template_id: str):
        super().__init__(
            f"Certificate template '{template_id}' was not found.",
            code="TEMPLATE_NOT_FOUND",
            details={"template_id": template_id},
        )


class InvalidTemplateError(PlatformException):
    """Raised when template definition or layout configuration is invalid."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(message, code="INVALID_TEMPLATE", details=details)


class StorageError(PlatformException):
    """Base exception for filesystem storage errors."""

    def __init__(self, message: str, code: str = "STORAGE_ERROR", details: Any = None):
        super().__init__(message, code=code, details=details)


class StoragePathTraversalError(StorageError):
    """Raised when a path escapes the permitted storage root boundary."""

    def __init__(self, path: str):
        super().__init__(
            f"Access denied: path traversal attempt detected for '{path}'.",
            code="PATH_TRAVERSAL_DETECTED",
            details={"attempted_path": path},
        )


class StorageFileNotFoundError(StorageError):
    """Raised when a required storage artifact is missing on disk."""

    def __init__(self, path: str):
        super().__init__(
            f"Storage artifact was not found on disk: '{path}'.",
            code="ARTIFACT_NOT_FOUND",
            details={"path": path},
        )


class IdempotencyError(PlatformException):
    """Base exception for idempotency violations."""

    def __init__(self, message: str, code: str = "IDEMPOTENCY_ERROR", details: Any = None):
        super().__init__(message, code=code, details=details)


class IdempotencyPayloadMismatchError(IdempotencyError):
    """Raised when an idempotency key is reused with a different request payload."""

    def __init__(self, key: str):
        super().__init__(
            f"Idempotency key '{key}' was previously used with a different request payload.",
            code="IDEMPOTENCY_PAYLOAD_MISMATCH",
            details={"idempotency_key": key},
        )


class ValidationFailedError(PlatformException):
    """Raised when bulk import or entity validation fails."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message, code="VALIDATION_FAILED", details={"errors": errors or []})
        self.errors = errors or []


class RenderingError(PlatformException):
    """Raised when PDF certificate generation fails."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(message, code="RENDERING_ERROR", details=details)


class RenderingFontError(RenderingError):
    """Raised when a required font cannot be loaded or registered."""

    def __init__(self, font_name: str):
        super().__init__(
            f"Required font '{font_name}' is not registered or unavailable.",
            code="FONT_UNAVAILABLE",
            details={"font_name": font_name},
        )


class UnauthorizedError(PlatformException):
    """Raised when authentication credentials or API keys are missing/invalid."""

    def __init__(self, message: str = "Invalid or missing API key"):
        super().__init__(message, code="UNAUTHORIZED", details={})
