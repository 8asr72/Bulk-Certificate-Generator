"""Certificate rendering engine using ReportLab with dynamic typography and security bounds."""

import io
from datetime import date
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from core.exceptions import InvalidTemplateError, RenderingError
from core.logging import logger
from models.template import DEFAULT_LAYOUT_CONFIG


class CertificateRenderer:
    """Renders professional PDF certificates deterministically with dynamic font scaling."""

    def __init__(self, layout_config: dict[str, Any] | None = None):
        self.layout = layout_config or DEFAULT_LAYOUT_CONFIG
        self._validate_layout()

    def _validate_layout(self) -> None:
        """Sanitize and validate layout parameters to prevent code execution and malformed geometry."""
        try:
            self.width = float(self.layout.get("width", 841.89))
            self.height = float(self.layout.get("height", 595.27))
            self.primary_color = HexColor(self.layout.get("primary_color", "#1A365D"))
            self.secondary_color = HexColor(self.layout.get("secondary_color", "#2B6CB0"))
            self.accent_color = HexColor(self.layout.get("accent_color", "#D69E2E"))
            self.text_color = HexColor(self.layout.get("text_color", "#2D3748"))
        except Exception as exc:
            raise InvalidTemplateError(
                f"Malformed template color or dimension configuration: {exc}"
            ) from exc

    def _calculate_scaled_font(
        self,
        text: str,
        font_name: str,
        initial_size: float,
        min_size: float,
        max_width: float,
    ) -> float:
        """Dynamically reduce font size so text fits inside max_width boundary."""
        current_size = initial_size
        while current_size >= min_size:
            width = pdfmetrics.stringWidth(text, font_name, current_size)
            if width <= max_width:
                return current_size
            current_size -= 1.0

        # Check if text fits even at min_size
        final_width = pdfmetrics.stringWidth(text, font_name, min_size)
        if final_width > max_width:
            raise RenderingError(
                f"Content '{text[:30]}...' too long to fit certificate layout at minimum readable font size {min_size}pt."
            )
        return min_size

    def _draw_decorations(self, c: canvas.Canvas) -> None:
        """Draw sophisticated multi-tier borders and rosette seal."""
        margin = float(self.layout.get("decorations", {}).get("border_margin", 24.0))
        border_width = float(self.layout.get("decorations", {}).get("border_width", 6.0))
        inner_margin = margin + 8.0

        # Primary outer border
        c.saveState()
        c.setStrokeColor(self.primary_color)
        c.setLineWidth(border_width)
        c.rect(margin, margin, self.width - 2 * margin, self.height - 2 * margin)

        # Secondary inner gold border
        c.setStrokeColor(self.accent_color)
        c.setLineWidth(1.5)
        c.rect(
            inner_margin,
            inner_margin,
            self.width - 2 * inner_margin,
            self.height - 2 * inner_margin,
        )

        # Corner corner accents
        c.setFillColor(self.accent_color)
        accent_size = 12.0
        for x, y in [
            (inner_margin + 6, inner_margin + 6),
            (self.width - inner_margin - 6 - accent_size, inner_margin + 6),
            (inner_margin + 6, self.height - inner_margin - 6 - accent_size),
            (
                self.width - inner_margin - 6 - accent_size,
                self.height - inner_margin - 6 - accent_size,
            ),
        ]:
            c.rect(x, y, accent_size, accent_size, fill=1, stroke=0)

        # Draw ornamental seal at bottom center
        seal_x = self.width / 2.0
        seal_y = 115.0
        c.setFillColor(self.accent_color)
        c.setStrokeColor(self.primary_color)
        c.setLineWidth(2.0)
        c.circle(seal_x, seal_y, 28.0, fill=1, stroke=1)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(seal_x, seal_y + 4, "OFFICIAL")
        c.drawCentredString(seal_x, seal_y - 6, "SEAL")
        c.restoreState()

    def _draw_text_item(
        self,
        c: canvas.Canvas,
        text: str,
        font_cfg: dict[str, Any],
        coord_cfg: dict[str, Any],
        fallback_color: HexColor,
    ) -> None:
        """Render individual text element with alignment and optional width constraints."""
        font_name = font_cfg.get("name", "Helvetica")
        font_size = float(font_cfg.get("size", 12))
        min_size = float(font_cfg.get("min_size", 10))
        color_hex = font_cfg.get("color")
        color = HexColor(color_hex) if color_hex else fallback_color

        x = float(coord_cfg.get("x", self.width / 2.0))
        y = float(coord_cfg.get("y", self.height / 2.0))
        align = coord_cfg.get("align", "center")
        max_width = coord_cfg.get("max_width")

        if max_width:
            font_size = self._calculate_scaled_font(
                text=text,
                font_name=font_name,
                initial_size=font_size,
                min_size=min_size,
                max_width=float(max_width),
            )

        c.saveState()
        c.setFont(font_name, font_size)
        c.setFillColor(color)

        if align == "center":
            c.drawCentredString(x, y, text)
        elif align == "right":
            c.drawRightString(x, y, text)
        else:
            c.drawString(x, y, text)

        c.restoreState()

    def render(
        self,
        recipient_name: str,
        issue_date: date,
        certificate_number: str,
        verification_code: str,
        title: str = "Certificate of Completion",
        description: str = "For demonstrating proficiency and successfully meeting all certification criteria",
        issuer_name: str = "Accredited Certification Authority",
        verification_base_url: str = "https://verify.certplatform.org/verify/",
    ) -> bytes:
        """Generate a complete PDF certificate and return valid binary PDF bytes."""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(self.width, self.height))

        # 1. Background decorations
        self._draw_decorations(c)

        fonts = self.layout.get("fonts", {})
        coords = self.layout.get("coordinates", {})

        # 2. Certificate Title
        if "title" in coords and "title" in fonts:
            self._draw_text_item(c, title, fonts["title"], coords["title"], self.primary_color)

        # 3. Subtitle ("PROUDLY PRESENTED TO")
        if "subtitle" in coords and "subtitle" in fonts:
            self._draw_text_item(
                c,
                "THIS IS PROUDLY PRESENTED TO",
                fonts["subtitle"],
                coords["subtitle"],
                self.secondary_color,
            )

        # 4. Recipient Name with dynamic scaling
        if "recipient_name" in coords and "recipient_name" in fonts:
            self._draw_text_item(
                c,
                recipient_name,
                fonts["recipient_name"],
                coords["recipient_name"],
                self.secondary_color,
            )

        # 5. Description
        if "description" in coords and "description" in fonts:
            self._draw_text_item(
                c, description, fonts["description"], coords["description"], self.text_color
            )

        # 6. Issuer Organization
        if "issuer" in coords and "issuer" in fonts:
            self._draw_text_item(
                c,
                f"Authorized by: {issuer_name}",
                fonts["issuer"],
                coords["issuer"],
                self.primary_color,
            )

        # 7. Issue Date
        if "issue_date" in coords and "meta" in fonts:
            formatted_date = issue_date.strftime("%B %d, %Y")
            self._draw_text_item(
                c,
                f"Issued On: {formatted_date}",
                fonts["meta"],
                coords["issue_date"],
                self.text_color,
            )

        # 8. Certificate Number
        if "certificate_number" in coords and "meta" in fonts:
            self._draw_text_item(
                c,
                f"Certificate No: {certificate_number}",
                fonts["meta"],
                coords["certificate_number"],
                self.text_color,
            )

        # 9. Verification Code
        if "verification_code" in coords and "meta" in fonts:
            self._draw_text_item(
                c,
                f"Verification Code: {verification_code}",
                fonts["meta"],
                coords["verification_code"],
                self.text_color,
            )

        # Finalize canvas
        c.showPage()
        c.save()

        pdf_bytes = buffer.getvalue()
        buffer.close()

        # Strict PDF integrity validation (first 5 bytes must be '%PDF-')
        if not pdf_bytes.startswith(b"%PDF-"):
            raise RenderingError("Generated output failed PDF integrity validation header check.")

        logger.debug(
            f"Successfully rendered certificate for '{recipient_name}' ({len(pdf_bytes)} bytes, serial={certificate_number})"
        )
        return pdf_bytes


certificate_renderer = CertificateRenderer()
