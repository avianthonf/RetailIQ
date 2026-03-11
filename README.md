# RetailIQ — Retail Data Platform

RetailIQ is a **planet-scale retail operations intelligence platform**. It is built as a **multi-region, distributed application** deployed on **Kubernetes** with a global **CockroachDB** cluster and multi-region **Redis** caching. 
 
 It is designed for **99.99% availability**, **p99 <50ms latency**, and **11 nines of data durability**.
- transactional APIs (auth, store, inventory, transactions, customers),
- analytics APIs backed by aggregate tables,
- forecasting (store + SKU),
- decision recommendations from deterministic rules,
- NLP-style deterministic query responses,
- **supplier management & purchase orders** (supplier tracking, PO lifecycle, stock receiving),
- barcode registry and receipt printing (barcode lookup, template management, async print jobs),
- **loyalty & credit** (points-based loyalty programs, credit ledger, atomic POS integration),
- **GST compliance** (HSN master, GSTIN validation, per-transaction GST recording, GSTR-1 generation),
- **pricing engine** (competitive price drift detection, margin-optimized suggestions, weekly analysis, **real-time market signal integration**, **Bayesian price elasticity modeling**),
- **market intelligence** (real-time signal ingestion, price index computation, anomaly detection, sentiment analysis, WebSocket streaming),
- **event-aware forecasting** (business event calendar, Prophet external regressors, demand sensing log, **Ensemble XGBoost/LSTM/Prophet engine**),
- **vision / OCR invoice processing** (Tesseract OCR, product fuzzy-matching, human review flow, **YOLOv8 Shelf Analytics**, **TrOCR Receipt Digitization**, **Loss Prevention Detection**),
- **Narrow Retail AI/ML Models** (LLaMA 7B RAG Assistant, Two-tower Recommendation Engine, Bayesian Dynamic Pricing, Deep Demand Forecasting),
- **security hardening**: rate limiting (429 return codes), FK index audit, input sanitization, automated security scans (`bandit`, `pip-audit`), schema-migration sync.
- **asynchronous background processing**: Celery-based workflow with multi-regional support.

---

## 🏗️ Technical Highlights
- **Rate Limit Integrity**: Guaranteed correct `429 Too Many Requests` status codes via centralized `HTTPException` handling.
- **Docker Optimization**: Optimized production build using CPU-only PyTorch indices, reducing image overhead and ensuring CI build stability.
- **Schema Resilience**: Continuous Alembic migration checks integrated into CI to prevent schema drift.

---

## 🚀 Quick Start (Production)

The API is live on AWS ECS Fargate and accessible via the Application Load Balancer:

```bash
# Health Check Endpoint
curl http://retailiq-alb-1647913544.us-east-1.elb.amazonaws.com/api/v1/health
```

**Auto-Deployment**: Merging or pushing to the `main` branch automatically triggers the `.github/workflows/deploy.yml` pipeline. The CI/CD has been optimized to run under 3 minutes using:
- **uv package manager** for 10x faster dependency installation
- **Parallel test execution** with pytest-xdist
- **Combined quality checks** (lint, security, migrations) in a single job
- **SQLite in-memory testing** (no external services needed)
- **Smart Python version matrix** (single version for PRs, full matrix on main)

The pipeline runs 250+ tests, builds the multi-stage Docker image, pushes to Amazon ECR, and performs a zero-downtime rolling update across the three ECS services (API, Worker, Beat).

