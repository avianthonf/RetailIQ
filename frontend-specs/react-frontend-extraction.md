# RetailIQ Frontend Extraction for a 1:1 React Build

This document extracts the frontend requirements implied by the current RetailIQ codebase and the existing `frontend-specs` artifacts. It is intended as a build blueprint for a full React frontend that matches the backend feature surface and business rules as closely as possible.

Important limitation: the repository does not contain an existing rendered web UI, component source, or design assets. So "1:1" here means:

- 1:1 feature coverage against the backend/API surface
- 1:1 form fields, validation, business rules, and screen states where they can be derived
- 1:1 interaction model where the route handlers and frontend spec docs imply one
- best-effort visual fidelity based on the design-system docs in `frontend-specs/`

## 1. Sources Used

- `frontend-specs/frontend-requirements-and-specs.txt`
- `frontend-specs/UI-Design-System.md`
- `frontend-specs/System-Integrity-Policy.md`
- `frontend-specs/Global-Sync-Configuration.json`
- `frontend-specs/Tax-Rounding-Spec.json`
- `frontend-specs/Hardware-Integration-Manifest.md`
- backend route handlers under `app/**/routes.py`
- backend schemas under `app/**/schemas.py`

## 2. Recommended React Stack

- React 19 + TypeScript
- React Router for app routing
- TanStack Query for server state
- Zustand or Redux Toolkit for client session/cart/offline state
- React Hook Form + Zod for forms
- Tailwind CSS or CSS Modules for styling
- Recharts or ECharts for charts
- decimal.js or big.js for currency and tax math
- Dexie over IndexedDB for offline transactions and snapshots
- ZXing for barcode scanning
- WebSocket client abstraction with polling fallback

## 3. Global API Contract

There are two response styles in the backend:

1. Standard envelope:
   - Shape: `{ success, data, error, meta, timestamp, message? }`
   - Used by most `/api/v1/*` endpoints and some `/api/v2/*`

2. Raw JSON responses:
   - Some routes return plain `jsonify(...)` payloads without the standard envelope
   - Most visible in finance, vision, and some AI routes

Frontend requirement:

- Build a single API client that can normalize both response styles.
- Treat `error.code` as canonical when present.
- Support status-specific UX for `401`, `403`, `404`, `409`, `422`, `423`, `429`, `500`, `503`.

## 4. Auth Model

Base routes: `/api/v1/auth`

### Register
- `POST /register`
- Fields:
  - `mobile_number` string, 10-15 digits
  - `password` string, min 6
  - `full_name` string, 2-100 chars
  - `email` valid email, required
  - `store_name` optional, max 100
  - `role` optional, `owner | staff`
- Default UX:
  - owner-first onboarding wizard
  - submit creates inactive user
  - OTP is sent next

### Verify OTP
- `POST /verify-otp`
- Fields:
  - `mobile_number`
  - `otp` exactly 6 chars
- Success payload includes:
  - `access_token`
  - `refresh_token`
  - `user_id`
  - `role`
  - `store_id`

### Resend OTP
- `POST /resend-otp`
- Fields:
  - `contact` or `mobile_number`
  - `purpose` optional, default `registration`
- Success returns:
  - `message`
  - `contact`
  - `otp_ttl`
  - `resend_after`

### Login
- `POST /login`
- Fields:
  - `mobile_number`
  - `password`
  - `mfa_code` optional, length 6
- Special states:
  - `mfa_required: true` means show MFA step inline
  - `423 ACCOUNT_LOCKED` means lockout screen with timer messaging
  - `403 INACTIVE_ACCOUNT` means redirect to verify flow

### MFA
- `POST /mfa/setup`
  - requires auth
  - body includes `password`
  - returns `secret`, `provisioning_uri`
- `POST /mfa/verify`
  - requires auth
  - body includes `mfa_code`

### Token Refresh
- `POST /refresh`
- body: `{ refresh_token }`
- May return `503 REDIS_UNAVAILABLE`

### Logout
- `DELETE /logout`
- optional body: `{ refresh_token }`

### Password Reset
- `POST /forgot-password`
- `POST /reset-password`

Frontend auth state should store:

- access token in memory
- refresh token in secure storage strategy suitable for web app constraints
- user identity: `user_id`, `role`, `store_id`
- session mode: `online | offline-safety`

## 5. App Information Architecture

Recommended route map:

