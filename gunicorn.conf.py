# ============================================================================
# RetailIQ — Gunicorn Production Configuration
# ============================================================================
import multiprocessing
import os

# ---------------------------------------------------------------------------
# Server socket
# ---------------------------------------------------------------------------
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:5000")

# ---------------------------------------------------------------------------
# Worker processes
# ---------------------------------------------------------------------------
# Fargate vCPU is typically 0.25–4 vCPU. Formula: min(cpu_count * 2 + 1, max)
# For 1 vCPU Fargate task → 3 workers; for 0.5 vCPU → 2 workers.
_max_workers = int(os.environ.get("GUNICORN_MAX_WORKERS", "4"))
workers = min(multiprocessing.cpu_count() * 2 + 1, _max_workers)

# gthread: threaded workers — good for I/O-bound Flask apps (DB/Redis calls)
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

# ---------------------------------------------------------------------------
# Preloading
# ---------------------------------------------------------------------------
# Preload the application to share memory across forked workers.
# Reduces per-worker memory by ~30-40% for Prophet/sklearn models.
preload_app = True

# ---------------------------------------------------------------------------
# Logging (stdout/stderr for CloudWatch / container log drivers)
# ---------------------------------------------------------------------------
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Structured access log format (JSON-friendly)
access_log_format = (
    '{"remote_ip":"%(h)s","request":"%(r)s","status":"%(s)s",'
    '"response_length":"%(b)s","referer":"%(f)s","user_agent":"%(a)s",'
    '"request_time_s":"%(D)s"}'
)

# ---------------------------------------------------------------------------
# Process naming
# ---------------------------------------------------------------------------
proc_name = "retailiq-api"

# ---------------------------------------------------------------------------
# Server mechanics
# ---------------------------------------------------------------------------
# Maximum number of pending connections
backlog = 2048

# Maximum number of requests a worker will process before restarting
# (mitigates memory leaks from Prophet/sklearn)
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "2000"))
max_requests_jitter = 200

# Restart workers if RSS exceeds this value (bytes) — not natively supported
# but useful as documentation for external monitoring thresholds.
# Recommended: monitor container RSS via CloudWatch and alert at 80% of task memory.

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
# Limit request line and header sizes
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# Forwarded-allow-ips — trust ALB private IPs
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "*")