For detailed AWS architecture, security, cost optimization, and CI/CD secrets setup, read the full [**AWS Deployment Guide (DEPLOYMENT.md)**](./DEPLOYMENT.md).

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Comprehensive System Architecture](#comprehensive-system-architecture)
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
16. [Pricing Engine Module](#pricing-engine-module)
17. [Event-Aware Forecasting Module](#event-aware-forecasting-module)
18. [Vision / OCR Invoice Processing Module](#vision--ocr-invoice-processing-module)
19. [Security & Performance Hardening](#security--performance-hardening)
20. [Configuration and Environment Variables](#configuration-and-environment-variables)
21. [Local Development](#local-development)
22. [Testing Strategy](#testing-strategy)
23. [CI/CD](#cicd)
24. [Operations and Troubleshooting](#operations-and-troubleshooting)
25. [Comprehensive Developer and Engineer Guide](#comprehensive-developer-and-engineer-guide)
26. [API Specification (OpenAPI)](#api-specification-openapi)
27. [Production Readiness Checklist](#production-readiness-checklist)

---

## System Overview

RetailIQ is built as a Flask app using SQLAlchemy models and blueprint modules. It exposes versioned APIs under `/api/v1/...`, persists operational data in PostgreSQL, and offloads compute-heavy/periodic workflows to Celery workers.

### Core Capabilities
- **Auth + access control**: JWT-based auth with role gating (`owner`, `staff`). Email-based OTP verification via Gmail SMTP.
- **Operational APIs**: inventory, transactions, customers, store configuration.
- **Analytics**: revenue/profit/category/payment/contribution views, mostly from aggregate tables.
- **Suppliers & POs**: Track active suppliers, linked products, purchase orders, and goods receipts.

### 📖 API Documentation

The complete API reference is available in OpenAPI 3.0 format:
- **Specification**: [`openapi.json`](file:///D:/Files/Desktop/RetailIQ-Final-Workspace/RetailIQ/openapi.json)

This specification includes all v1 and v2 endpoints, request/response models, and authentication requirements.
- **Forecasting**: forecast cache for store-level and SKU-level projections.
- **Decision engine**: deterministic recommendations using rules over computed context.
- **NLP endpoint**: deterministic intent router + template-based responses (not generative).
- **Staff Performance**: Session management, daily target setting, and automated role-based metric aggregations. Exposed via unified POST/PUT `/targets` mapping.
- **Loyalty & Credit**: Points-based loyalty programs, credit ledger, atomic loyalty accrual at transaction time, point redemption, credit sale enforcement, automated point expiry. Exposed via native endpoint aliases mapped perfectly for DataSage.
- **GST Compliance**: HSN code management, GSTIN validation (modulo-36 checksum), per-transaction CGST/SGST recording, GSTR-1 JSON generation, and liability slab analytics.
- **WhatsApp Integration**: Outbound messaging (Alerts & Purchase Orders) via Meta Cloud API, secure Fernet token encryption at rest, and Meta webhook verification/handling.
- **Chain Ownership**: Multi-store grouping, chain-wide KPI dashboards, store comparison matrix with relative coding, and automated inter-store transfer suggestions.
- **Pricing Engine**: Competitive price drift detection via price elasticity proxy, margin-optimized RAISE/LOWER suggestions, configurable pricing rules, and weekly automated analysis. Now enhanced with **Market Intelligence signals** for inflation-aware adjustments.
- **Market Intelligence**: Real-time ingestion of supplier pricing, commodity indices, and consumer sentiment. Provides Fisher/Laspeyres price indices, anomaly detection (Isolation Forest), and sub-second signal streaming via WebSockets.
- **Developer Platform**: Public API Ecosystem with OAuth 2.0 (RS256), API Key management.
- **Usage Metering**: Precise tracking of API consumption for billing and quotas.
- **Webhook Infrastructure**: Reliable, signed event delivery for third-party integrations.

## 💳 Embedded Finance Platform (Team 2)

RetailIQ is now a financial infrastructure layer for merchants, providing banking-as-a-service (BaaS) capabilities embedded directly into the retail workflow.

### Architecture & Core Components

- **Immutable Ledger**: A double-entry accounting engine (`app/finance/ledger.py`) that ensures all financial movements are balanced and auditable.
- **Credit Scoring Engine**: Proprietary scoring (`app/finance/credit_scoring.py`) using RetailIQ transaction data, revenue velocity, and inventory turnover signals.
- **Lending Infrastructure**: Full lifecycle management for term loans, lines of credit, and revenue advances.
- **Payment Processing**: Integrated merchant settlements with automated fee deduction and ledger synchronization.
- **Treasury Management**: Automated sweeps and yield accrual on merchant reserve accounts.
- **Parametric Insurance**: Automated claims and payouts based on external triggers (e.g., weather-based business interruption).

### Financial Data Model

| Model | Purpose |
|-------|---------|
| `FinancialAccount` | Per-merchant accounts (Operating, Reserve, Revenue, Escrow). |
| `LedgerEntry` | Atomic, balanced DEBIT/CREDIT pairs for all movements. |
| `LoanApplication` | Tracks credit requests from application to payoff. |
| `InsurancePolicy` | Parametric insurance enrollment and automated coverage. |
| `MerchantCreditProfile` | Stores computed credit scores and risk factors. |

### API Quick Start (`/api/v2/finance/`)

- `GET /dashboard`: Aggregated financial health (cash-on-hand, total debt, credit score).
- `POST /loans/apply`: Submit a request for credit using a `product_id`.
- `PUT /treasury/sweep-config`: Configure automated treasury yield strategies.
- `GET /ledger`: Access a complete auditable history of all account movements.

---

## 🏢 B2B Wholesale Marketplace (Team 3)

RetailIQ's B2B Wholesale Marketplace is a data-driven procurement platform connecting retailers directly with wholesalers and brands. Unlike standard catalogs, it uses ML/AI to recommend purchasing strategies and embeds finance options seamlessly via Team 2 integration.

### Architecture & Core Components

- **Supplier Directory (`app/marketplace/`)**: Registry of verified wholesalers, brands, and their master catalogs.
- **Digital RFQ Engine**: End-to-end Request for Quote flow allowing retailers to negotiate terms and bulk discounts anonymously.
- **AI Procurement Recommendations**: Deep continuous analysis of store inventory run-rates and localized demand to automatically suggest reorders.
- **Unified Supplier Dashboard**: An analytics-heavy portal for suppliers to view pipeline momentum and analyze historical wholesale fulfillment metrics.
- **Marketplace Core Models**: `SupplierProfile`, `CatalogItem`, `MarketplacePurchaseOrder`, `RFQ`, and `SupplierReview`.

### API Quick Start (`/api/v1/marketplace/`)

- `GET /directory`: Browse the global supplier directory and product catalogs.
- `POST /rfqs`: Submit a new Request for Quote to a supplier for a specific SKU.
- `POST /purchase-orders`: Submit a binding marketplace PO to a finalized supplier.
- `GET /supplier/dashboard`: Fetch pipeline metrics, RFQ conversion rates, and total generated revenue (Supplier role only).

---

## 🚀 Deployment & Scaling

## Comprehensive System Architecture

### Planet-Scale Distributed Topology
RetailIQ is evolving from a single-region ECS setup to a global, distributed architecture across 5+ regions (US-East, EU-West, AP-South, etc.).

#### High-level Components
- **Global Load Balancer (CDN)**: Anycast global routing with edge caching (latency-based).
- **Kubernetes Multi-Region (EKS/GKE)**:
    - `api`: Flask Gunicorn app (Distroless runtime).
    - `worker`: Distributed Celery workforce.
    - `beat`: Highly available Celery scheduler.
- **CockroachDB Cluster**: Multi-region distributed SQL with row-level geo-partitioning.
- **Redis Cluster**: Global caching with local-read optimization.
- **Kafka**: Real-time event streaming and message brokering.

### Observability Stack
- **Prometheus + Grafana**: SLA monitoring (Availability, p99 Latency, Cost/1M requests).
- **Jaeger**: Distributed tracing across regions.
- **Loki**: Global log aggregation.

### Runtime Hierarchy
1. **Request Ingress**: Client -> Global LB -> Regional K8s Ingress -> API Pod.
2. **State Management**: API Pod -> Regional Redis (Cache) / Global CockroachDB (Record).
3. **Async Processing**: API Pod -> Kafka/Redis Broker -> Celery Worker.

### Detailed Component Architecture
```mermaid
graph TD
    subgraph "External Integration"
        WA[WhatsApp Meta API]
        GST[GSTN Portal]
        INT[Market Intelligence Signals]
    end

    subgraph "API Layer (Flask/Gunicorn)"
        AUTH[Auth/OAuth 2.0]
        INV[Inventory/Store]
        SALE[Transactions/Sales]
        AI[AI v2/Vision/NLP]
        DEV[Developer Portal]
    end

    subgraph "Logic & Processing"
        RULE[Decision Engine]
        FORE[Forecasting Prophet/XGBoost]
        TASK[Celery Workers]
        ERR[Centralized Error Handling]
    end

    subgraph "Storage Layer"
        CDB[(CockroachDB Global)]
        RED[(Redis Multi-Region Cache)]
    end

    subgraph "CI/CD & Hardening"
        RUFF[Ruff Linter]
        ALEM[Alembic Migration Sync]
        SCAN[Security Scan - Bandit/pip-audit]
    end

    INT --> |Real-time| AUTH
    AUTH --> CDB
    INV --> CDB
    SALE --> CDB
    SALE --> |Events| TASK
    TASK --> |Aggregate| CDB
    TASK --> FORE
    FORE --> |Cache| RED
    DEV --> |Usage| CDB
    ERR -.-> |Standardized JSON| API_LAYER
    CI_CD --> |Blocking Checks| DEV_WORKFLOW
```

### AI/ML Inference Architecture
RetailIQ integrates specialized ML models for predictive insights:
- **Demand Forecasting**: Uses an ensemble of **Facebook Prophet** and **XGBoost** to predict SKU-level demand. Models are trained asynchronously via Celery and cached in Redis.
- **Vision Engine**: Employs **YOLOv8** for shelf analytics and **Tesseract OCR** for receipt digitization.
- **Dynamic Pricing**: Uses **Bayesian elasticity modeling** to suggest price adjustments based on sales velocity and margin targets.

### Financial Integrity: The Immutable Ledger
The B2B Marketplace and Embedded Finance modules rely on a **double-entry immutable ledger**. Every credit movement or loan disbursement creates a balanced DEBIT/CREDIT pair, ensuring mathematical consistency and full auditability across all merchant accounts.

---

## Planet-Scale Infrastructure Transition (Phase 1)
We are currently in **Phase 1: Foundation**. Highlights:
- **Distroless Runtime**: Hardened production images using `gcr.io/distroless/python3`.
- **Predictive AI:** ARIMA, Prophet, and specialized custom ML models for inventory and price forecasting
- **Offline Reliability:** PWA sync layer, CockroachDB shadow replication
- **Mobile Edge:** Kotlin Multiplatform (KMP), native SwiftUI iOS, Service Worker PWA, CRDT local database (SQLDelight)
- **CockroachDB Shadow Replication**: Real-time CDC from legacy PostgreSQL 15.
- **Full Observability**: Live metrics, traces, and logs in `/observability`.

## 🏗️ Architecture

RetailIQ uses a powerful modular architecture spanning backend microservices, planet-scale databases, and now a cross-platform mobile edge.

### Core Backend Components
- `app/models/` – SQLAlchemy schemas spanning users, products, transactions, analytics, and more.
- `app/api_v2/` – The next-generation REST APIs with high-throughput optimizations.
- `app/forecasting/` & `app/ai_v2/` – Predicts inventory depletion and recommends pricing using ML.
- `app/sync/` - Conflict-free Replicated Data Type (CRDT) engine for edge offline-sync capabilities.

### Mobile Edge Architecture (Team 7)
The RetailIQ mobile stack relies on **Kotlin Multiplatform (KMP)**.
- **Shared (`mobile/shared/`)**: Domain models, Ktor APIs, SQLDelight DB schema, CRDT Sync Engine, Koin DI, Auth.
- **Android (`mobile/androidApp/`)**: Jetpack Compose reactive UI.
- **iOS (`mobile/iosApp/`)**: SwiftUI with AVFoundation barcode scanning + Apple Push Notifications.
- **Web (`mobile/pwa/`)**: React + TypeScript PWA featuring Service Workers, caching strategies, and indexedDB offline persistence.

## 🚀 Getting Started

### 1. Backend API (Python)

---

## Repository Map

```text
app/
  __init__.py                # Flask app factory, extension init, blueprint registration
  email.py                   # Gmail SMTP email service (OTP + password reset emails)
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
  pricing/                   # pricing engine, suggestion API, rules, price history
  market_intelligence/       # real-time signals, indices, anomaly detection, connectors, WS
  events/                    # business event calendar, demand sensing endpoint
  vision/                    # OCR invoice processing, parser, upload/confirm API
  developer/                 # Developer registration, application management, API Gateway
  api_v2/                    # Public Developer API (OAuth protected)
  auth/oauth.py              # OAuth 2.0 Provider logic
  utils/webhooks.py          # Webhook queuing and broadcasting utility
  utils/
    sanitize.py              # Input sanitization (strip + truncate) utility

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

1. Request 3. Blueprint route validates payload via Marshmallow schemas and extracts context (`g.current_user`).
4. **Service Layer Execution**: Routes delegate complex logic to `app/<module>/services.py` for better testability and reuse.
5. **Unified Response Layer**: Every response is wrapped via `standard_json` to ensure a consistent API envelope.
6. Data is committed/rolled back using SQLAlchemy sessions.
7. Non-critical background follow-ups (aggregates/alerts/etc.) are queued asynchronously via Celery.

### Auth + Role Model
- Authenticated identity includes `user_id`, `store_id`, `role`.
- Role checks use decorators for owner-only operations.
- Refresh token lifecycle uses Redis token-keyed records with 30-day TTL.
- Access tokens (JWT/RS256) expire after 2 hours; clients must use `/auth/refresh` to renew.
- **Auto-login on signup**: `POST /auth/verify-otp` activates the account AND returns full auth tokens (`access_token`, `refresh_token`, `user_id`, `role`, `store_id`) — same shape as the login response. This allows mobile clients to skip the manual login step after registration.

### Email-Based OTP Verification
- **Registration requires `email`** — the `RegisterSchema` enforces `email` as a required field.
- **OTP delivery**: On registration, a 6-digit OTP is stored in Redis (300s TTL) and emailed to the user via Gmail SMTP. The email contains a branded HTML template with the verification code.
- **Password reset**: The `forgot-password` endpoint generates a UUID token (600s TTL), stores it in Redis, and emails a branded reset email to the user's registered email address.
- **Dev fallback**: When `MAIL_USERNAME`/`MAIL_PASSWORD` are not configured (local dev), emails are logged to the console instead of being sent via SMTP.
- **Email service** (`app/email.py`): Uses Python's built-in `smtplib` with TLS for Gmail SMTP (`smtp.gmail.com:587`). No additional dependencies required.

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
- `purchase_orders` & `purchase_order_items`: PO tracking structure, exposed via expanded `PUT/POST /send` and explicit `GET /{id}` query structures.
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

### Pricing entities (migration `c3d91f2a7b44`)
- `product_price_history`: Enhanced with `store_id`, `old_price`, `new_price`, `reason`, `changed_by` — tracks every price change with full audit trail.
- `pricing_suggestions`: Engine-generated suggestions — `suggested_price`, `current_price`, `price_change_pct`, `reason`, `confidence`, `status` CHECK(`PENDING`/`APPLIED`/`DISMISSED`), `actioned_at`.
- `pricing_rules`: Per-store configurable rules — `rule_type`, `parameters` (JSONB), `is_active`.

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
- `run_weekly_pricing_analysis` (Sunday 03:00: runs pricing engine for all stores, upserts PENDING suggestions, skips duplicates within 7 days)

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

## Pricing Engine Module

Blueprint registered under `/api/v1/pricing`.

### Pricing Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/pricing/suggestions` | ✅ | List PENDING suggestions for the store with margin impact analysis |
| `POST` | `/api/v1/pricing/suggestions/<id>/apply` | ✅ | Apply suggestion: updates `products.selling_price`, records `product_price_history`, marks APPLIED. Returns 409 if already actioned |
| `POST` | `/api/v1/pricing/suggestions/<id>/dismiss` | ✅ | Dismiss suggestion. Returns 409 if already actioned |
| `GET` | `/api/v1/pricing/history?product_id=<id>` | ✅ | Price change history for a product (last 100 entries) |
| `GET` | `/api/v1/pricing/rules` | ✅ | List store pricing rules |
| `PUT` | `/api/v1/pricing/rules` | ✅ | Upsert a pricing rule by `rule_type` |

### Engine Algorithm (`app/pricing/engine.py`)

The `generate_price_suggestions(store_id, session)` function:
1. **Qualifies products** with ≥30 days of `daily_sku_summary` history in the 90-day window.
2. **Computes price elasticity proxy**: Pearson correlation between binary "price above median" flags and `units_sold`. Undetermined correlation (constant demand) defaults to 0.0 (perfectly inelastic).
3. **Calculates margin**: `(selling_price - cost_price) / selling_price`.
4. **RAISE trigger**: `margin < 15%` AND `elasticity_proxy > -0.3` → suggests +5% price increase.
5. **LOWER trigger**: zero sales in 14 days AND `margin > 30%` AND no store-wide anomaly → suggests -10% price decrease.
6. **Anomaly guard**: If the entire store had zero revenue in the lookback window, zero-velocity is attributed to a store-wide issue rather than a product problem.

### Celery Task
- **`run_weekly_pricing_analysis`** (Sunday 03:00): Iterates all stores, calls the pricing engine, and upserts PENDING suggestions. Skips if a PENDING suggestion for the same product already exists within 7 days (idempotency).


---

## 21. Public Developer Platform & API Ecosystem

RetailIQ is an **open platform** allowing third-party developers to build integrated solutions.

### Core Components
- **OAuth 2.0 Provider**: Secure authorization code and client credentials flows using RS256 JWT signing.
- **API Gateway**: Centralized entry point (`/api/v2`) with Redis-backed rate limiting, usage metering, and scope validation.
- **Webhook System**: Asynchronous event delivery (Celery) with HMAC-SHA256 signing, delivery logging, and exponential backoff retries.
- **Developer Portal**: Self-service application management and API key generation.
- **App Marketplace**: A directory of third-party applications integrated with RetailIQ.

### Example: Consuming the Public API
1. **Register** as a developer via `/api/v1/developer/register`.
2. **Create an App** to get `client_id` and `client_secret`.
3. **Obtain Token**: `POST /oauth/token` with `grant_type=client_credentials`.
4. **Call API v2**: `GET /api/v2/inventory?store_id=1` with `Authorization: Bearer <token>`.

---

## 22. Configuration and Environment Variables
Create `.env` for local overrides; in Docker, defaults from `.env.example` are loaded.

Common variables:
- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `JWT_PRIVATE_KEY`
- `JWT_PUBLIC_KEY`
- `SECRET_KEY`
- `MAIL_USERNAME` — Gmail address used as the OTP/reset email sender
- `MAIL_PASSWORD` — Gmail App Password (16-char, generated from [Google Account → App Passwords](https://myaccount.google.com/apppasswords))

### Notes
- In non-test environments, provide stable JWT keys (do not rely on ephemeral generated keys).
- For production, use a secret manager and avoid committing real secrets.
- `MAIL_USERNAME` and `MAIL_PASSWORD` are optional in development (emails fall back to console output). In production, they are stored in AWS Secrets Manager (`retailiq/prod/mail-username`, `retailiq/prod/mail-password`).

---

## Local Development

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
pytest tests/test_email_service.py -v  # email/OTP integration tests
pytest tests/test_security.py -v       # security hardening tests
pytest tests/test_e2e.py -v            # end-to-end integration tests
```

### Security Tests (`tests/test_security.py`)
- **`test_login_rate_limit`**: Verifies 429 on 11th login attempt within a minute (uses separate app fixture with rate limiting enabled).
- **`test_store_scoping_on_all_new_endpoints`**: Creates two stores and verifies that a JWT from store B cannot access store A's data across all post-launch blueprints.
- **`test_sensitive_fields_not_in_logs`**: PUTs a WhatsApp config with an `access_token` and verifies the raw token is redacted from captured log output.

### E2E Integration Tests (`tests/test_e2e.py`)
Multi-step user journey tests that span multiple endpoints and simulate Celery tasks inline:
- **`test_full_retail_day`**: Create 3 products → record 5 sales (CASH/UPI) → rebuild aggregates → verify dashboard revenue → evaluate alerts → verify LOW_STOCK on depleted product.
- **`test_supplier_po_stock_cycle`**: Create supplier → link product → create/send PO → receive goods → verify stock increased, PO FULFILLED, GRN created.
- **`test_loyalty_full_cycle`**: Setup 1pt/₹ loyalty → create customer → ₹200 sale → assert 200 pts earned → redeem 100 → assert balance 100 → over-redeem 200 → 422.
- **`test_gst_month_compilation`**: Enable GST → seed HSN codes (5%/18%) → 10 transactions → compile GST filing → verify summary totals and liability slabs sum correctly.
- **`test_offline_snapshot_freshness`**: Seed 30 days of aggregates → build snapshot → verify `built_at` <60s old and `revenue_30d` populated.
- **`test_chain_cross_store_isolation`**: Create stores A and B → supplier in A → A's JWT sees it → B's JWT does NOT.

---

## CI/CD

| 📦 **Migration Check** | Alembic migration detection | ✅ Yes |

---

## 25. Comprehensive Developer and Engineer Guide

### Coding Standards
- **Linter**: We use `ruff` for extremely fast linting and formatting. Always run `ruff --fix .` before committing.
- **Type Hints**: All new code MUST include Python type hints for clarity and static analysis.
- **Error Handling**: Use the `HTTPException` handler in `app/__init__.py`. Return `429` for rate limits, `422` for validation errors, and `500` only for truly unhandled exceptions.
- **Migration Workflow**: All schema changes MUST be accompanied by a manual or auto-generated Alembic migration. Run `alembic check` locally to ensure no missing fields are detected.
- **Docker Build**: Optimized for CI speed using `--extra-index-url https://download.pytorch.org/whl/cpu`.

### Data Modeling & Migrations
- **Models**: Core models live in `app/models/__init__.py`. External or secondary models should be integrated via `missing_models.py` or separate files but MUST be imported in the main models init to be detected by Alembic.
- **Migrations**: Always verify that `flask db migrate` produces a clean script. If adding tables for new features (e.g., Market Intelligence), ensure they are correctly linked to the `Base` metadata.

### Security Best Practices
- **Dependency Audit**: We run `pip-audit` and `safety` in CI. Never downgrade a pinned security version (e.g., `flask-cors>=6.0.2`).
- **Input Sanitization**: Use `bleach` for HTML sanitization and internal regex-based stripping for sensitive fields.
- **Log Masking**: Sensitive fields like `access_token` or `password` are automatically redacted by the `SensitiveDataFilter` in `app/__init__.py`.

**Security Hardening (Mar 2026 Audit)**:
- All core dependencies are pinned to secure versions (resolving CVEs in `flask-cors`, `scikit-learn`, `marshmallow`, `weasyprint`).
- Hardened multi-stage Docker build ensures a minimal attack surface using Google's Distroless images.
- CI includes mandatory `pip-audit` and `bandit` scans.
- Explicit UTF-8 encoding enforcement across the codebase prevents parsing/logic errors.
| ✅ **CI Pass** | Status gate for branch protection rules | ✅ Required |

### GitOps Deployment (`ArgoCD`)
Deployments are managed via **GitOps** using ArgoCD:
1. **Build & Push**: GitHub Actions builds the Distroless image and pushes to ECR.
2. **Manifest Update**: CI updates the image tag in `k8s/overlays/<region>/kustomization.yaml`.
3. **Sync**: ArgoCD detects the change and synchronizes the K8s clusters globally.
4. **Validation**: Automated smoke tests run post-sync; automatic rollback if health checks fail.

Branch protection recommended:
- require **CI Pass** check before merge,
- disallow direct pushes to `main`.

---

## Operations and Troubleshooting

## Health endpoint
- `GET /api/v1/health` returns app-level status payload.

## Environment Validation

The app loads `.env` via `python-dotenv` at startup (before any `os.environ` reads). In **production** mode (`FLASK_ENV=production`), the app **refuses to start** if:

- `SECRET_KEY` is missing or set to a known weak default
- `DATABASE_URL` is missing or uses default dev credentials (`retailiq:retailiq`)
- `REDIS_URL` or `CELERY_BROKER_URL` is missing
- `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` are missing

In **development** mode, missing values use sensible defaults with a warning.

A startup banner logs the active configuration (with masked DB passwords) on boot:
```
  ┌─────────────────────────────────────────────┐
  │  RetailIQ starting                          │
  │  ENV:      production                       │
  │  DB:       postgresql://retailiq:***@db...   │
  │  JWT keys: from env                         │
  │  .env:     loaded                           │
  └─────────────────────────────────────────────┘
```

## Common startup issues
1. **"STARTUP ABORTED — Missing or invalid configuration"**
   - Copy `.env.example` to `.env` and fill in production values.
   - Run `cp .env.example .env` and edit the file.

## API Specification (OpenAPI)

RetailIQ provides a complete **OpenAPI 3.0** specification for all services.

- **File**: [`openapi.json`](./openapi.json)
- **Groups**:
    - **v1**: Core Retail Operations (Auth, Inventory, Sales).
    - **v2**: Developer & Partner APIs (OAuth 2.0 protected).
    - **AI**: Vision, NLP, and Optimization endpoints.
    - **OAuth**: Token exchange and authorization.

You can import `openapi.json` into tools like **Postman**, **Insomnia**, or **Swagger UI** to explore and test the API.

---

## 🏗️ Comprehensive System Architecture

RetailIQ is designed as a **Planet-Scale Modular Monolith**, strategically built to transition towards a globally distributed, high-performance architecture. OpenAPI generation scripts (`extract_routes.py` and `build_openapi.py`) automate API schemas directly from Flask blueprints.

### Architectural Tiers

1.  **Edge / Routing Layer (Global Load Balancing)**
    *   **CDN & WAF**: Filters malicious traffic, terminates SSL, and routes users to the nearest regional deployment.
    *   **API Gateway**: Handles rate limiting (`flask-limiter`), OAuth 2.0 token validation, and API usage metering.

2.  **Application Layer (Flask/Gunicorn)**
    *   **Stateless Micro-Services**: Built on Flask Blueprints, each representing a bounded context (e.g., `app/pricing`, `app/loyalty`, `app/finance`).
    *   **Synchronous Processing**: Handles immediate transactional workloads like Point-of-Sale checkout, customer lookup, and inventory deduction.

3.  **Asynchronous Processing Layer (Celery & Redis)**
    *   **Message Broker (Redis)**: Queues heavy workloads to prevent blocking the API thread.
    *   **Workers & Beat**: Executes background jobs such as Demand Forecasting (Prophet/XGBoost), OCR Invoice Processing (Tesseract), Weekly Pricing Analysis, and automated Treasury Sweeps.

4.  **Storage & Persistence Layer**
    *   **Global Record (PostgreSQL/CockroachDB)**: Stores all transactional models via SQLAlchemy ORM. Uses `begin_nested()` for atomic sub-transactions in batch operations.
    *   **High-Speed Cache (Redis)**: Caches NLP intent responses, OAuth tokens, API rate limits, and short-term forecast structures.
    *   **Blob Storage (S3)**: Stores uploaded receipts and OCR invoice images.
    *   **Audit Logging**: Every price change and sensitive configuration update is immutable and tracked in history tables.

### Data Flow Diagram

```mermaid
graph TD
    User((Client Apps)) -->|REST / WS| Gateway[API Gateway & Rate Limiter]
    Gateway --> Auth[Auth & OAuth 2.0]
    Gateway --> CoreOps[Core Ops: Inventory, Sales, Finance]
    
    CoreOps --> DB[(CockroachDB / PostgreSQL)]
    CoreOps --> Cache[(Redis Cluster)]
    
    CoreOps -->|Async Events| Broker[Celery Task Queue]
    Broker --> Worker1[ML Forecasting Worker]
    Broker --> Worker2[OCR & Vision Worker]
    Broker --> Worker3[Analytics Aggregator]
    
    Worker1 --> DB
    Worker2 --> DB
    Worker3 --> DB
```

---

## 25. Comprehensive Developer and Engineer Guide

Welcome to the Developer and Engineer Guide for RetailIQ. This guide summarizes best practices when contributing to the codebase.

### UTC Standardization and Timezones
Given RetailIQ's multi-region architecture (planet-scale), date and time handling is critical.
1. **Never use `date.today()` or `datetime.now()`**: These return timezone-naive objects dependent on the host machine's local timezone.
2. **Always use UTC definitions**: Use `datetime.now(timezone.utc)` for exact times, and `datetime.now(timezone.utc).date()` for current dates.
3. This applies to both production API routes (`app/`), background scheduled Celery tasks (`app/tasks/`), and all `pytest` testing suites (`tests/`).

### Test Suite Execution
RetailIQ enforces comprehensive test coverage to maintain production stability. A failing test will block the CI/CD deployment pipeline.
- To execute the entire integration suite locally: `python -m pytest tests/ -v`
- To run a specific test suite or test case in isolation: `python -m pytest tests/test_name.py::test_function -vv -s`
- Avoid hardcoding values like `store_id=1` or `customer_id=1`. Instead, use dynamic SQLalchemy fixtures like `test_store.store_id`.

#### 1.1 Testing Principles (RetailIQ Standard)
All tests must be classified into one of three tiers during PR review:
- **VITAL**: Protects security boundaries, transaction atomicity, or critical business logic. Must never be removed.
- **REDUNDANT**: Tests language features or trivial getters. These should be removed to keep the CI pipeline fast.
- **WEAK**: Tests that assert structure but not integrity (e.g., `len > 0` without value checks). These must be rewritten to VITAL.

### 1. Development Environment Setup
```bash
# Clone and setup the environment
git clone <repo_url>
cd RetailIQ
python -m venv .venv

# Windows
.venv\Scripts\activate
# Unix/MacOS
source .venv/bin/activate

# Install all dependencies
pip install -r requirements-dev.txt

# Create your .env file
cp .env.example .env

# Run Alembic migrations to setup local DB
alembic upgrade head

# Start local server
flask run
```

### 2. Feature Implementation Lifecycle

When adding a new module or feature, strictly follow this pattern:
1.  **Define Models (`app/models/`)**: Create SQLAlchemy objects. Always use `db.Column` and ensure Foreign Keys have appropriate indexes.
2.  **Generate Migration**: Run `alembic revision --autogenerate -m "Add feature"`. Review the generated migration script manually!
3.  **Create Schemas (`app/<module>/schemas.py`)**: Use Marshmallow to define validation and serialization layers. **Never** trust raw incoming JSON.
4.  **Implement Service Layer (`app/<module>/services.py`)**: Extract all non-trivial business logic, aggregations, and decision-making into a dedicated service file.
5.  **Build Routes (`app/<module>/routes.py`)**: Add the Flask routes. Secure them with `@require_auth` or `@require_role('owner')`. **Always** return responses via the `standard_json` utility.
6.  **Write Tests (`tests/`)**: Create a new `test_<module>.py` file. Run `pytest -q tests/test_<module>.py`.

### 3. Core Engineering Standards

#### A. Security & Hardening
*   **Zero Trust Inputs**: All free-text endpoints must pass through the `sanitize_string` utility to prevent XSS.
*   **Standardized API Responses**: All API returns must use the `standard_json` wrapper from `app.utils.responses`.
*   **Validation Errors**: Ensure all Marshmallow-raised validation errors consistently return an HTTP `422 Unprocessable Entity` state according to RESTful semantics instead of 400.
*   **Logging**: Never log sensitive data. The application uses a custom `SensitiveDataFilter` to mask tokens and passwords.
*   **Rate Limiting**: Apply explicit limits to new blueprints if they exceed the global default (e.g., `limiter.limit("10/minute")`).

#### B. Performance, Database, & Latency
*   **The 200ms Rule**: No synchronous API request should take more than 200ms. If it does, offload it to Celery.
*   **N+1 Queries**: Use `joinedload` or `selectinload` in SQLAlchemy to prevent N+1 query loops when fetching relationships.
*   **Index Audits**: Ensure new tables with `user_id` or `store_id` have appropriate composite indexes.
*   **Database Agnostic Functions**: Always import generic SQL functions like `func` directly from `sqlalchemy` (e.g., `func.sum`) instead of relying on `db.func` which may not be dynamically supported by all drivers or scoped sessions.

#### C. Asynchronous Tasks (Celery)
*   Ensure all Celery tasks are **idempotent**. They may run multiple times if the message broker drops a connection.
*   Use the `app.tasks.db_session.task_session()` context manager for all background DB operations to avoid orphaned transactions.
*   **Webhook Delivery System**: All third-party webhook dispatches are handled asynchronously via Celery with exponential backoff and meticulous DB logging (`WebhookEvent`), tracking exact `last_response_code`, `delivery_url`, and `attempt_count` for unmatched reliability.

#### D. Timezone & DateTime Handling
*   **UTC Consistency**: Always use UTC-aware datetimes (`datetime.now(timezone.utc)`) within the application logic, databases, scheduling, and testing to prevent mismatches between multi-region environments. Do not use local `date.today()`.

### 4. CI/CD Pipeline & Code Quality

Deployments are governed by GitHub Actions. A PR will be blocked if any of the following fail:
*   **Linter**: `ruff check .` must return 0 errors. Use `ruff format .` before pushing.
*   **Unit Tests**: `pytest` must pass.
*   **Type Checker**: Pyre2 type analysis.
*   **Security Scan**: Bandit AST analysis for known Python vulnerabilities.

### 5. Deployment Checks
Before pushing to production, verify:
*   [ ] Alembic migrations apply cleanly.
*   [ ] New environment variables are documented.
*   [ ] AWS ECS Task Definitions reflect any new architecture components.
*   [ ] Backwards-incompatible schema changes are mitigated with zero-downtime multi-phase migrations.

---

### 6. Modular Audit Framework
RetailIQ now includes a suite of specialized audit prompts for brutal system reviews. These are located in `prompts/`:
1. `pass_1_security_penetration_tester.txt`: Focused on auth, payments, and injection.
2. `pass_2_performance_engineer.txt`: Targets N+1 queries and model latency.
3. `pass_3_backend_architect_ddd.txt`: Enforces domain boundaries and separation of concerns.
4. `pass_4_qa_architect_test_audit.txt`: Identifies coverage gaps and weak assertions.
5. `pass_5_reliability_engineer_sre.txt`: Audits retries, timeouts, and failure resilience.

### 7. Core Engineering Principles
- **Accuracy over Coverage**: 70% coverage with strict assertions is better than 100% with weak ones.
- **Fail Fast**: The application ## Comprehensive System Architecture

### Distributed Intelligence Infrastructure
RetailIQ is engineered as a high-availability, multi-region platform designed to handle thousands of retail points-of-sale concurrently.

#### Layered Architecture
1.  **Ingress Layer**: AWS Global Accelerator and ALB provide low-latency entry points.
2.  **Service Layer (Flask)**: Modular blueprints handle everything from Auth to Vision/AI.
3.  **Application Logic**: Optimized Service Layer patterns separate business logic from routing.
4.  **Async/Worker Layer**: Celery + Redis handles compute-heavy forecasting and batch aggregations.
5.  **Data Layer**: CockroachDB (SQL) for transactional consistency and Redis for real-time caching.

#### Specialized Subsystems
-   **Forecasting Engine**: Uses Facebook Prophet + XGBoost for demand sensing.
-   **Vision Pipeline**: Integrates YOLOv8 and Tesseract for shelf/invoice analytics.
-   **Audit & Security**: Centralized Mixins provide deep traceability for every record.

---

## Comprehensive Developer and Engineer Guide

### 🛠️ Core Engineering Standards
-   **Type Safety**: Use `typing` and `Mapped` throughout the codebase.
-   **RESTful Purity**: Ensure correct status codes (e.g., `422` for validation, `429` for rate limits).
-   **Error Enveloping**: Wrap all responses in `standard_json`.
-   **Asynchronous-First**: Offload any operation >200ms to Celery.

### 📦 Development Workflow
1.  **Environment Setup**:
    ```bash
    python -m venv .venv
    pip install -r requirements.txt
    ```
2.  **Database Management**:
    ```bash
    alembic upgrade head  # Apply latest migrations
    alembic check         # Verify schema alignment
    ```
3.  **Quality Control**:
    ```bash
    ruff format .         # Consistent styling
    ruff check .          # Static analysis
    pytest                # Full test suite execution
    ```

### 🧪 Testing Strategy
-   **Unit Tests**: Located in `tests/`, using in-memory SQLite for speed.
-   **Integration Tests**: Found in `tests/test_e2e.py`, simulating full business cycles.
-   **Security Tests**: Auditing rate limiting, store scoping, and token privacy in `tests/test_security.py`.

### 🚀 Production Deployment
Deployments are automated via GitHub Actions `.github/workflows/deploy.yml`. The pipeline includes:
-   **Security Gates**: Bandit and pip-audit scans.
-   **Migration Parity**: `alembic check` to prevent schema drift.
-   **Docker Optimization**: Distroless images with CPU-only PyTorch for efficiency.
. Use docker-compose up --build or activate a virtualenv config.
3. Refer to .env.example to build your local .env. Ensure that you generate strong JWT_PRIVATE_KEY and JWT_PUBLIC_KEY mock values.
4. Database migrations run via Alembic (lembic upgrade head).

### Contributing Guidelines
All PRs require strict linting (Ruff), security audits (Bandit), and comprehensive Pytest pass rates. No undocumented endpoints will be merged. Use standard standard_json responses universally.

## 5) Managing Docker Healthchecks

RetailIQ uses a **two-layer healthcheck strategy** to prevent ECS deployment timeouts:

1. **Dockerfile-level** (`Dockerfile.prod`): The `HEALTHCHECK` directive is conditional on `SERVICE_ROLE`. API containers cURL port 5000; workers and beat bypass with `exit 0`.
2. **ECS task-definition-level** (`aws/task-definitions/*.json`): The `worker.json` and `beat.json` task definitions include an explicit `healthCheck` block (`echo healthy`) that **overrides** the Dockerfile HEALTHCHECK entirely. This guarantees ECS marks the container as healthy immediately, avoiding deployment timeout race conditions between `wait_for_db`, the container startup period, and ECS stability checks.

**If you add a new service role:**
- Add a case in `scripts/entrypoint.sh` for the new role.
- Account for it in the `Dockerfile.prod` HEALTHCHECK conditional.
- Create a new `aws/task-definitions/<role>.json` with an explicit `healthCheck` block (use `echo healthy` for non-HTTP services).


---

## Production Readiness Checklist

Before deployment, ensure all are true:
- [ ] `pytest -q` passes fully.
- [ ] migrations apply cleanly on fresh DB and existing env.
- [ ] secrets managed externally (no plaintext secrets in repo).
- [ ] stable JWT key management strategy in place.
- [ ] log aggregation and monitoring configured.
- [x] rate limits applied on auth and all endpoints.
- [x] sensitive data log filter in place.
- [ ] backup/restore validated for PostgreSQL.
- [x] rate limits and auth policies reviewed.
- [ ] worker + beat autoscaling and queue policies defined.
- [ ] rollback strategy documented.

---

## Event-Aware Forecasting Module

The event-aware forecasting engine extends Prophet with a **business event calendar** so that upcoming holidays, promotions, and closures influence demand predictions as external regressors.

### Architecture

```
GET /events                 →  list / filter events
POST /events                →  create event
PUT  /events/{id}           →  update event
DELETE /events/{id}         →  delete event
GET /events/upcoming?days=N →  next N days of events
GET /forecasting/demand-sensing/{product_id}
                            →  run event-adjusted forecast (14-day), log to demand_sensing_log
```

### How It Works

1. **Event Registry** — `BusinessEvent` stores events with `start_date`, `end_date`, `event_type` (`HOLIDAY | FESTIVAL | PROMOTION | SALE_DAY | CLOSURE`), and optional `expected_impact_pct`.
2. **Regressor Injection** — `generate_demand_forecast` fetches up to 5 events (highest absolute `expected_impact_pct`) that overlap the history + horizon window. Binary regressor columns (`event_<id8>`: `1.0` on event days, `0.0` otherwise) are injected into the Prophet DataFrame via `m.add_regressor()`.
3. **Base vs Adjusted** — After Prophet prediction, `extra_regressors_additive` from the forecast is subtracted to yield `base_forecast`. Both are stored per-day.
4. **Demand Sensing Log** — Each run writes to `demand_sensing_log` with `base_forecast`, `event_adjusted_forecast`, and the active events list as JSONB.
5. **Fallback Safety** — If the history is below `MIN_DAYS_PROPHET` (35 days), the Ridge regression fallback is used and events are still recorded in the log (as active events metadata) but not applied as regressors.

### Data Models

| Table | Purpose |
|---|---|
| `business_events` | Event calendar per store |
| `demand_sensing_log` | Per-day forecast snapshots with active events |
| `event_impact_actuals` | Post-hoc measured impact of events on demand |

### Regressor Cap

To prevent Prophet from overfitting on sparse event data, a maximum of **5 regressors** are added per forecast run, chosen by highest absolute `|expected_impact_pct|`. Events with `NULL` impact are assigned a default behavioural `prior_scale=10.0`.

### Migration

Migration file: `migrations/versions/e7b8c9d0a1f2_events_tables.py`  
Alembic chain: `chain_integration (64289450c79b)` → `pricing_tables (c3d91f2a7b44)` → **`events_tables (e7b8c9d0a1f2)`** (HEAD)

---
## Vision / OCR Invoice Processing Module

The Vision module lets store owners photograph supplier invoices and have Tesseract OCR extract line items automatically. Extracted entries are fuzzy-matched against the product catalogue using PostgreSQL `pg_trgm`, then presented for human review before stock is atomically updated.

### Architecture

```
Upload Image ──▶ POST /vision/ocr/upload
                 │  saves file to uploads/ocr/{store_id}/
                 │  creates OcrJob (status=QUEUED)
                 └─▶ Celery task: process_ocr_job
                      │ pytesseract → raw text
                      │ parse_invoice_text() → structured items
                      │ pg_trgm similarity match → products
                      └─▶ OcrJobItems created, job → REVIEW

Review ──────────▶ GET  /vision/ocr/{job_id}           (poll status + items)
Confirm ─────────▶ POST /vision/ocr/{job_id}/confirm   (atomic stock update)
Dismiss ─────────▶ POST /vision/ocr/{job_id}/dismiss   (mark as FAILED)
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/vision/ocr/upload` | Upload invoice image (`.jpg/.png/.jpeg`, ≤10 MB). Returns `job_id`. |
| `GET`  | `/api/v1/vision/ocr/{job_id}` | Poll job status and extracted items with match confidence. |
| `POST` | `/api/v1/vision/ocr/{job_id}/confirm` | Confirm items → atomic stock increase + `StockAdjustment` log. |
| `POST` | `/api/v1/vision/ocr/{job_id}/dismiss` | Dismiss/reject the OCR result. |

### Data Model (migration `31f7ac7d8d9a`)

| Table | Purpose |
|-------|---------|
| `ocr_jobs` | Tracks each upload: image path, status (`QUEUED→PROCESSING→REVIEW→APPLIED\|FAILED`), raw OCR text. |
| `ocr_job_items` | Individual line items: raw text, matched `product_id`, confidence, quantity, unit price. |
| `vision_category_tags` | Category tags extracted from the invoice with confidence scores. |

### Parser (`app/vision/parser.py`)

Regex-based text parser handles: quantities with units (`pcs`, `kg`, `litre`, `pack`, `box`, `carton`, `dozen`), prices with `₹`/`Rs`/`Rs.` prefixes, comma-separated numbers, and multi-line product names.

### Testing (10 tests in `tests/test_vision.py`)

- **Parser**: basic extraction, comma prices, case-insensitive units, multi-line accumulation
- **Upload API**: valid image → 201, oversized → 413, wrong MIME → 415
- **OCR task**: simulated task creates items and transitions job to REVIEW
- **Confirm**: atomic stock update verified; partial failure rolls back all changes

### Security

All endpoints require JWT auth (`@require_auth`). Job ownership is enforced via `store_id` comparison. OCR uploads are rate-limited to 20/hour per store.

---

## Security & Performance Hardening

The hardening pass adds cross-cutting security and performance controls without new features.

### Rate Limiting

| Endpoint | Limit | Key |
|----------|-------|-----|
| `POST /auth/register` | 5/hour | IP |
| `POST /auth/login` | 10/minute | IP |
| `POST /vision/ocr/upload` | 20/hour | `store_id` (from JWT) |
| All other endpoints | 300/minute | IP (global default) |

Powered by `flask-limiter` with Redis storage. Rate limiting is disabled in tests (`RATELIMIT_ENABLED=False`) except for the dedicated `test_login_rate_limit` test which uses a separate app fixture.

### FK Index Audit (migration `f4a5b6c7d8e9`)

35 indexes added to FK columns across all post-launch tables: `supplier_products`, `purchase_order_items`, `gst_transactions`, `loyalty_transactions`, `credit_transactions`, `ocr_job_items`, `ocr_jobs`, `vision_category_tags`, `whatsapp_templates`, `whatsapp_message_log`, `store_group_memberships`, `chain_daily_aggregates`, `inter_store_transfer_suggestions`, `business_events`, `demand_sensing_log`, `event_impact_actuals`, `stock_adjustments`, `stock_audit_items`, `product_price_history`, and more.

### Input Sanitization

- **OCR text truncation**: `parse_invoice_text()` truncates input to 50,000 characters to prevent DoS from huge payloads.
- **Free-text fields**: `app/utils/sanitize.py` provides `sanitize_string(value, max_length)` which strips leading/trailing whitespace and truncates. Applied on supplier create/update (name 128, address 512) and PO notes.

### Log Redaction (`SensitiveDataFilter`)

A `logging.Filter` attached to the Flask app logger and the root logger redacts values matching `token`, `password`, `access_token`, or `secret` patterns with `***REDACTED***`. This prevents API keys and passwords from appearing in log files.

### Slow Request Detection

In development mode (`FLASK_ENV=development` and not `TESTING`):
- `SQLALCHEMY_ECHO=True` logs all SQL queries.
- An `@app.after_request` hook logs `[SLOW REQUEST] {method} {path} took {time}ms` for any response taking >500ms.

---

## AWS Deployment & CI/CD

RetailIQ is fully documented for production deployment on **AWS ECS Fargate**.

The repository includes:
- Multi-stage `Dockerfile.prod`
- ECS Task Definitions (`aws/task-definitions/`)
- IAM roles and CloudWatch alarms (`aws/iam/`, `aws/cloudwatch/`)
- Full GitHub Actions CI/CD pipeline (`.github/workflows/deploy.yml`)

For the comprehensive step-by-step guide, including architecture diagrams, cost optimization, security hardening, and troubleshooting, see the [**AWS Deployment Guide (DEPLOYMENT.md)**](./DEPLOYMENT.md).

---

## Contributing
1. Create a branch (`feature/your-feature-name`).
2. Implement code + tests. Ensure code coverage remains high.
3. Open a Pull Request detailing the architecture impact, database changes, and rollback plan.

---

## Comprehensive Developer and Engineer Guide

This guide provides technical deep-dives for engineers contributing to RetailIQ.

### 1. Development Principles
- **Domain-Driven Design (DDD)**: Each module (e.g., `inventory`, `transactions`) should encapsulate its own domain logic and models.
- **Fail-Fast Validation**: Use Marshmallow schemas to validate all incoming request data at the ingestion point.
- **Async by Default**: Offload any operation taking >200ms or involving external APIs to Celery.
- **Schema First**: All database changes must be managed via Alembic migrations.

### 2. Service Layer Pattern
Routes should remain thin. Complex business logic (e.g., price history logging, alert evaluation) belongs in the module's `services.py`.
Example:
```python
# app/inventory/routes.py
@inventory_bp.route("/products", methods=["POST"])
def create_product():
    data = ProductCreateSchema().load(request.json)
    product = ProductService.create_new_product(data)
    return standard_json(data=ProductSchema().dump(product), status_code=201)
```

### 3. Error Handling & Responses
Always use `app.utils.responses.standard_json` to return data. This ensures the frontend receives a predictable JSON envelope:
```json
{
  "success": true,
  "message": "Operation successful",
  "data": { ... },
  "error": null
}
```

### 4. Testing
- **E2E Tests**: Use `tests/test_e2e.py` for long-running user journeys.
- **Mocking**: Use `pytest-mock` to mock external services (e.g., WhatsApp Meta API).
- **Environment**: Tests run against an in-memory SQLite database. Avoid PG-specific syntax in core logic unless guarded by dialect checks.

### 5. CI/CD Pipeline
The CI/CD pipeline is optimized for speed (<3 minutes) and reliability:
- **Fast Dependency Installation**: Uses `uv` package manager for 10x faster installs
- **Parallel Testing**: Tests run in parallel with `pytest-xdist`
- **Smart Service Management**: No external services (Postgres/Redis) needed as tests use SQLite in-memory
- **Quality Gates**: Combined lint (Ruff), security (Bandit), and migration checks in one job
- **Version Strategy**: PRs test on Python 3.10 only; main branch tests on 3.10, 3.11, and 3.12
- **Docker Optimization**: Production Docker builds run on main branch only with multi-stage caching

For emergency hotfixes, use the `ci-fast.yml` workflow which runs critical tests only in under 2 minutes.

### 6. Deployment
Changes merged to `main` are automatically deployed to AWS ECS. The deployment pipeline:
1. Runs the optimized test suite
2. Builds the production Docker image using the multi-stage Dockerfile.prod
3. Pushes to Amazon ECR with SHA tagging
4. Performs zero-downtime rolling updates across API, Worker, and Beat ECS services
5. Verifies service health and sends Slack notifications

Ensure `alembic upgrade head` is part of the deployment script for schema migrations.

---

## License
This project is proprietary software for RetailIQ.
