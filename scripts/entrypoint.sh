#!/bin/sh
set -e

echo "[*] Running database migrations with Alembic..."
alembic upgrade head
echo "[+] Database schema migrated successfully."

echo "[*] Starting application service: $@"
exec "$@"
