#!/usr/bin/env bash
# ============================================================================
# RetailIQ — Production Entrypoint
# Dispatches to API / Worker / Beat based on SERVICE_ROLE env var.
# Runs Alembic migrations (with distributed lock) for the API role only.
# ============================================================================
set -euo pipefail

SERVICE_ROLE="${SERVICE_ROLE:-api}"

# ── Logging helper ──────────────────────────────────────────────────────────
log() { echo "[entrypoint] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

# ── Wait for database ──────────────────────────────────────────────────────
wait_for_db() {
    log "Waiting for PostgreSQL to become ready …"
    python scripts/wait_for_db.py
    log "PostgreSQL is ready."
}

# ── Run Alembic migrations (with Redis distributed lock) ───────────────────
run_migrations() {
    log "Attempting to acquire migration lock …"

    # Use a simple Redis-based lock to prevent multiple API containers from
    # running migrations simultaneously during a rolling deployment.
    python -c "
import os, sys, time, redis as r
url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
client = r.Redis.from_url(url, decode_responses=True)
lock_key = 'lock:alembic_migration'
lock_ttl = 300  # 5 minutes

# Try to acquire the lock
if client.set(lock_key, '1', nx=True, ex=lock_ttl):
    print('[entrypoint] Migration lock acquired.')
    sys.exit(0)
else:
    # Another container is running migrations — wait for it to finish
    print('[entrypoint] Migration lock held by another process; waiting …')
    for _ in range(lock_ttl):
        time.sleep(1)
        if not client.exists(lock_key):
            print('[entrypoint] Lock released by leader; migrations complete.')
            sys.exit(10)
    print('[entrypoint] Timeout waiting for migration lock.', file=sys.stderr)
    sys.exit(10)
"
    LOCK_EXIT=$?

    if [ "$LOCK_EXIT" -eq 0 ]; then
        log "Running Alembic migrations …"
        alembic upgrade head
        MIGRATION_EXIT=$?

        # Release the lock regardless of migration outcome
        python -c "
import os, redis as r
url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
client = r.Redis.from_url(url, decode_responses=True)
client.delete('lock:alembic_migration')
print('[entrypoint] Migration lock released.')
"
        if [ "$MIGRATION_EXIT" -ne 0 ]; then
            log "ERROR: Alembic migrations failed (exit code $MIGRATION_EXIT)."
            exit 1
        fi
        log "Migrations completed successfully."
    else
        log "Skipping migrations (another container handled them)."
    fi
}

# ── Service dispatch ───────────────────────────────────────────────────────
case "$SERVICE_ROLE" in

    api)
        wait_for_db
        run_migrations
        log "Starting Gunicorn API server …"
        exec gunicorn -c gunicorn.conf.py wsgi:app
        ;;

    worker)
        wait_for_db
        CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-4}"
        CELERY_QUEUES="${CELERY_QUEUES:-celery}"
        log "Starting Celery worker (concurrency=$CELERY_CONCURRENCY, queues=$CELERY_QUEUES) …"
        exec celery -A celery_worker.celery_app worker \
            --loglevel=info \
            --concurrency="$CELERY_CONCURRENCY" \
            --queues="$CELERY_QUEUES" \
            --without-heartbeat \
            --without-mingle \
            --without-gossip \
            --max-tasks-per-child=1000
        ;;

    beat)
        wait_for_db
        log "Starting Celery Beat scheduler …"
        exec celery -A celery_worker.celery_app beat \
            --loglevel=info
        ;;

    *)
        log "ERROR: Unknown SERVICE_ROLE '$SERVICE_ROLE'. Expected: api | worker | beat"
        exit 1
        ;;
esac