- `/auth/register`
- `/auth/verify`
- `/auth/login`
- `/auth/forgot-password`
- `/auth/reset-password`
- `/app/dashboard`
- `/app/analytics`
- `/app/inventory`
- `/app/inventory/:productId`
- `/app/inventory/audit`
- `/app/transactions`
- `/app/transactions/:transactionId`
- `/app/transactions/:transactionId/return`
- `/app/pos`
- `/app/customers`
- `/app/customers/:customerId`
- `/app/pricing`
- `/app/store/profile`
- `/app/store/categories`
- `/app/store/tax-config`
- `/app/finance`
- `/app/finance/kyc`
- `/app/finance/loans`
- `/app/finance/ledger`
- `/app/marketplace`
- `/app/marketplace/orders`
- `/app/marketplace/orders/:orderId`
- `/app/receipts`
- `/app/staff`
- `/app/vision/intake`
- `/app/assistant`
- `/app/settings`

Navigation behavior from specs:

- Mobile: bottom nav, full-screen modals
- Tablet: collapsed icon sidebar
- Desktop: persistent sidebar, breadcrumbs, 3-4 column dashboard grids

## 6. Design System to Implement

From `UI-Design-System.md` and related specs:

- Background: `#0F172A`
- Active: `#3B82F6`
- Success: `#10B981`
- Alert: `#EF4444`
- Primary text: `#F8FAFC`
- Secondary text: `#94A3B8`
- Glass surface: `rgba(255,255,255,0.05)` with blur

Required states:

- skeletons instead of dashboard spinners
- explicit empty states
- explicit brutal recovery states for auth expiry, rate limit, and server failure

Responsive rules:

- `<640`: single column
- `640-1024`: two-column grid
- `>1024`: 3-4 column grid

Low-end device mode from system policies:

- disable blur
- use solid backgrounds
- disable sparkline animation

## 7. Shared Runtime Rules

### Currency and Tax
- Currency is INR in specs
- Use `HALF_UP`
- External precision: 2
- Internal precision: 4
- Allowed GST rates: `0, 5, 12, 18, 28`
- Never use native JS float for monetary calculations

### Offline Safety Mode
- Enter if auth expires while offline
- IndexedDB stores offline transactions and snapshots
- FIFO replay for transactions
- `is_manual_review` must be surfaced for conflicted syncs
- use unique device receipt prefixes in offline mode

### Sync Config
- `Global-Sync-Configuration.json` overrides static docs
- Current extracted values:
  - `max_offline_txns = 500`
  - `max_offline_days = 3`
  - `warning_threshold = 400`
  - `config_refresh = 3600s`
  - `inventory_poll = 300s`

### Scanner and Hardware
- Desktop scanner:
  - HID keyboard emulation
  - global rapid-key listener
  - auto-submit on Enter/Tab suffix
- Mobile scanner:
  - camera viewfinder
  - 3fps cap
  - torch toggle
- Printing:
  - ESC/POS target
  - fallback to PDF/image sharing

## 8. Core Shared React State

Recommended client state slices:

- `auth`
  - tokens
  - user
  - role
  - offline safety mode
- `ui`
  - sidebar state
  - low-end mode
  - modals
  - alert drawer
- `cart`
  - line items
  - quantities
  - discounts
  - customer
  - optimistic totals
- `sync`
  - offline queue
  - pending snapshots
  - manual review queue
  - websocket connectivity
- `settings`
  - store profile
  - tax config
  - receipt template
  - hardware preferences

## 9. Dashboard Screens

### Executive Dashboard
Primary endpoints:

- `GET /api/v1/dashboard/overview`
- `GET /api/v1/dashboard/alerts`
- `GET /api/v1/dashboard/alerts/feed?limit=20`
- `GET /api/v1/dashboard/live-signals`
- `GET /api/v1/analytics/dashboard`

Extracted KPI payloads include:

- `sales`, `sales_delta`, `sales_sparkline`
- `gross_margin`, `gross_margin_delta`, `gross_margin_sparkline`
- `inventory_at_risk`, `inventory_at_risk_delta`, `inventory_at_risk_sparkline`
- `outstanding_pos`, `outstanding_pos_delta`, `outstanding_pos_sparkline`
- `loyalty_redemptions`, `loyalty_redemptions_delta`, `loyalty_redemptions_sparkline`
- `online_orders`, `online_orders_delta`, `online_orders_sparkline`
- `last_updated`

Dashboard page should contain:

