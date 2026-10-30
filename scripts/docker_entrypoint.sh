#!/usr/bin/env bash
set -euo pipefail

echo "[Arthentic Boot] Synchronizing contract ABIs..."
python3 /app/scripts/sync_abis.py || true

echo "[Arthentic Boot] Running consolidated 6-Domain Alembic migrations..."
alembic upgrade head || echo "[Arthentic Boot] Alembic upgrade skipped or handled via ORM metadata"

echo "[Arthentic Boot] Seeding initial roles and demo fixtures..."
python3 -c "from server.db.seed import seed_dev_users; seed_dev_users()" || true

echo "[Arthentic Boot] Starting FastAPI Modular Monolith on 0.0.0.0:8000..."
exec uvicorn server.main:app --host 0.0.0.0 --port 8000
