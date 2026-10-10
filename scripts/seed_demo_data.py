import csv
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import models  # noqa: F401
from core.database import Base, SessionLocal, check_db_connection, engine
from models import DEFAULT_LAYOUT_CONFIG, CertificateTemplate

SAMPLE_RECIPIENTS = [
    {
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "issue_date": "2026-06-01",
        "external_reference": "ACAD-2026-001",
    },
    {
        "name": "Prof. Alexander Montgomery Featherstone-Smythe III",
        "email": "alexander.featherstone@example.com",
        "issue_date": "2026-06-01",
        "external_reference": "ACAD-2026-002",
    },
    {
        "name": "Carlos Ruiz Hernandez",
        "email": "carlos.ruiz@example.com",
        "issue_date": "2026-06-02",
        "external_reference": "ACAD-2026-003",
    },
    {
        "name": "Aisha Patel",
        "email": "aisha.patel@example.com",
        "issue_date": "2026-06-02",
        "external_reference": "ACAD-2026-004",
    },
]


def create_sample_files(target_dir: Path) -> None:
    """Generate sample CSV and XLSX fixture files."""
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate CSV
    csv_path = target_dir / "recipients_sample.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "issue_date", "external_reference"])
        writer.writeheader()
        writer.writerows(SAMPLE_RECIPIENTS)
    print(f"[+] Created sample CSV file: {csv_path}")

    # 2. Generate XLSX
    xlsx_path = target_dir / "recipients_sample.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Recipients"
    ws.append(["Name", "Email", "Issue_Date", "External_Reference"])
    for r in SAMPLE_RECIPIENTS:
        ws.append([r["name"], r["email"], r["issue_date"], r["external_reference"]])
    wb.save(xlsx_path)
    print(f"[+] Created sample XLSX file: {xlsx_path}")


def seed_database_templates() -> None:
    """Seed sample templates if database is accessible."""
    if not check_db_connection():
        print("[!] Database not reachable; skipping live template database insertion.")
        return

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = (
            db.query(CertificateTemplate)
            .filter(CertificateTemplate.name == "Executive Leadership")
            .first()
        )
        if not existing:
            template = CertificateTemplate(
                name="Executive Leadership",
                version=1,
                is_active=True,
                title="Certificate of Executive Leadership",
                description_pattern="For demonstrated visionary leadership and organizational excellence",
                issuer_name="Global Executive Academy",
                layout_config=DEFAULT_LAYOUT_CONFIG,
            )
            db.add(template)
            db.commit()
            print("[+] Seeded default 'Executive Leadership' certificate template.")
        else:
            print("[*] Template 'Executive Leadership' already exists in database.")
    finally:
        db.close()


def main() -> None:
    print("=" * 60)
    print(" SEEDING DEMONSTRATION FIXTURES & TEMPLATES")
    print("=" * 60)
    examples_dir = Path(__file__).resolve().parent.parent / "examples"
    create_sample_files(examples_dir)
    seed_database_templates()
    print("=" * 60)
    print(" SEEDING COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
