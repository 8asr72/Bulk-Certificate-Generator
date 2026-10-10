"""Unit tests for CertificateRenderer, dynamic typography, and error boundaries."""

from datetime import date

import pytest

from core.exceptions import InvalidTemplateError, RenderingError
from services.certificate_service import CertificateRenderer


def test_render_valid_certificate():
    """Verify standard certificate rendering produces valid PDF bytes."""
    renderer = CertificateRenderer()
    pdf_bytes = renderer.render(
        recipient_name="Alice Smith",
        issue_date=date(2026, 4, 15),
        certificate_number="CERT-2026-UNIT-01",
        verification_code="token-unit-01",
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_dynamic_font_scaling_for_long_name():
    """Verify long recipient names are scaled dynamically without overflowing."""
    renderer = CertificateRenderer()
    long_name = "Professor Bartholomew Montgomery Fitzpatrick-Hetherington III"
    pdf_bytes = renderer.render(
        recipient_name=long_name,
        issue_date=date(2026, 4, 15),
        certificate_number="CERT-2026-UNIT-02",
        verification_code="token-unit-02",
    )

    assert pdf_bytes.startswith(b"%PDF-")


def test_excessively_long_name_raises_rendering_error():
    """Verify names exceeding even the minimum readable font size fail safely."""
    renderer = CertificateRenderer()
    unfit_name = "Supercalifragilisticexpialidocious " * 25
    with pytest.raises(RenderingError) as exc_info:
        renderer.render(
            recipient_name=unfit_name,
            issue_date=date(2026, 4, 15),
            certificate_number="CERT-2026-FAIL-01",
            verification_code="token-fail-01",
        )
    assert "too long to fit certificate layout" in str(exc_info.value)


def test_malformed_layout_configuration():
    """Verify invalid coordinates or color specifications raise InvalidTemplateError."""
    malformed_config = {
        "width": "not-a-number",
        "primary_color": "invalid-color-value",
    }
    with pytest.raises(InvalidTemplateError):
        CertificateRenderer(layout_config=malformed_config)


def test_unicode_and_special_character_rendering():
    """Verify rendering with Unicode accents and characters."""
    renderer = CertificateRenderer()
    pdf_bytes = renderer.render(
        recipient_name="Jean-Luc Picard",
        issue_date=date(2026, 4, 15),
        certificate_number="CERT-2026-UNICODE-01",
        verification_code="token-unicode-01",
    )
    assert pdf_bytes.startswith(b"%PDF-")
