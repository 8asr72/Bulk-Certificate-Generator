import importlib
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.database import check_db_connection

REQUIRED_PACKAGES = [
    ("fastapi", "FastAPI"),
    ("uvicorn", "Uvicorn"),
    ("pydantic", "Pydantic v2"),
    ("sqlalchemy", "SQLAlchemy 2.0"),
    ("alembic", "Alembic"),
    ("celery", "Celery"),
    ("redis", "Redis"),
    ("reportlab", "ReportLab PDF Engine"),
    ("PIL", "Pillow Image Library"),
    ("openpyxl", "OpenPyXL Spreadsheet Parser"),
    ("psycopg", "Psycopg PostgreSQL Driver"),
]


def check_python_version() -> bool:
    print("[*] Checking Python runtime...")
    ver = sys.version_info
    print(f"    - Current version: {ver.major}.{ver.minor}.{ver.micro}")
    if ver.major == 3 and ver.minor >= 11:
        print("    [+] Python version satisfies >=3.11 requirement.")
        return True
    print("    [-] Python version is below 3.11. Upgrade recommended.")
    return False


def check_packages() -> bool:
    print("\n[*] Checking required Python dependencies...")
    all_ok = True
    for pkg_name, display_name in REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(pkg_name)
            ver = getattr(mod, "__version__", "installed")
            print(f"    [+] {display_name:<30} (version {ver})")
        except ImportError as e:
            print(f"    [-] Missing package: {display_name:<20} ({e})")
            all_ok = False
    return all_ok


def check_storage() -> bool:
    print("\n[*] Checking storage directory access and permissions...")
    root = settings.storage_root_path
    cert_dir = settings.certificates_dir
    tmp_dir = settings.tmp_dir

    print(f"    - Storage Root:   {root}")
    print(f"    - Certificates:   {cert_dir}")
    print(f"    - Temp Staging:   {tmp_dir}")

    test_file = tmp_dir / "write_test.tmp"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        print("    [+] Storage write/delete test passed.")
        return True
    except Exception as exc:
        print(f"    [-] Storage test failed: {exc}")
        return False


def check_database() -> bool:
    print("\n[*] Checking database connectivity...")
    print(
        f"    - Configured URL: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}"
    )
    ok = check_db_connection()
    if ok:
        print("    [+] Database connection verified successfully.")
    else:
        print("    [!] Database is currently unreachable at configured connection string.")
        print(
            "        (Note: In Docker, postgres runs on host port 5432; in tests, SQLite is used)."
        )
    return ok


def main() -> int:
    print("=" * 60)
    print(" BULK CERTIFICATE GENERATION PLATFORM: ENVIRONMENT AUDIT")
    print("=" * 60)

    py_ok = check_python_version()
    pkg_ok = check_packages()
    stor_ok = check_storage()
    check_database()

    print("\n" + "=" * 60)
    if py_ok and pkg_ok and stor_ok:
        print(" ENVIRONMENT STATUS: HEALTHY AND READY")
        print("=" * 60)
        return 0
    else:
        print(" ENVIRONMENT STATUS: ACTION REQUIRED FOR MISSING ITEMS")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
