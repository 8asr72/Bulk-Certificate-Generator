"""Unit tests for ImportService, CSV/XLSX parsing, and acceptance policies."""

import io
from datetime import date

import openpyxl
import pytest

from core.exceptions import ValidationFailedError
from services.import_service import ImportService


@pytest.fixture
def import_service():
    return ImportService()


def test_import_valid_csv(import_service: ImportService):
    """Verify parsing a valid CSV file."""
    csv_content = (
        b"name,email,issue_date,external_reference\n"
        b"Alice Johnson,alice@example.com,2026-06-15,REF001\n"
        b"Bob Smith,bob@example.com,2026-06-16,REF002\n"
    )

    result = import_service.parse_csv(csv_content, acceptance_policy="all_or_nothing")
    assert len(result.valid_recipients) == 2
    assert result.valid_recipients[0].name == "Alice Johnson"
    assert result.valid_recipients[0].email == "alice@example.com"
    assert result.valid_recipients[0].issue_date == date(2026, 6, 15)
    assert result.valid_recipients[0].external_reference == "REF001"


def test_import_csv_duplicate_headers(import_service: ImportService):
    """Verify CSV with duplicate header is rejected."""
    csv_content = b"name,email,name\nJohn,john@example.com,John2\n"
    with pytest.raises(ValidationFailedError) as exc:
        import_service.parse_csv(csv_content)
    assert "Duplicate column header" in str(exc.value)


def test_import_csv_missing_required_headers(import_service: ImportService):
    """Verify CSV missing required 'email' header is rejected."""
    csv_content = b"name,date\nJohn,2026-01-01\n"
    with pytest.raises(ValidationFailedError) as exc:
        import_service.parse_csv(csv_content)
    assert "must contain both 'name' and 'email'" in str(exc.value)


def test_all_or_nothing_policy_rejects_mixed_batch(import_service: ImportService):
    """Verify all_or_nothing policy rejects batch if any row is invalid."""
    csv_content = b"name,email\nValid User,valid@example.com\nInvalid User,not-an-email\n"

    with pytest.raises(ValidationFailedError) as exc:
        import_service.parse_csv(csv_content, acceptance_policy="all_or_nothing")
    assert len(exc.value.errors) == 1
    assert exc.value.errors[0]["row"] == 2


def test_partial_acceptance_policy_accepts_valid_rows(import_service: ImportService):
    """Verify partial_acceptance policy accepts valid rows and returns row errors."""
    csv_content = (
        b"name,email\n"
        b"Valid User,valid@example.com\n"
        b"Invalid User,bad-email-format\n"
        b"Another Valid,second@example.com\n"
    )

    result = import_service.parse_csv(csv_content, acceptance_policy="partial_acceptance")
    assert len(result.valid_recipients) == 2
    assert len(result.errors) == 1
    assert result.errors[0]["row"] == 2
    assert "Invalid email" in result.errors[0]["error"]


def test_import_valid_xlsx(import_service: ImportService):
    """Verify parsing a valid XLSX spreadsheet without formula execution."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Recipients"
    ws.append(["Name", "Email", "Date"])
    ws.append(["Carlos Ruiz", "carlos@example.com", "2026-07-20"])
    ws.append(["Diana Prince", "diana@example.com", "2026-07-21"])

    stream = io.BytesIO()
    wb.save(stream)
    xlsx_bytes = stream.getvalue()

    result = import_service.parse_xlsx(xlsx_bytes, acceptance_policy="all_or_nothing")
    assert len(result.valid_recipients) == 2
    assert result.valid_recipients[0].name == "Carlos Ruiz"
    assert result.valid_recipients[0].email == "carlos@example.com"
    assert result.valid_recipients[1].name == "Diana Prince"
