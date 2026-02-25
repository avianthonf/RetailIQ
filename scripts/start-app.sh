#!/usr/bin/env bash
set -euo pipefail

python scripts/wait_for_db.py
alembic upgrade head
exec gunicorn --bind 0.0.0.0:5000 wsgi:app
