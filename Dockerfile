FROM python:3.10-slim

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    build-essential \
    libpq-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Create non-root user BEFORE installing packages ───────────────────────────
# pip installs into system site-packages (root-owned) — no chown needed later.
RUN useradd --create-home --shell /bin/bash --uid 1001 app

WORKDIR /app

# ── Python dependencies (root installs into system site-packages) ─────────────
RUN pip install --no-cache-dir --upgrade pip

COPY requirements-core.txt requirements-core.txt
RUN pip install --no-cache-dir -r requirements-core.txt

COPY requirements-ml.txt requirements-ml.txt
RUN pip install --no-cache-dir -r requirements-ml.txt

# ── Application source — owned by app at copy time, no recursive chown ────────
COPY --chown=app:app . .

USER app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--threads", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "wsgi:app"]
