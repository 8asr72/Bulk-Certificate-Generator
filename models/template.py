"""CertificateTemplate model representing reusable, versioned visual layouts."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import BaseModel

if TYPE_CHECKING:
    from models.job import GenerationJob

DEFAULT_LAYOUT_CONFIG: dict[str, Any] = {
    "page_size": "A4_LANDSCAPE",
    "width": 841.89,  # Points (ReportLab standard A4 landscape)
    "height": 595.27,
    "primary_color": "#1A365D",
    "secondary_color": "#2B6CB0",
    "accent_color": "#D69E2E",
    "text_color": "#2D3748",
    "fonts": {
        "title": {"name": "Helvetica-Bold", "size": 28, "color": "#1A365D"},
        "subtitle": {"name": "Helvetica", "size": 14, "color": "#718096"},
        "recipient_name": {
            "name": "Helvetica-Bold",
            "size": 34,
            "min_size": 14,
            "color": "#2B6CB0",
        },
        "description": {"name": "Helvetica", "size": 15, "color": "#4A5568"},
        "issuer": {"name": "Helvetica-Bold", "size": 16, "color": "#2D3748"},
        "meta": {"name": "Helvetica", "size": 10, "color": "#718096"},
    },
    "coordinates": {
        "title": {"x": 420.94, "y": 480.0, "align": "center"},
        "subtitle": {"x": 420.94, "y": 445.0, "align": "center"},
        "recipient_name": {"x": 420.94, "y": 360.0, "max_width": 620.0, "align": "center"},
        "description": {"x": 420.94, "y": 290.0, "max_width": 640.0, "align": "center"},
        "issuer": {"x": 220.0, "y": 140.0, "align": "center"},
        "issue_date": {"x": 620.0, "y": 140.0, "align": "center"},
        "certificate_number": {"x": 50.0, "y": 45.0, "align": "left"},
        "verification_code": {"x": 791.89, "y": 45.0, "align": "right"},
    },
    "decorations": {
        "border_width": 6.0,
        "inner_border_width": 1.5,
        "border_margin": 24.0,
        "show_seal": True,
    },
}


class CertificateTemplate(BaseModel):
    """Reusable, versioned certificate template definition."""

    __tablename__ = "certificate_templates"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_template_name_version"),)

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    title: Mapped[str] = mapped_column(
        String(255),
        default="Certificate of Completion",
        nullable=False,
    )
    description_pattern: Mapped[str] = mapped_column(
        Text,
        default="For successfully completing the certification requirements",
        nullable=False,
    )
    issuer_name: Mapped[str] = mapped_column(
        String(255),
        default="Accredited Certification Authority",
        nullable=False,
    )
    background_asset_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    layout_config: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=DEFAULT_LAYOUT_CONFIG,
        nullable=False,
    )

    # Relationships
    jobs: Mapped[list["GenerationJob"]] = relationship(
        "GenerationJob",
        back_populates="template",
        cascade="all, delete-orphan",
    )
