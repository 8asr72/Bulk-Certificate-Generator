"""Structured logging configuration with correlation ID tracking and secret redaction."""

import contextvars
import json
import logging
import re
import sys
from typing import Any

from core.config import settings

# Context variable for distributed tracing and request correlation
correlation_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
job_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)
recipient_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "recipient_id", default=None
)

SENSITIVE_PATTERNS = [
    re.compile(
        r"(api[-_]?key|password|secret|authorization|token)[\"']?\s*[:=]\s*[\"']?([^\"',\s]+)",
        re.IGNORECASE,
    ),
]


def redact_sensitive_text(text: str) -> str:
    """Scan and redact known credential and secret patterns from text."""
    for pattern in SENSITIVE_PATTERNS:
        text = pattern.sub(r"\1=***", text)
    return text


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured JSON entries with contextual identifiers."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_text(record.getMessage()),
            "environment": settings.ENVIRONMENT,
        }

        # Add contextvars if populated
        cid = correlation_id_ctx.get()
        if cid:
            log_data["correlation_id"] = cid

        jid = job_id_ctx.get() or getattr(record, "job_id", None)
        if jid:
            log_data["job_id"] = str(jid)

        rid = recipient_id_ctx.get() or getattr(record, "recipient_id", None)
        if rid:
            log_data["recipient_id"] = str(rid)

        # Include exception details if present
        if record.exc_info and record.exc_text:
            log_data["exception"] = redact_sensitive_text(record.exc_text)
        elif record.exc_info:
            log_data["exception"] = redact_sensitive_text(self.formatException(record.exc_info))

        return json.dumps(log_data)


def setup_logging(level: str | None = None) -> None:
    """Initialize structured logging across the application."""
    log_level = getattr(
        logging, (level or ("DEBUG" if settings.DEBUG else "INFO")).upper(), logging.INFO
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers
    root_logger.handlers = []

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(StructuredJsonFormatter())
    root_logger.addHandler(handler)

    # Quiet overly chatty third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("reportlab").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)


logger = logging.getLogger("bulk_certificate_platform")