- KPI card row
- alerts drawer or right rail
- live signals ticker/list
- top products today
- 7-day revenue chart with moving average
- category breakdown chart
- payment mode breakdown
- insight cards

Alerts data shape:

- `id`
- `type`
- `severity`
- `title`
- `message`
- `timestamp`
- `source`
- `acknowledged`
- `resolved`

## 10. Analytics Screens

Base: `/api/v1/analytics`

### Revenue
- `GET /revenue?start&end&group_by=day|week|month`
- Returns rows with:
  - `date`
  - `revenue`
  - `profit`
  - `transactions`
  - `moving_avg_7d`

### Profit
- `GET /profit?start&end&group_by=day|week|month`
- Returns:
  - `date`
  - `profit`
  - `revenue`
  - `margin_pct`
  - `moving_avg_7d`

### Top Products
- `GET /top-products?metric=revenue|quantity|profit&limit`

### Category Breakdown
- `GET /category-breakdown?start&end`

### Contribution
- `GET /contribution?start&end&compare_start&compare_end`
- Returns:
  - `skus[]`
  - `summary`
- Each SKU includes:
  - `product_id`
  - `name`
  - `revenue_current`
  - `revenue_prior`
  - `delta_revenue`
  - `contribution`
  - `is_pareto`
  - `price_effect`
  - `volume_effect`
  - `profit_current`

### Payment Modes
- `GET /payment-modes`

### Customers Summary
- `GET /customers/summary`

### Diagnostics
- `GET /diagnostics`
- Returns:
  - `trend_deviations`
  - `sku_rolling_variance`
  - `margin_drift`

UI modules needed:

- date-range picker
- chart type switcher
- KPI summary bar
- Pareto table
- diagnostic flags table
- CSV export hooks

## 11. Inventory Screens

Base: `/api/v1/inventory`

### Product List
- `GET /products` is described in older docs, but actual backend list route is the collection root:
  - `GET /api/v1/inventory`
- Query params:
  - `page`
  - `page_size`
  - `category_id`
  - `is_active`
  - `low_stock`
  - `slow_moving`

Product row shape:

- `product_id`
- `store_id`
- `category_id`
- `name`
- `sku_code`
- `uom`
- `cost_price`
- `selling_price`
- `current_stock`
- `reorder_level`
- `supplier_name`
- `barcode`
- `image_url`
- `is_active`
- `lead_time_days`

Required table/grid behaviors:

- filters
- pagination
- low-stock badge when `current_stock <= reorder_level`
- slow-moving filter
- category filter

### Create Product
- `POST /api/v1/inventory`
- owner only
- fields:
  - `name`
  - `category_id`
  - `sku_code` optional, backend auto-generates if blank
  - `uom` in `pieces | kg | litre | pack`
  - `cost_price`
  - `selling_price`
  - `current_stock`
  - `reorder_level`
  - `supplier_name`
  - `barcode`
  - `image_url`
  - `lead_time_days`
  - `hsn_code`
- validation:
  - `selling_price >= cost_price`

### Edit Product
- `PUT /api/v1/inventory/:productId`
- supports partial update
- if price changes and `cost_price > selling_price`, backend creates a `MARGIN_WARNING` alert

### Deactivate Product
- `DELETE /api/v1/inventory/:productId`
- soft-deactivates product

### Stock Update Modal
- `POST /api/v1/inventory/:productId/stock`
- alias exists at `/stock-update`
- fields:
  - `quantity_added`
  - `purchase_price`
  - `date`
  - `supplier_name`
  - `update_cost_price`

### Stock Audit
- `POST /api/v1/inventory/audit`
- owner only
- fields:
  - `items[]`
  - `notes`
- each item:
  - `product_id`
  - `actual_qty`
- response:
  - `audit_id`
  - `audit_date`
  - `items[]` with discrepancy info

### Price History
- `GET /api/v1/inventory/:productId/price-history`

### Inventory Alerts
- `GET /api/v1/inventory/alerts`
- `DELETE /api/v1/inventory/alerts/:alertId`

Inventory page should include:

- list/table view
- create/edit drawer
- stock intake modal
- audit workflow screen
- product detail side panel
- barcode tools
- price history timeline

## 12. POS and Transactions

Backend reality:

- actual checkout endpoint in this repo is `POST /api/v1/transactions`
- older spec mentions `/transactions/checkout`, but route handlers implement root collection create

