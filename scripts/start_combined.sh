#!/bin/bash
# scripts/start_combined.sh

# ── 1. Wait for Database ──────────────────────────────────────────────────────
echo "Checking database availability..."
python scripts/wait_for_db.py

# ── 2. Run Migrations ─────────────────────────────────────────────────────────
echo "Running database migrations..."
alembic upgrade head

# ── 3. Start Gunicorn (API) in the background ─────────────────────────────────
# Reduced to 1 worker to save memory on the $20 credit tier.
echo "Starting Gunicorn (API)..."
gunicorn \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    wsgi:app &

# ── 4. Start Celery Worker (Background Tasks) in the foreground ───────────────
# Low concurrency to minimize RAM footprint.
echo "Starting Celery Worker..."
exec celery -A celery_worker.celery_app worker --loglevel=info --concurrency=2
