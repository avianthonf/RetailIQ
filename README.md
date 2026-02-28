# RetailIQ — Retail Data Platform

RetailIQ is a modular backend platform for retail operations intelligence. It combines:
- transactional APIs (auth, store, inventory, transactions, customers),
- analytics APIs backed by aggregate tables,
- forecasting (store + SKU),
- decision recommendations from deterministic rules,
- NLP-style deterministic query responses,
- **supplier management & purchase orders** (supplier tracking, PO lifecycle, stock receiving),
- barcode registry and receipt printing (barcode lookup, template management, async print jobs),
- **loyalty & credit** (points-based loyalty programs, credit ledger, atomic POS integration),
- **GST compliance** (HSN master, GSTIN validation, per-transaction GST recording, GSTR-1 generation),
- asynchronous background processing with Celery.

The platform is designed to run locally and in containerized environments with PostgreSQL + Redis.

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture End-to-End](#architecture-end-to-end)
3. [Repository Map](#repository-map)
4. [Request Lifecycle](#request-lifecycle)
5. [Data Model Overview](#data-model-overview)
6. [Asynchronous Tasking Model](#asynchronous-tasking-model)
7. [Forecasting + Decisions + NLP](#forecasting--decisions--nlp)
8. [Supplier Management Module](#supplier-management-module)
9. [Barcode & Receipt Printing Module](#barcode--receipt-printing-module)
10. [Staff Performance Module](#staff-performance-module)
11. [Offline Analytics Snapshot Module](#offline-analytics-snapshot-module)
12. [Loyalty & Credit Module](#loyalty--credit-module)
13. [GST Compliance Module](#gst-compliance-module)
14. [WhatsApp Business Integration](#whatsapp-business-integration)
15. [Chain Ownership & Multi-store Module](#chain-ownership--multi-store-module)
16. [Configuration and Environment Variables](#configuration-and-environment-variables)
17. [Running the System](#running-the-system)
18. [Testing Strategy](#testing-strategy)
19. [CI/CD](#cicd)
20. [Operations and Troubleshooting](#operations-and-troubleshooting)
21. [How to Modify the System Safely](#how-to-modify-the-system-safely)
22. [Production Readiness Checklist](#production-readiness-checklist)

---

## System Overview

RetailIQ is built as a Flask app using SQLAlchemy models and blueprint modules. It exposes versioned APIs under `/api/v1/...`, persists operational data in PostgreSQL, and offloads compute-heavy/periodic workflows to Celery workers.

### Core Capabilities
- **Auth + access control**: JWT-based auth with role gating (`owner`, `staff`).
- **Operational APIs**: inventory, transactions, customers, store configuration.
- **Analytics**: revenue/profit/category/payment/contribution views, mostly from aggregate tables.
- **Suppliers & POs**: Track active suppliers, linked products, purchase orders, and goods receipts.
- **Forecasting**: forecast cache for store-level and SKU-level projections.
- **Decision engine**: deterministic recommendations using rules over computed context.
- **NLP endpoint**: deterministic intent routing + template-based responses (not generative).
- **Staff Performance**: Session management, daily target setting, and automated role-based metric aggregations.
- **Loyalty & Credit**: Points-based loyalty programs, credit ledger, atomic loyalty accrual at transaction time, point redemption, credit sale enforcement, and automated point expiry.
- **GST Compliance**: HSN code management, GSTIN validation (modulo-36 checksum), per-transaction CGST/SGST recording, GSTR-1 JSON generation, and liability slab analytics.
- **WhatsApp Integration**: Outbound messaging (Alerts & Purchase Orders) via Meta Cloud API, secure Fernet token encryption at rest, and Meta webhook verification/handling.
- **Chain Ownership**: Multi-store grouping, chain-wide KPI dashboards, store comparison matrix with relative coding, and automated inter-store transfer suggestions.

---

## Architecture End-to-End

### High-level Components
- **Flask API (Gunicorn)**: serves REST endpoints.
- **PostgreSQL**: transactional + aggregate + forecast storage.
- **Redis**:
  - Celery broker,
  - rate limiter storage,
  - short-lived auth artifacts (OTP, reset, refresh token lookup),
  - lightweight distributed locks for task idempotency.
- **Celery Worker**: executes async jobs.
- **Celery Beat**: schedules periodic jobs.

### Runtime Topology (`docker-compose.yml`)
- `app`: API server container.
- `postgres`: database.
- `redis`: cache/broker.
- `worker`: Celery worker process.
- `beat`: Celery scheduler.

Startup behavior:
1. `app` runs `scripts/start-app.sh`.
2. Startup script ensures `.env` exists (copies from `.env.example` if missing).
3. Waits for DB readiness (`scripts/wait_for_db.py`).
4. Applies migrations (`alembic upgrade head`).
5. Starts Gunicorn.

This enables reliable first-run startup in Dockerized environments.

---

## Repository Map

```text
app/
  __init__.py                # Flask app factory, extension init, blueprint registration
  models/                    # SQLAlchemy schema (core tables + aggregate tables)
  auth/                      # registration/login/otp/refresh/logout/password reset
  store/                     # store profile + categories + tax config
  inventory/                 # product and stock workflows
  transactions/              # transaction ingest/list/return and service layer
  customers/                 # customer CRUD + customer analytics
  analytics/                 # analytics endpoints + helper utilities/cache wrapper
  forecasting/               # forecast engine + forecast API serving from cache
  decisions/                 # context builder + deterministic recommendation rules
  nlp/                       # deterministic intent router + templates + query endpoint
  tasks/                     # canonical Celery tasks + task DB session
  suppliers/                 # supplier CRUD, PO lifecycle, Goods Receiving
  staff_performance/         # session management, targets, team reports
  receipts/                  # barcode registry + receipt template + print job APIs
  loyalty/                   # loyalty programs, credit ledger, redemption, analytics
  gst/                       # GST config, HSN master, GSTIN validator, GSTR-1 generation
  whatsapp/                  # Meta API client, message logs, secure config, templates
  chain/                     # store groups, chain dashboard, compare, transfers
    __init__.py              # Blueprint definition
    routes.py                # 7 REST endpoints (barcodes + receipts)
    formatter.py             # build_receipt_payload() — pure dict builder

migrations/
  env.py                     # Alembic environment (reads DATABASE_URL)
  versions/                  # migration scripts

scripts/
  start-app.sh               # bootstrapping app startup script
  wait_for_db.py             # DB readiness probe

tests/
  conftest.py                # shared fixtures (in-memory SQLite test app)
  test_*.py                  # module-level tests

.github/workflows/
  test-on-commit.yml         # CI test workflow
```

---

## Request Lifecycle

1. Request enters Flask via Gunicorn.
2. Blueprint route validates payload via Marshmallow schemas.
3. `require_auth` decodes JWT and attaches identity (`g.current_user`).
4. Business logic executes via service layer and SQLAlchemy session.
5. Data is committed/rolled back.
6. Response is wrapped in standard response envelope in most modules.
7. Non-critical background follow-ups (aggregates/alerts/etc.) are queued asynchronously.

### Auth + Role Model
- Authenticated identity includes `user_id`, `store_id`, `role`.
- Role checks use decorators for owner-only operations.
- Refresh token lifecycle uses Redis token-keyed records with 30-day TTL.
- Access tokens (JWT/RS256) expire after 2 hours; clients must use `/auth/refresh` to renew.
- **Auto-login on signup**: `POST /auth/verify-otp` activates the account AND returns full auth tokens (`access_token`, `refresh_token`, `user_id`, `role`, `store_id`) — same shape as the login response. This allows mobile clients to skip the manual login step after registration.

---

## Data Model Overview

### Core transactional entities
- `users`, `stores`, `categories`, `products`, `customers`, `transactions`, `transaction_items`.
- Inventory/ops: `stock_adjustments`, `stock_audits`, `stock_audit_items`.

### Intelligence entities
- `alerts`
- `forecast_cache`
- Aggregate tables:
  - `daily_store_summary`
  - `daily_category_summary`
  - `daily_sku_summary`

### Supplier Management entities
- `suppliers`: registry of external vendors.
- `supplier_products`: many-to-many link resolving quoted price and lead time.
- `purchase_orders` & `purchase_order_items`: PO tracking structure.
- `goods_receipt_notes`: atomic ingestion of received products to store stock.

### Barcode & Receipt entities (migration `a3f91d2c5b88`)
- `barcodes`: barcode→product registry (unique `barcode_value`, per-store, FK to `products`).
- `receipt_templates`: per-store receipt config (header/footer/GSTIN flag/paper width).
- `print_jobs`: async print job records with JSONB payload and status tracking.

### Staff Performance entities
- `staff_sessions`: Start/end session logs for staff workers, status enumeration.
- `staff_daily_targets`: Goal metrics per user mapped by store and date.

### Loyalty & Credit entities (migration `a5f8e91c7b3d`)
- `loyalty_programs`: Per-store config — `points_per_rupee`, `redemption_rate`, `min_redemption_points`, `expiry_days`, `is_active`.
- `customer_loyalty_accounts`: Per-customer running balance — `total_points`, `redeemable_points`, `lifetime_earned`, `last_activity_at`.
- `loyalty_transactions`: Ledger entries with `type` CHECK(`EARN`, `REDEEM`, `EXPIRE`, `ADJUST`), linked to account and optionally to a sale transaction.
- `credit_ledger`: Per-customer/store credit state — `balance`, `credit_limit`, with UNIQUE(`customer_id`, `store_id`).
- `credit_transactions`: Credit ledger entries with `type` CHECK(`CREDIT_SALE`, `REPAYMENT`, `ADJUSTMENT`).
- `transactions.session_id`: Updated nullable attribution FK indexing transactions to sessions.

### Circular FK note (`users` ↔ `stores`)
The schema intentionally has a circular relationship:
- `stores.owner_user_id -> users.user_id`
- `users.store_id -> stores.store_id`

This is handled safely via migration ordering (create users without FK, create stores, then add FK) and explicit FK naming on model side.

---

## Asynchronous Tasking Model

Canonical tasks live in `app/tasks/tasks.py`.

### Major jobs
- `rebuild_daily_aggregates` / `rebuild_daily_aggregates_all_stores`
- `evaluate_alerts` / `evaluate_alerts_all_stores`
- `run_batch_forecasting`
- `forecast_store`
- `detect_slow_movers`
- `send_weekly_digest`
- `auto_close_open_sessions` (Ends orphaned staff sessions)
- `generate_staff_daily_summary` (Snapshot metrics via Redis caching)
- `build_analytics_snapshot` / `build_all_analytics_snapshots` (Offline analytics payload generation)
- `expire_loyalty_points` (Monthly on 1st: expire points from accounts inactive beyond `expiry_days`)
- `credit_overdue_alerts` (Daily: create HIGH-priority alerts for credit balances unpaid >30 days)

### Task Reliability Patterns
- Redis lock keys to avoid duplicate concurrent runs.
- Retries/backoff on selected tasks.
- DB writes via task-specific session manager (`app/tasks/db_session.py`).
- Transaction APIs fail-open for async dispatch (core writes succeed even if broker dispatch fails).

---

## Forecasting + Decisions + NLP

## Forecasting
- Engine (`app/forecasting/engine.py`) chooses model based on history size.
- Writes forecast points to `forecast_cache`.
- API endpoints serve from cache (no expensive compute in request path).

## Decisions
- Builds per-product context using stock, history, forecast, and store-level signals.
- Applies deterministic rule registry with confidence/priority/time-sensitive metadata.
- Returns sorted, de-duplicated recommendations.

## NLP Endpoint
- Keyword intent routing (`forecast`, `inventory`, `revenue`, `profit`, `top_products`, `loyalty_summary`, `credit_overdue`, default).
- SQL-backed metrics + deterministic templates.
- `loyalty_summary` template: enrolled customers, points issued/redeemed this month.
- `credit_overdue` template: count and total outstanding of overdue credit customers.
- Stable machine-readable output for frontend consumption.

## API Contracts (Hardened Shapes)
The return shapes of key analytical endpoints have been explicitly hardened:
- **Analytics Dashboard (`/api/v1/analytics/dashboard`)**: `revenue_7d` guarantees exactly 7 daily `{date, revenue}` objects (zero-filled). It also returns full `category_breakdown` (descending) and `payment_mode_breakdown` arrays.
- **Forecasting (`/api/v1/forecasting/sku/<sku_id>`)**: The forecast payload (`data`) separates historical context and future projections into `{ historical: [{date, actual}], forecast: [{date, predicted, lower_bound, upper_bound}] }`. Meta features `confidence_tier` (`prophet`/`ridge`/`flat`) and omits bounds (`null`) for fallback model types.

---

## Supplier Management Module

Blueprint registered under `/api/v1` (routes prefix themselves with `/suppliers` or `/purchase-orders`).

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/suppliers` | ✅ | List active suppliers with computed analytics (fill rate, avg lead time) |
| `POST` | `/api/v1/suppliers` | ✅ | Create new supplier profile |
| `GET` | `/api/v1/suppliers/<id>` | ✅ | Get supplier details, sourced products, and PO history |
| `PUT` | `/api/v1/suppliers/<id>` | ✅ | Update supplier profile |
| `DELETE` | `/api/v1/suppliers/<id>` | ✅ | Soft-delete supplier |
| `POST` | `/api/v1/suppliers/<id>/products` | ✅ | Link product to supplier with quoted price and lead time |
| `GET` | `/api/v1/purchase-orders` | ✅ | List purchase orders (optional `?status=` filter) |
| `POST` | `/api/v1/purchase-orders` | ✅ | Create new DRAFT PO with items |
| `PUT` | `/api/v1/purchase-orders/<id>/send` | ✅ | Transition PO from DRAFT to SENT |
| `POST` | `/api/v1/purchase-orders/<id>/receive` | ✅ | Atomic goods receipt: updates PO received_qty, updates product stock, creates GoodsReceiptNote, and auto-transitions to FULFILLED if complete |
| `PUT` | `/api/v1/purchase-orders/<id>/cancel` | ✅ | Transition PO to CANCELLED |

### Key Features
- **Atomic Receiving**: The `/receive` endpoint uses nested transactions (`db.session.begin_nested()`) to guarantee that product stock is only updated if the Goods Receipt Note and PO Item updates succeed.
- **Analytics**: Real-time computation of supplier fill rate, average lead time, and estimated 6-month price change delta using SQLAlchemy ORM aggregations.
- **Overdue PO Alerts**: A daily Celery task (`check_overdue_purchase_orders`) detects SENT POs past their expected delivery date and emits `MEDIUM` priority alerts.

---

## Barcode & Receipt Printing Module

Blueprint registered under `/api/v1` (routes prefix themselves with `/barcodes` or `/receipts`).

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/receipts/template` | ✅ | Get store receipt template (defaults if not set) |
| `PUT` | `/api/v1/receipts/template` | ✅ | Upsert receipt template for store |
| `POST` | `/api/v1/receipts/print` | ✅ | Create print job; body: `{transaction_id?, printer_mac_address?}` |
| `GET` | `/api/v1/receipts/print/<job_id>` | ✅ | Poll print job status |
| `GET` | `/api/v1/barcodes/lookup?value=…` | ✅ | Resolve barcode → product_id, name, stock, price |
| `POST` | `/api/v1/barcodes` | ✅ | Register barcode; body: `{product_id, barcode_value, barcode_type?}` |
| `GET` | `/api/v1/barcodes?product_id=…` | ✅ | List all barcodes for a product |

### Barcode validation
- `barcode_value` must match `^[A-Za-z0-9\-]{4,64}$`.
- Duplicate `barcode_value` across any store returns **409**.

### Receipt payload (`formatter.py`)
`build_receipt_payload(transaction_id, store_id, db_session) -> dict` returns:
```
{ store_name, store_address, gstin?, items:[{name,qty,unit_price,line_total}],
  subtotal, discount_total, tax_total, grand_total, payment_mode,
  timestamp, transaction_ref, header_text, footer_text }
```

### Database tables added
- **`barcodes`** — `id`, `product_id FK`, `store_id FK`, `barcode_value UNIQUE`, `barcode_type`, `created_at`
- **`receipt_templates`** — `id`, `store_id UNIQUE FK`, `header_text`, `footer_text`, `show_gstin`, `paper_width_mm`, `updated_at`
- **`print_jobs`** — `id`, `store_id FK`, `transaction_id FK?`, `job_type`, `status`, `payload JSONB`, `created_at`, `completed_at`

---

## Offline Analytics Snapshot Module

Blueprint registered under `/api/v1/offline`.

### Features
- Provides a compact (**<= 50KB**) JSON snapshot of key metrics (KPIs, 30-day revenue history, top products, low stock, and open alerts).
- Designed to allow mobile clients (like DataSage) to download the snapshot when online and render meaningful charts and alerts while completely offline.
- Contains size-enforcement rules that automatically truncate historical arrays if the payload exceeds limits.

### Endpoints
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/offline/snapshot` | ✅ | Returns the latest snapshot. If one does not exist or is missing, triggers a `build_analytics_snapshot` celery task and responds with HTTP 202. |

### Architecture
- **Table**: `analytics_snapshots` directly stores the JSON payload, along with metadata (`built_at` and `size_bytes`).
- **Celery Task**: `build_analytics_snapshot` natively queries models and aggregate tables via a dedicated Sqlalchemy session and idempotently upserts.
- **Beat Schedule**: Snapshots are scheduled periodically to refresh them globally for active stores (e.g. daily at 06:00 via Celery Beat).

---

## Loyalty & Credit Module

Blueprint registered under `/api/v1` (routes prefix themselves with `/loyalty` or `/credit`).

### Loyalty Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/loyalty/program` | ✅ | Get store's loyalty program config |
| `PUT` | `/api/v1/loyalty/program` | ✅ (owner) | Upsert loyalty program config |
| `GET` | `/api/v1/loyalty/customers/<id>` | ✅ | Account details: points balance, lifetime earned, recent transactions |
| `POST` | `/api/v1/loyalty/customers/<id>/redeem` | ✅ | Redeem points: `{points_to_redeem, transaction_id?}`. Validates balance and min_redemption_points |
| `GET` | `/api/v1/loyalty/analytics` | ✅ | Summary: enrolled customers, points issued/redeemed this month, redemption rate |

### Credit Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/credit/customers/<id>` | ✅ | Credit ledger + transaction history |
| `POST` | `/api/v1/credit/customers/<id>/repay` | ✅ | Repayment: `{amount, notes?}`. Reduces credit balance |

### Key Features
- **Atomic Loyalty Accrual**: When recording a transaction with a `customer_id`, if the store has an active `loyalty_program`, points are calculated as `grand_total × points_per_rupee`. The loyalty account is upserted and a `loyalty_transactions` EARN row is created within the same DB transaction — if loyalty update fails, the entire sale rolls back.
- **Credit Sale Enforcement**: Transactions with `payment_mode = 'CREDIT'` upsert the `credit_ledger` and create `CREDIT_SALE` entries. If the new balance would exceed `credit_limit`, the sale is blocked with HTTP 422.
- **Point Expiry**: Monthly Celery task (`expire_loyalty_points`) expires points from accounts inactive beyond the program's `expiry_days` setting.
- **Overdue Alerts**: Daily Celery task (`credit_overdue_alerts`) creates HIGH-priority alerts for customers with credit balance > 0 and no activity in 30 days.

---

## GST Compliance Module

Blueprint registered under `/api/v1` (routes prefix themselves with `/gst`).

### GST Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/gst/config` | ✅ | Get store's GST config (GSTIN, registration_type, state_code, is_gst_enabled) |
| `PUT` | `/api/v1/gst/config` | ✅ (owner) | Upsert GST config with GSTIN validation |
| `GET` | `/api/v1/gst/hsn-search?q=` | ✅ | Search HSN master by code prefix or description (ILIKE). Top 10 matches |
| `GET` | `/api/v1/gst/summary?period=YYYY-MM` | ✅ | Compiled period data or triggers compilation. Returns taxable/CGST/SGST/IGST totals |
| `GET` | `/api/v1/gst/gstr1?period=YYYY-MM` | ✅ | Full GSTR-1 JSON structure for filing. 404 if not compiled |
| `GET` | `/api/v1/gst/liability-slabs?period=YYYY-MM` | ✅ | Breakdown by GST rate slab: `{rate, taxable_value, tax_amount}` |

### Data Model (migration `908d85de1d01`)
- `hsn_master`: HSN code registry — `hsn_code` (UNIQUE), `description`, `default_gst_rate`. Seeded with 50 common retail codes.
- `store_gst_config`: Per-store config — `gstin`, `registration_type` (REGULAR/COMPOSITION/UNREGISTERED), `state_code`, `is_gst_enabled`.
- `gst_transactions`: Per-transaction GST breakdown — `taxable_amount`, `cgst_amount`, `sgst_amount`, `igst_amount`, `total_gst`, `hsn_breakdown` (JSONB). UNIQUE on `transaction_id`.
- `gst_filing_periods`: Monthly aggregation — `total_taxable`, `total_cgst`, `total_sgst`, `total_igst`, `invoice_count`, `gstr1_json_path`, `status` (DRAFT/COMPILED). UNIQUE on `(store_id, period)`.
- `products` extended with `hsn_code` (FK→hsn_master) and `gst_category` (EXEMPT/ZERO/REGULAR).

### Key Features
- **GSTIN Validator** (`app/gst/utils.py`): Validates 15-char structure (state code 01-37 + PAN format + entity + 'Z' + modulo-36 checksum).
- **Atomic GST Recording**: When recording a transaction on a GST-enabled REGULAR store, CGST/SGST are computed per line item from HSN rates (intrastate split: rate/2 each). A `gst_transactions` row is created within the same DB transaction.
- **Monthly GSTR-1 Compilation**: Celery task `compile_monthly_gst` aggregates `gst_transactions` into `gst_filing_periods` and writes GSTR-1 JSON to filesystem.
- **GST Backfill Task**: Celery task `update_gst_transactions_task` sweeps for transactions missing GST rows and creates them retrospectively.

---

## WhatsApp Business Integration

Blueprint registered under `/api/v1/whatsapp`.

### WhatsApp Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/whatsapp/config` | ✅ (owner) | Retrieves store WhatsApp configuration (excluding secret token). |
| `PUT` | `/api/v1/whatsapp/config` | ✅ (owner) | Upserts store configuration. `access_token` is Fernet-encrypted at rest. |
| `GET` | `/api/v1/whatsapp/webhook` | ❌ | Meta webhook challenge verification (hub.verify_token). |
| `POST` | `/api/v1/whatsapp/webhook` | ❌ | Meta webhook receiver for incoming status updates (queued, sent, delivered, read) to update `whatsapp_message_log`. |
| `POST` | `/api/v1/whatsapp/send-alert` | ✅ (owner) | Sends critical store `Alert` message to the store owner's registered phone number. |
| `POST` | `/api/v1/whatsapp/send-po` | ✅ (owner) | Sends dynamically formatted text summary of a `PurchaseOrder` to the supplier. |
| `GET` | `/api/v1/whatsapp/message-log` | ✅ (owner) | Paginated audit log of all outbound messages and their delivery statuses. |

### Data Model (migration `b966c53b0061`)
- `whatsapp_config`: Store settings holding `phone_number_id`, `webhook_verify_token`, and the Fernet-secured `access_token_encrypted`.
- `whatsapp_templates`: Approved Meta message templates.
- `whatsapp_message_log`: Outbound message audit trail containing `recipient_phone`, `direction`, `content_preview`, `status`, and exact `delivered_at` timestamps sourced via webhooks.

### Key Features
- **Dry-Run Mode**: Setting `WHATSAPP_DRY_RUN=true` globally prevents literal HTTP dispatches to Meta, returning a mocked success ID while still fully executing the formatting and DB logging logic (used extensively within tests).
- **Secure Handling**: Keys like `access_token` are encrypted instantly before storage using symmetric AES (Fernet) bound to the `SECRET_KEY`.
- **UI Integration Hooks**: When the engine evaluates alerts, if `whatsapp_config.is_active` is true and valid, contextual option `Send via WhatsApp` becomes available to the frontend.

---

## Chain Ownership & Multi-store Module

Blueprint registered under `/api/v1/chain`. Requires `chain_role: CHAIN_OWNER` in JWT claims.

### Chain Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/chain/groups` | ✅ (owner) | Create a new store group, making the user a CHAIN_OWNER. |
| `POST` | `/api/v1/chain/groups/<id>/stores` | ✅ (chain_owner) | Add a store to the group. |
| `GET` | `/api/v1/chain/dashboard` | ✅ (chain_owner) | Chain-wide KPI dashboard: total revenue, best/worst store, open alerts, per-store breakdown, pending transfer suggestions. |
| `GET` | `/api/v1/chain/compare?period=today\|week\|month` | ✅ (chain_owner) | Store × KPI comparison matrix with `relative_to_avg: above\|near\|below` coding. |
| `GET` | `/api/v1/chain/transfers` | ✅ (chain_owner) | List inter-store transfer suggestions. |
| `POST` | `/api/v1/chain/transfers/<id>/confirm` | ✅ (chain_owner) | Mark a transfer suggestion as actioned. |

### JWT Extension
- When `generate_access_token()` runs, if the user is `owner_user_id` of a `StoreGroup`, the claims `chain_group_id` (UUID string) and `chain_role: "CHAIN_OWNER"` are injected.
- **Backward-compatible**: all existing `store_id`-scoped decorators and queries remain unchanged.

### Data Model (migration `64289450c79b`)
- `store_groups`: Chain identity — `name`, `owner_user_id`.
- `store_group_memberships`: Many-to-many link — `group_id`, `store_id`, optional `manager_user_id`. UNIQUE on `(group_id, store_id)`.
- `chain_daily_aggregates`: Per-store daily roll-ups — `revenue`, `profit`, `transaction_count`. UNIQUE on `(group_id, store_id, date)`.
- `inter_store_transfer_suggestions`: Automated transfer recommendations — `from_store_id`, `to_store_id`, `product_id`, `suggested_qty`, `reason`, `status` (PENDING/ACTIONED).

### Celery Tasks
- **`aggregate_chain_daily_all_groups`** (daily 01:00): Orchestrates per-group aggregation from `DailyStoreSummary` into `ChainDailyAggregate`.
- **`detect_transfer_opportunities_all_groups`** (weekly Monday 05:00): Finds CRITICAL LOW_STOCK alerts in one store matched with surplus in a sibling store; creates `InterStoreTransferSuggestion`.

---

## Configuration and Environment Variables
Create `.env` for local overrides; in Docker, defaults from `.env.example` are loaded.

Common variables:
- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `JWT_PRIVATE_KEY`
- `JWT_PUBLIC_KEY`
- `SECRET_KEY`

### Notes
- In non-test environments, provide stable JWT keys (do not rely on ephemeral generated keys).
- For production, use a secret manager and avoid committing real secrets.

---

## Running the System

## Option A: Docker (recommended)

```bash
docker-compose up --build
```

Services:
- API on `http://localhost:5000`
- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`

## Option B: Local Python runtime

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=wsgi.py
flask run
```

For local DB migrations:
```bash
alembic upgrade head
```

---

## Testing Strategy

## Test discovery
`pytest.ini` scopes discovery to:
- `tests/`
- files matching `test_*.py`

## Running tests
```bash
pytest -q
```

### Test Environment Behavior
- Uses in-memory SQLite with shared `StaticPool` for fast isolated tests.
- Compilers map PG-specific `JSONB`/`UUID` for SQLite compatibility.
- Test fixture injects ephemeral JWT keys.

### Recommended test commands
```bash
pytest -q
pytest -q tests/test_transactions.py tests/test_audit.py tests/test_auth_flow.py
```

---

## CI/CD

GitHub Actions workflow `.github/workflows/test-on-commit.yml`:
- triggers on push + pull request,
- installs dependencies,
- runs `pytest -v`.

Recommended branch protection:
- require passing CI before merge,
- disallow direct pushes to default branch.

---

## Operations and Troubleshooting

## Health endpoint
- `GET /api/v1/health` returns app-level status payload.

## Common startup issues
1. **DB unavailable**
   - check Postgres container health.
   - inspect logs for `wait_for_db.py` timeout.
2. **Migration failure**
   - run `alembic upgrade head` manually.
   - verify `DATABASE_URL` points to expected DB.
3. **Redis broker errors**
   - confirm `REDIS_URL` / `CELERY_BROKER_URL`.
   - verify Redis service up.

## Useful commands
```bash
docker-compose logs -f app
docker-compose logs -f worker
docker-compose logs -f beat
```

---

## How to Modify the System Safely

## 1) Adding a new endpoint
- Create/extend module blueprint route.
- Add schema validation and auth decorators.
- Add/extend service logic.
- Add tests under `tests/`.

## 2) Adding new background task
- Implement in `app/tasks/tasks.py`.
- Use `task_session` and idempotent lock when appropriate.
- Add unit/integration tests.
- If scheduled, register in `celery_worker.py` beat schedule.

## 3) Changing DB schema
- Update model.
- Create Alembic migration.
- Validate migration from empty DB + upgrade path from existing DB.
- Add/adjust tests.

## 4) Changing auth behavior
- Keep token and Redis key strategy consistent across login/refresh/logout/verify-otp.
- The `verify-otp` endpoint returns the same `AuthTokens` shape as `login` — any changes to the login response must be mirrored.
- Refresh token rotation happens on every `/auth/refresh` call (old token is deleted from Redis, new one is issued).
- Add lifecycle tests (rotation/replay/revocation).

---

## Production Readiness Checklist

Before deployment, ensure all are true:
- [ ] `pytest -q` passes fully.
- [ ] migrations apply cleanly on fresh DB and existing env.
- [ ] secrets managed externally (no plaintext secrets in repo).
- [ ] stable JWT key management strategy in place.
- [ ] log aggregation and monitoring configured.
- [ ] backup/restore validated for PostgreSQL.
- [ ] rate limits and auth policies reviewed.
- [ ] worker + beat autoscaling and queue policies defined.
- [ ] rollback strategy documented.

---

## Contributing

1. Create a branch.
2. Implement code + tests.
3. Run `pytest -q`.
4. Open PR with:
   - summary,
   - migration impact,
   - test evidence,
   - rollout notes.

---

## License

This project is open source under the MIT License (see `LICENSE` if present).
