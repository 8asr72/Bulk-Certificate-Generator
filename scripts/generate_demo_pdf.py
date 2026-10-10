"""Standalone demonstration script generating a realistic sample certificate PDF."""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

# Ensure project root is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.certificate_service import certificate_renderer


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a demo certificate PDF.")
    parser.add_argument(
        "--name",
        type=str,
        default="Dr. Alexander Montgomery Featherstone-Smythe III",
        help="Recipient name to display on the certificate",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="demo_certificate.pdf",
        help="Destination path for output PDF",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="Professional Master Certificate in Cloud Systems Architecture",
        help="Certificate title",
    )
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    print(f"[*] Rendering certificate for: '{args.name}'...")
    start_time = time.perf_counter()

    pdf_bytes = certificate_renderer.render(
        recipient_name=args.name,
        issue_date=date.today(),
        certificate_number="CERT-2026-DEMO-A1B2",
        verification_code="demo-verify-token-xyz987",
        title=args.title,
        description="For extraordinary mastery and distinguished contributions in distributed systems",
        issuer_name="International Institute of Distributed Computing",
    )

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    output_path.write_bytes(pdf_bytes)
    print("[+] Certificate generated successfully!")
    print(f"    - Output file: {output_path}")
    print(f"    - File size:   {len(pdf_bytes)} bytes")
    print(f"    - Render time: {elapsed_ms:.2f} ms")


if __name__ == "__main__":
    main()