### Create Transaction
- `POST /api/v1/transactions`
- fields:
  - `transaction_id` UUID, required client-generated
  - `timestamp` ISO datetime, required client-generated
  - `payment_mode` one of `CASH | UPI | CARD | CREDIT`
  - `customer_id` optional
  - `notes` optional, max 200
  - `line_items[]`
- line item fields:
  - `product_id`
  - `quantity`
  - `selling_price`
  - `discount_amount`

POS frontend requirements:

- client generates UUID
- client timestamps transaction
- client computes optimistic subtotal and totals locally
- if scanner detects existing product in cart, increment quantity locally
- maintain offline queue when disconnected

### Batch Sync
- `POST /api/v1/transactions/batch`
- up to 500 transactions
- needed for offline replay

### Transactions List
- `GET /api/v1/transactions`
- filters:
  - `page`
  - `page_size`
  - `start_date`
  - `end_date`
  - `payment_mode`
  - `customer_id`
  - `min_amount`
  - `max_amount`
- staff role is restricted to today’s transactions

### Transaction Detail
- `GET /api/v1/transactions/:id`

### Return Transaction
- `POST /api/v1/transactions/:id/return`
- owner only
- fields:
  - `items[]`
- each item:
  - `product_id`
  - `quantity_returned`
  - `reason`

### Daily Summary
- `GET /api/v1/transactions/summary/daily?date=YYYY-MM-DD`

POS screen modules:

- scanner/search input
- cart table
- customer attach
- payment mode selector
- totals panel
- offline queue indicator
- sync resolution drawer
- return workflow

## 13. Customers and Loyalty

Base: `/api/v1/customers`

### Customer List
- `GET /api/v1/customers`
- filters:
  - `page`
  - `page_size`
  - `name`
  - `mobile`
  - `created_after`
  - `created_before`

### Create Customer
- `POST /api/v1/customers`
- fields:
  - `name`
  - `mobile_number` 10-15 digits
  - `email`
  - `gender` in `male | female | other`
  - `birth_date`
  - `address`
  - `notes`

### Customer Detail
- `GET /api/v1/customers/:id`
- `PUT /api/v1/customers/:id`

### Customer Transactions
- `GET /api/v1/customers/:id/transactions`
- filters:
  - `page`
  - `page_size`
  - `date_from`
  - `date_to`
  - `category_id`
  - `min_amount`
  - `max_amount`

### Customer Summary
- `GET /api/v1/customers/:id/summary`

### Top Customers
- `GET /api/v1/customers/top?metric=revenue|visits&limit`

### Customer Analytics
- `GET /api/v1/customers/analytics`

Also exposed:

- loyalty and credit endpoints under:
  - `/api/v1/loyalty/*`
  - `/api/v1/credit/*`

The frontend should reserve space for:

- customer list
- customer profile
- purchase history
- loyalty account
- credit account

## 14. Store Setup and Settings

Base: `/api/v1/store`

### Store Profile
- `GET /profile`
- `PUT /profile`

Editable fields:

- `store_name`
- `store_type` one of:
  - `grocery`
  - `pharmacy`
  - `general`
  - `electronics`
  - `clothing`
  - `other`
- `city`
- `state`
- `gst_number`
- `currency_symbol`
- `working_days`
- `opening_time`
- `closing_time`
- `timezone`

Special rule:

- first time `store_type` is set, backend seeds default categories

### Categories
- `GET /categories`
- `POST /categories`
- `PUT /categories/:categoryId`
- `DELETE /categories/:categoryId`

Category fields:

- `name`
- `color_tag`
- `is_active`
- `gst_rate` 0-100

Category constraints:

- max 50 categories
- cannot delete if products still assigned
- delete becomes soft deactivate

### Tax Config
- `GET /tax-config`
- `PUT /tax-config`

Tax config editor should support:

- bulk category GST editing
- slab validation
- decimal-safe local preview

## 15. Pricing Screens

Base: `/api/v1/pricing`

### Suggestions Inbox
- `GET /suggestions`
- suggestion fields:
  - `id`
  - `product_id`
  - `product_name`
  - `current_price`
  - `suggested_price`
  - `price_change_pct`
  - `suggestion_type`
  - `reason`
  - `confidence`
  - `confidence_score`
  - `status`
  - `created_at`
  - `current_margin_pct`
  - `suggested_margin_pct`

### Apply Suggestion
- `POST /suggestions/:id/apply`

