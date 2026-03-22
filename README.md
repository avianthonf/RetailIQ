# RetailIQ Backend

RetailIQ is the Flask backend for the RetailIQ retail operating system. This repository is aligned to the current verified frontend contracts and the workspace parity source of truth.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Railway (GCP)                                                  │
│  ┌──────────────────────┐   ┌─────────────────────────────┐    │
│  │  Gunicorn (1 worker) │   │  Celery Worker (concurrency=2)│  │
│  │  ├─ Flask App        │   │  ├─ Forecast batch jobs      │  │
│  │  ├─ Auth (JWT+OTP)   │   │  ├─ OCR processing          │  │
│  │  ├─ REST API v1/v2   │   │  └─ Notification delivery   │  │
│  │  └─ CORS middleware  │   └──────────┬──────────────────┘   │
│  └──────────┬───────────┘              │                       │
│             │                          │                       │
│  ┌──────────▼──────────────────────────▼──────────────────┐   │
│  │  PostgreSQL (Railway managed)                           │   │
│  │  ├─ Users, Stores, Transactions, Inventory             │   │
│  │  └─ Alembic migrations                                 │   │
│  └────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  Redis (Railway managed)                                │   │
│  │  ├─ OTP storage (TTL-based)                            │   │
│  │  ├─ Refresh token storage                              │   │
│  │  ├─ Rate limiting backend                              │   │
│  │  └─ Celery broker/result backend                       │   │
│  └────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │
         │ SMTP_SSL (port 465)
         ▼
┌────────────────────┐
│  Gmail SMTP        │
│  (App Password)    │
│  OTP / Reset emails│
└────────────────────┘
```

### Key Components

- **Web Framework**: Flask 3.1 + Gunicorn (gthread worker)
- **Database**: PostgreSQL via SQLAlchemy 2.0 + Alembic migrations
- **Cache/Queue**: Redis 5.x — OTP store, refresh tokens, Celery broker
- **Auth**: JWT (HS256) access/refresh tokens + 6-digit OTP email verification
- **Email**: Gmail SMTP via `smtplib.SMTP_SSL` (port 465) for Railway/GCP compatibility
- **Task Queue**: Celery 5.4 for async jobs (forecasting, OCR, notifications)
- **Rate Limiting**: Flask-Limiter backed by Redis

## Developer & Engineer Guide

### Local Development

```bash
# 1. Install dependencies
pip install -r requirements-core.txt

# 2. Set up .env (copy from .env.example)
cp .env.example .env

# 3. Start PostgreSQL + Redis (Docker)
docker-compose up -d

# 4. Run migrations
alembic upgrade head

# 5. Start dev server
flask run --port 5000
```

### Railway Deployment

The app deploys via `Dockerfile.railway` → `scripts/start_combined.sh` which runs:
1. Database migration (`alembic upgrade head`)
2. Gunicorn API server (background)
3. Celery worker (foreground)

#### Required Railway Environment Variables

| Variable | Example | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql://...` | Railway auto-injects |
| `REDIS_URL` | `redis://...` | Railway Redis service |
| `SECRET_KEY` | (random 64+ chars) | Flask session signing |
| `JWT_SECRET_KEY` | (random 64+ chars) | JWT token signing |
| `SMTP_HOST` | `smtp.gmail.com` | Gmail SMTP server |
| `SMTP_PORT` | `465` | **Must be 465** — Railway/GCP blocks port 587 |
| `SMTP_USER` | `you@gmail.com` | Gmail address |
| `SMTP_PASSWORD` | `abcdefghijklmnop` | Gmail App Password (16 chars) |
| `EMAIL_ENABLED` | `true` | Enable email delivery |
| `ENVIRONMENT` | `production` | Activates prod checks |
| `FLASK_ENV` | `production` | Config selector |
| `PYTHONUNBUFFERED` | `1` | Ensures logs stream to Railway |

#### Email Configuration (Railway-specific)

Railway runs on GCP which blocks outbound SMTP on port 587 (STARTTLS). The email service (`app/email.py`) supports two modes:

- **Port 465** (`SMTP_SSL`): Direct SSL — **required for Railway / GCP**
- **Port 587** (`STARTTLS`): Works locally and on providers that allow it

The diagnostic endpoint `GET /api/v1/auth/email-health` tests SMTP connectivity without sending a real email. Use it to verify configuration after deployment.

#### Logging Architecture

All Python logs are routed to `stdout` via an explicit `StreamHandler` in `app/factory.py`. Combined with `PYTHONUNBUFFERED=1` in the Dockerfile, every log line streams immediately to Railway's log viewer. Gunicorn access/error logs also go to stdout (`--access-logfile -` `--error-logfile -`).

Log format: `%(asctime)s %(levelname)s %(name)s: %(message)s`

Key log prefixes to search for:
- `[EMAIL]` — SMTP send attempts, successes, and failures
- `[EMAIL-HEALTH]` — Diagnostic endpoint results
- `[DEV]` — OTP console fallback (dev only)
- `[DISABLED-EMAIL]` — Email disabled or misconfigured

### API Structure

All endpoints live under `/api/v1/` (v2 for AI and finance):

| Module | Prefix | Purpose |
|--------|--------|---------|
| `auth` | `/api/v1/auth` | Register, login, OTP, MFA, password reset |
| `store` | `/api/v1/store` | Store CRUD, settings |
| `inventory` | `/api/v1/inventory` | Product management, stock |
| `transactions` | `/api/v1/transactions` | Sales, POS |
| `customers` | `/api/v1/customers` | Customer profiles, loyalty |
| `analytics` | `/api/v1/analytics` | Reports, dashboards |
| `forecasting` | `/api/v1/forecasting` | Demand predictions |
| `team` | `/api/v1/team` | Staff management |
| `ai_v2` | `/api/v2/ai` | AI-powered features |

### Auth Flow

1. **Registration**: `POST /api/v1/auth/register` → OTP email sent → `POST /api/v1/auth/verify-otp` → JWT tokens returned
2. **Login (email)**: `POST /api/v1/auth/login` with email → OTP email sent → `POST /api/v1/auth/verify-otp` → JWT tokens
3. **Login (mobile+password)**: `POST /api/v1/auth/login` with mobile_number + password → JWT tokens (if no MFA)
4. **Token refresh**: `POST /api/v1/auth/refresh` with refresh_token → new access + refresh tokens

## Current Verified Status

- Backend route mapping is closed
- Backend `ruff format --check .` passed
- Backend `ruff check app tests` passed
- Backend `pytest -q` passed
- Backend `pip_audit` passed for `requirements.txt` and `requirements-core.txt`
- Live smoke checks against the deployed backend passed for `/health`, `/`, `/api/v1/ops/maintenance`, and `/api/v1/team/ping`

## Source Of Truth

The canonical parity artifacts live in the workspace folder:

- `D:/Files/Desktop/Retailiq-Frnt-Bknd-Shortcuts/parity-source-of-truth.md`
- `D:/Files/Desktop/Retailiq-Frnt-Bknd-Shortcuts/parity-summary.json`
- `D:/Files/Desktop/Retailiq-Frnt-Bknd-Shortcuts/backend-to-frontend-matrix.csv`
- `D:/Files/Desktop/Retailiq-Frnt-Bknd-Shortcuts/frontend-to-backend-matrix.csv`

## Notes

- Keep backend contracts aligned with the parity source of truth.
- Do not reintroduce mock dashboard data or stale audit claims into this README.
