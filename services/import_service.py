"""Bulk recipient import and validation engine for CSV, XLSX, and JSON payloads."""

import csv
import io
import re
from datetime import date, datetime
from typing import Any

import openpyxl
from pydantic import ValidationError

from core.config import settings
from core.exceptions import ValidationFailedError
from schemas.job import AcceptancePolicy
from schemas.recipient import RecipientCreate

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
]

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class ImportValidationResult:
    """Holds partitioned valid recipient models and row-level error reports."""

    def __init__(
        self,
        valid_recipients: list[RecipientCreate],
        errors: list[dict[str, Any]],
        total_rows_inspected: int,
    ):
        self.valid_recipients = valid_recipients
        self.errors = errors
        self.total_rows_inspected = total_rows_inspected

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


class ImportService:
    """Parses and validates recipient data from JSON, CSV, and XLSX formats."""

    @staticmethod
    def _parse_date(date_val: Any) -> date:
        """Parse various date formats or Excel datetime objects safely."""
        if not date_val:
            return date.today()
        if isinstance(date_val, datetime):
            return date_val.date()
        if isinstance(date_val, date):
            return date_val

        str_val = str(date_val).strip()
        if not str_val:
            return date.today()

        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(str_val, fmt).date()
            except ValueError:
                continue

        raise ValueError(
            f"Invalid date format: '{date_val}'. Supported formats include YYYY-MM-DD, DD/MM/YYYY."
        )

    @staticmethod
    def _normalize_row_dict(raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize case and whitespace for dictionary keys."""
        normalized = {}
        for k, v in raw.items():
            if k:
                key = str(k).strip().lower()
                normalized[key] = v
        return normalized

    def validate_recipient_row(self, row_idx: int, data: dict[str, Any]) -> RecipientCreate:
        """Validate an individual row against RecipientCreate schema rules."""
        raw_name = data.get("name")
        raw_email = data.get("email")
        raw_date = data.get("issue_date") or data.get("date")
        raw_ref = data.get("external_reference") or data.get("reference") or data.get("ref")

        if not raw_name or not str(raw_name).strip():
            raise ValueError("Field 'name' is required and cannot be empty")

        clean_name = str(raw_name).strip()
        if len(clean_name) > 255:
            raise ValueError("Field 'name' exceeds maximum length of 255 characters")

        if not raw_email or not str(raw_email).strip():
            raise ValueError("Field 'email' is required and cannot be empty")

        clean_email = str(raw_email).strip().lower()
        if not EMAIL_REGEX.match(clean_email):
            raise ValueError(f"Invalid email address: '{raw_email}'")

        parsed_date = self._parse_date(raw_date)
        clean_ref = str(raw_ref).strip() if raw_ref else None
        if clean_ref and len(clean_ref) > 255:
            raise ValueError("Field 'external_reference' exceeds maximum length of 255 characters")

        try:
            return RecipientCreate(
                name=clean_name,
                email=clean_email,
                issue_date=parsed_date,
                external_reference=clean_ref,
            )
        except ValidationError as exc:
            first_err = exc.errors()[0]
            raise ValueError(f"{first_err['loc'][0]}: {first_err['msg']}") from exc

    def process_raw_records(
        self,
        raw_rows: list[dict[str, Any]],
        acceptance_policy: AcceptancePolicy = "all_or_nothing",
    ) -> ImportValidationResult:
        """Validate a list of raw dictionaries with the chosen acceptance policy."""
        if not raw_rows:
            raise ValidationFailedError("Submission contains no recipient records.")

        if len(raw_rows) > settings.MAX_BATCH_SIZE:
            raise ValidationFailedError(
                f"Batch size of {len(raw_rows)} exceeds maximum limit of {settings.MAX_BATCH_SIZE} records."
            )

        valid_recipients: list[RecipientCreate] = []
        errors: list[dict[str, Any]] = []

        for idx, row in enumerate(raw_rows, start=1):
            # Check for entirely empty rows
            if not any(bool(str(v).strip()) for v in row.values() if v is not None):
                continue

            try:
                norm = self._normalize_row_dict(row)
                recipient = self.validate_recipient_row(idx, norm)
                valid_recipients.append(recipient)
            except Exception as exc:
                errors.append(
                    {
                        "row": idx,
                        "error": str(exc),
                        "raw_data": {k: str(v) for k, v in row.items() if v is not None},
                    }
                )

        if acceptance_policy == "all_or_nothing" and errors:
            raise ValidationFailedError(
                f"Batch rejected under all-or-nothing policy due to {len(errors)} invalid rows.",
                errors=errors,
            )

        if not valid_recipients and errors:
            raise ValidationFailedError(
                "All rows in the submission failed validation.",
                errors=errors,
            )

        return ImportValidationResult(
            valid_recipients=valid_recipients,
            errors=errors,
            total_rows_inspected=len(raw_rows),
        )

    def parse_csv(
        self,
        file_bytes: bytes,
        acceptance_policy: AcceptancePolicy = "all_or_nothing",
    ) -> ImportValidationResult:
        """Parse and validate CSV content."""
        if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise ValidationFailedError(
                f"File size exceeds maximum upload limit of {settings.MAX_UPLOAD_SIZE_MB}MB."
            )

        try:
            text_stream = io.StringIO(file_bytes.decode("utf-8-sig"))
        except UnicodeDecodeError:
            try:
                text_stream = io.StringIO(file_bytes.decode("latin-1"))
            except Exception as exc:
                raise ValidationFailedError(f"Unsupported file encoding: {exc}") from exc

        reader = csv.reader(text_stream)
        try:
            raw_headers = next(reader)
        except StopIteration:
            raise ValidationFailedError("Uploaded CSV file is empty.") from None

        headers = [h.strip() for h in raw_headers if h is not None]
        lower_headers = [h.lower() for h in headers]

        # Duplicate header detection
        seen = set()
        for h in lower_headers:
            if h in seen:
                raise ValidationFailedError(f"Duplicate column header detected in CSV: '{h}'")
            seen.add(h)

        if "name" not in lower_headers or "email" not in lower_headers:
            raise ValidationFailedError("CSV must contain both 'name' and 'email' headers.")

        raw_rows = []
        for row in reader:
            if not row or not any(field.strip() for field in row):
                continue
            row_dict = dict(zip(headers, row, strict=False))
            raw_rows.append(row_dict)

        return self.process_raw_records(raw_rows, acceptance_policy=acceptance_policy)

    def parse_xlsx(
        self,
        file_bytes: bytes,
        acceptance_policy: AcceptancePolicy = "all_or_nothing",
    ) -> ImportValidationResult:
        """Parse and validate XLSX spreadsheet without executing formula expressions."""
        if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise ValidationFailedError(
                f"File size exceeds maximum upload limit of {settings.MAX_UPLOAD_SIZE_MB}MB."
            )

        try:
            # data_only=True ensures cached calculated values are loaded and formulas are not executed
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
            ws = wb.active
            if ws is None:
                raise ValidationFailedError("Uploaded XLSX workbook contains no active worksheets.")
        except Exception as exc:
            raise ValidationFailedError(f"Invalid or corrupt XLSX file: {exc}") from exc

        rows_iter = ws.iter_rows(values_only=True)
        try:
            raw_headers = next(rows_iter)
        except StopIteration:
            raise ValidationFailedError("Uploaded XLSX spreadsheet is empty.") from None

        if not raw_headers:
            raise ValidationFailedError("Spreadsheet has no headers.")

        headers = [str(h).strip() for h in raw_headers if h is not None]
        lower_headers = [h.lower() for h in headers]

        seen = set()
        for h in lower_headers:
            if h in seen:
                raise ValidationFailedError(f"Duplicate column header detected in XLSX: '{h}'")
            seen.add(h)

        if "name" not in lower_headers or "email" not in lower_headers:
            raise ValidationFailedError("Spreadsheet must contain both 'name' and 'email' headers.")

        raw_rows = []
        for row in rows_iter:
            if not row or not any(v is not None and str(v).strip() for v in row):
                continue
            row_dict = dict(zip(headers, row, strict=False))
            raw_rows.append(row_dict)

        wb.close()
        return self.process_raw_records(raw_rows, acceptance_policy=acceptance_policy)


import_service = ImportService()