### Dismiss Suggestion
- `POST /suggestions/:id/dismiss`

### Pricing History
- `GET /history?product_id=...`

### Pricing Rules
- `GET /rules`
- `PUT /rules`
- update body:
  - `rule_type`
  - `parameters`
  - `is_active`

Pricing UI needs:

- recommendation cards/table
- comparison modal
- margin impact labels
- rules editor
- history chart/timeline

## 16. Finance Screens

Backend prefix is actually `/api/v2/finance`, not `/api/v1/finance`

### KYC
- `POST /api/v2/finance/kyc/submit`
- `GET /api/v2/finance/kyc/status`
- submit fields:
  - `business_type`
  - `tax_id`
  - `document_urls` object

### Credit Score
- `GET /api/v2/finance/credit-score`
- returns:
  - `score`
  - `tier`
  - `factors`
  - `last_updated`
- `POST /api/v2/finance/credit-score/refresh`

### Accounts
- `GET /api/v2/finance/accounts`

### Ledger
- `GET /api/v2/finance/ledger?account_id=...`

### Loans
- `POST /api/v2/finance/loans/apply`
- fields:
  - `product_id`
  - `amount`
  - `term_days`
- `GET /api/v2/finance/loans`
- `POST /api/v2/finance/loans/:loanId/disburse`

### Payments
- `POST /api/v2/finance/payments/process`
- fields:
  - `amount`
  - `payment_method`

### Treasury
- `GET /api/v2/finance/treasury/balance`
- `PUT /api/v2/finance/treasury/sweep-config`
- config fields:
  - `strategy`
  - `min_balance`

### Finance Dashboard
- `GET /api/v2/finance/dashboard`
- returns:
  - `cash_on_hand`
  - `treasury_balance`
  - `total_debt`
  - `credit_score`

Finance UI modules:

- KYC stepper
- radial credit gauge
- accounts cards
- ledger table
- loan application modal
- debt tracker
- treasury settings panel

## 17. Payments Integration

Base: `/api/v1/payments`

### Providers
- `GET /providers?country_code=IN`

### Payment Intent
- `POST /intent`
- fields:
  - `transaction_id`
  - `provider_code`
  - `phone_number` optional
  - `method` optional

Important note:

- current backend hardcodes currency `"USD"` in this route even though the broader product is INR-first
- frontend should not assume provider amounts are localized correctly until backend is aligned

## 18. Receipts and Barcode Flows

### Receipt Template
- `GET /api/v1/receipts/template`
- `PUT /api/v1/receipts/template`
- fields:
  - `header_text`
  - `footer_text`
  - `show_gstin`
  - `paper_width_mm`

### Print Jobs
- `POST /api/v1/receipts/print`
- body:
  - `transaction_id` optional
  - `printer_mac_address` optional
- `GET /api/v1/receipts/print/:jobId`

### Barcode Lookup
- `GET /api/v1/barcodes/lookup?value=...`

### Barcode Register
- route is implemented as `POST /api/v1/barcodes/register`
- body:
  - `product_id`
  - `barcode_value`
  - `barcode_type`

### Barcode List
- route is implemented as `GET /api/v1/barcodes/list?product_id=...`

Needed frontend modules:

- receipt settings form
- print queue widget
- barcode assignment modal
- barcode lookup/search utility

## 19. Vision and OCR Flows

### OCR Invoice Intake
Base: `/api/v1/vision`

- `POST /ocr/upload`
  - multipart field: `invoice_image`
  - max 10MB
  - allowed: png/jpg/jpeg
- `GET /ocr/:jobId`
- `POST /ocr/:jobId/confirm`
- `POST /ocr/:jobId/dismiss`

OCR review UI needs:

- upload dropzone
- polling job status
- review table with product matching
- quantity/unit-price corrections
- confirm to apply stock updates

### Shelf Scan

Two variants exist:

- `POST /api/v2/ai/vision/shelf-scan`
- `POST /api/v1/vision/shelf-scan`

Both expect image source input and return analysis.

### Receipt Digitization

Two variants exist:

- `POST /api/v2/ai/vision/receipt` with `image_url`
- `POST /api/v1/vision/receipt` multipart with `receipt_image`

Frontend should prefer one canonical path and adapt via feature flag.

## 20. AI Assistant and Forecasting

### AI v2
Base: `/api/v2/ai`

- `POST /forecast`
  - body: `{ product_id }`
- `POST /pricing/optimize`
  - body: `{ product_ids }`
- `POST /nlp/query`
  - body: `{ query }`
- `POST /recommend`
  - body: `{ user_id }`

Potential UI surfaces:

- forecast detail chart with confidence visuals
- price optimization review list
- floating assistant chat
- recommendations panel

### Forecasting v1
- additional forecasting routes exist under `/api/v1/forecasting/*`

## 21. Marketplace Screens

Backend prefix is `/api/v2/marketplace`

### Search
- `GET /search`
- params:
  - `query`
  - `category`
  - `price_min`
  - `price_max`
  - `supplier_rating_min`
  - `moq_max`
  - `sort_by`
  - `page`

### Recommendations
- `GET /recommendations?category&urgency`

### RFQ
- `POST /rfq`
- `GET /rfq/:rfqId`

### Orders
- `POST /orders`
- `GET /orders`
- `GET /orders/:orderId`
- `GET /orders/:orderId/track`

### Supplier Tools
- `GET /suppliers/dashboard?supplier_id=...`
- `GET /suppliers/:supplierId/catalog`
- `POST /suppliers/onboard`

Marketplace UI modules:

- search results grid
- supplier comparison
- RFQ builder
- order detail page
- logistics timeline

## 22. Offline Snapshot

- `GET /api/v1/offline/snapshot`
- If missing, returns `202` and triggers background build
- success data:
  - `built_at`
  - `size_bytes`
  - `snapshot`

Frontend should:

- cache the latest successful snapshot in IndexedDB
- expose freshness timestamp
- enable read-only analytics mode offline

## 23. Role-Based UI

Extracted roles:

- `owner`
- `staff`
- `admin` appears in config docs, but route-level checks mainly use `owner` and `staff`

Owner-only areas:

- product creation
- stock audit
- category create/update/delete
- store profile update
- tax config update
- pricing actions in practice should likely be owner-visible
- loan apply/disburse
- sweep config
- returns
- KYC submit

Staff-specific behavior:

- transaction list restricted to current day
- POS session-aware workflows

## 24. Known Backend Contract Inconsistencies the Frontend Must Handle

These matter for a real React implementation:

- older docs say `/api/v1/inventory/products`, backend collection route is `/api/v1/inventory`
- older docs say `/api/v1/transactions/checkout`, backend create route is `/api/v1/transactions`
- finance routes are mounted under `/api/v2/finance`
- marketplace routes are mounted under `/api/v2/marketplace`
- some OpenAPI paths appear stale or broader than actual route semantics
- some endpoints use standard envelope, others raw JSON
- barcode routes are implemented as `/register` and `/list`, while OpenAPI output may simplify them
- WebSocket support in repo is placeholder-level; frontend should support polling fallback

## 25. Suggested React Project Structure

```text
src/
  app/
    router.tsx
    providers.tsx
  api/
    client.ts
    auth.ts
    dashboard.ts
    inventory.ts
    transactions.ts
    analytics.ts
    customers.ts
    finance.ts
    pricing.ts
    receipts.ts
    vision.ts
    marketplace.ts
  features/
    auth/
    dashboard/
    analytics/
    inventory/
    pos/
    transactions/
    customers/
    store/
    pricing/
    finance/
    receipts/
    vision/
    marketplace/
    assistant/
  components/
    layout/
    charts/
    data-table/
    forms/
    feedback/
    hardware/
  state/
    auth.ts
    cart.ts
    sync.ts
    ui.ts
  lib/
    decimal.ts
    scanner.ts
    websocket.ts
    offline-db.ts
    permissions.ts
```

## 26. Build Order

Recommended implementation order:

1. auth shell and API client normalization
2. app layout, sidebar, route guards, error handling
3. dashboard and analytics
4. inventory and store settings
5. POS and transactions with decimal-safe totals
6. customers, pricing, receipts
7. finance
8. OCR and AI features
9. marketplace
10. offline queue, safety mode, sync resolution center

## 27. Bottom Line

A full React frontend is very feasible from this repo, but it should be treated as a backend-driven product shell rather than a pixel clone of an existing UI. The codebase already gives us:

- a broad route surface
- enough schema detail for forms and validations
- business invariants for offline, tax, and hardware workflows
- a design direction for layout, colors, states, and interactions

The main implementation risk is not missing features. It is normalizing inconsistent endpoint contracts and choosing one canonical frontend interpretation where the specs and route handlers diverge.
