# RetailIQ Frontend Master Spec

This is the exhaustive frontend handoff document for building a complete React frontend against the current RetailIQ repository.

It supersedes the earlier extraction by adding:

- full screen inventory
- component-level anatomy
- route-by-route API mapping
- form field and validation coverage
- client state model
- state machines for key flows
- offline and sync rules
- canonical frontend decisions where backend/docs disagree
- unresolved gaps and risks

This is still not a literal pixel clone of an existing UI, because the repo does not contain a shipped frontend or Figma source. It is the closest exhaustive implementation spec that can be derived from the backend and the provided frontend-spec docs.

## 1. Deliverable Scope

Target frontend surfaces:

- Web admin dashboard
- Desktop/POS terminal UI
- Mobile merchant/POS responsive UI

Functional domains covered:

- auth and onboarding
- dashboard and analytics
- inventory, pricing, suppliers, purchase orders
- POS, transactions, returns, receipts, barcode scanning
- customers, loyalty, customer credit
- store profile, category, tax/GST settings
- finance, KYC, loans, ledger, treasury
- AI assistant, demand forecast, OCR, shelf scan
- marketplace procurement
- staff sessions and performance
- events calendar and demand-sensing
- WhatsApp operations
- chain/multi-store operations
- offline snapshot and sync handling
- i18n, currency, country metadata

## 2. Canonical Frontend Technology Choice

Recommended stack:

- React 19
- TypeScript
- React Router
- TanStack Query
- Zustand
- React Hook Form
- Zod
- Tailwind or CSS Modules
- Recharts or ECharts
- Dexie + IndexedDB
- decimal.js or big.js
- ZXing

Non-negotiable implementation constraints:

- decimal-safe money calculations
- normalized API layer for inconsistent response envelopes
- role-aware routing and action gating
- offline queue and replay support
- polling fallback for real-time features

## 3. Canonical App Route Tree

Suggested route tree:

```text
/auth
  /register
  /verify-otp
  /login
  /forgot-password
  /reset-password

/app
  /dashboard
  /analytics
  /inventory
  /inventory/new
  /inventory/:productId
  /inventory/audit
  /pricing
  /transactions
  /transactions/:transactionId
  /transactions/:transactionId/return
  /pos
  /customers
  /customers/:customerId
  /customers/:customerId/loyalty
  /customers/:customerId/credit
  /suppliers
  /suppliers/:supplierId
  /purchase-orders
  /purchase-orders/:poId
  /finance
  /finance/kyc
  /finance/ledger
  /finance/loans
  /finance/treasury
  /store/profile
  /store/categories
  /store/tax
  /gst
  /tax-engine
  /receipts
  /vision/intake
  /vision/jobs/:jobId
  /assistant
  /marketplace
  /marketplace/orders
  /marketplace/orders/:orderId
  /staff
  /events
  /whatsapp
  /chain
  /settings
```

## 4. Primary Layout System

### Desktop Layout
- persistent left sidebar
- top app bar with breadcrumb, search, alert bell, account menu
- content canvas with max-width sections
- optional right-side drawers for alerts, sync, details

### Tablet Layout
- collapsed icon sidebar
- stacked filter bars
- drawers for secondary detail

### Mobile Layout
- bottom navigation
- full-screen sheets instead of side drawers
- scan-first POS flow
- larger tap targets

## 5. Design Tokens

Source of truth from `UI-Design-System.md`:

- background: `#0F172A`
- active: `#3B82F6`
- success: `#10B981`
- critical: `#EF4444`
- text primary: `#F8FAFC`
- text secondary: `#94A3B8`
- glass background: `rgba(255,255,255,0.05)`

Additional implementation rules:

- glassmorphism only when low-end mode is off
- use skeleton placeholders for dashboard cards and tables
- empty-state modules are required, not optional
- use success-toned empty state for no alerts

## 6. Global UX Contracts

### Loading
- no KPI spinners
- preserve layout with skeletons
- table skeleton rows must match final row density

### Empty
- inventory search empty
- analytics no-data empty
- alerts success empty

### Errors
- `401`: session-expired modal
- `401 + offline`: enter safety mode
- `429`: toast with retry countdown
- `500`: full-page lost-signal view
- `503`: service unavailable banner with retry policy

### Toast Types
- success
- warning
- destructive
- sync
- background retry

## 7. Global API Normalization

### Response Type A

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": null,
  "timestamp": "..."
}
```

### Response Type B

Plain JSON objects or arrays returned directly from Flask `jsonify`.

### Client Requirement

The API client must normalize to:

```ts
type NormalizedApiResult<T> = {
  ok: boolean
  status: number
  data: T | null
  errorCode: string | null
  errorMessage: string | null
  meta?: Record<string, unknown> | null
  raw: unknown
}
```

## 8. Auth and Session State Machine

States:

- `anonymous`
- `registering`
- `otp_pending`
- `authenticated`
- `mfa_pending`
- `refreshing`
- `locked`
- `offline_safety`
- `expired`

Transitions:

1. register success -> `otp_pending`
2. OTP verify success -> `authenticated`
3. login with `mfa_required` -> `mfa_pending`
4. login success -> `authenticated`
5. token expiry online -> `refreshing`
6. refresh success -> `authenticated`
7. refresh failure online -> `expired`
8. refresh failure offline -> `offline_safety`
9. locked account response `423` -> `locked`

## 9. Offline and Sync State Machine

States:

- `online`
- `offline_readonly`
- `offline_pos_enabled`
- `syncing`
- `manual_review_required`

Triggers:

- network offline
- auth expiry while offline
- offline transaction threshold warnings
- server drift or conflict during replay

Rules:

- transactions replay FIFO only
- inventory last-write-wins only for stock updates, not transactions
- transaction replay conflicts go to resolution center
- config refresh occurs separately from transaction sync

## 10. Core Shared State Slices

### `authState`
- accessToken
- refreshToken
- userId
- storeId
- role
- mfaEnabled
- sessionMode

### `uiState`
- sidebarCollapsed
- rightDrawer
- modalStack
- lowEndMode
- activeToasts

### `cartState`
- cartId
- lineItems
- customerId
- paymentMode
- notes
- subtotal
- totalDiscount
- estimatedTax
- total
- locallyCalculatedAt

### `syncState`
- isOnline
- pendingTransactions
- pendingInventoryOps
- manualReviewItems
- lastSnapshotAt
- configVersion

### `settingsState`
- storeProfile
- categories
- taxConfig
- receiptTemplate
- whatsappConfig
- hardwarePrefs

## 11. Money and Tax Engine Rules

From the specs:

- currency default: INR
- precision: 2 display, 4 internal
- rounding: `HALF_UP`
- drift threshold: `0.05`
- slab mismatch is hard reject

Frontend implementation requirement:

- build all totals through `Decimal`
- never sum via JS `number`
- preserve raw line-item taxable values for comparison and replay

## 12. Runtime Configuration

Current config extracted from `Global-Sync-Configuration.json`:

- tax slabs fetched dynamically from `/api/v1/config/tax-slabs` in docs, but this endpoint is not present in inspected routes
- fallback slabs:
  - `0`
  - `5`
  - `12`
  - `18`
  - `28`
- offline:
  - unauthenticated POS false
  - `max_offline_txns: 500`
  - `max_offline_days: 3`
  - `warning_threshold: 400`
  - safety roles include `owner`, `admin`
- performance:
  - max render `16.6ms`
  - low-end RAM threshold `2048MB`

Frontend decision:

- implement a runtime config layer with local defaults, because the documented invariants endpoint does not currently exist in the inspected backend.

## 13. Hardware Integration Requirements

### Barcode Desktop Mode
- global key listener
- detect rapid input bursts
- ignore text-field leakage unless scanner focus mode is active
- auto-submit on Enter/Tab suffix

### Barcode Mobile Mode
- camera feed
- 3fps target
- torch toggle
- center guide box
- dimmed outer mask

### Printer
- queue print jobs through API
- show job polling status
- generate printable HTML/PDF fallback if printer unavailable

## 14. Screen Inventory

### A. Auth Stack

#### Register Screen
Sections:
- merchant identity form
- store setup form
- password requirements block
- CTA footer

Fields:
- mobile_number
- password
- full_name
- email
- store_name
- role

States:
- default
- submitting
- validation error
- duplicate mobile
- success -> OTP step

#### OTP Verify Screen
Sections:
- contact summary
- 6-digit segmented input
- resend timer
- alternate contact help

#### Login Screen
Sections:
- mobile/password form
- optional MFA step
- forgot-password link
- account locked state

#### Forgot Password Screen
- mobile number only

#### Reset Password Screen
- token
- new password

### B. Dashboard Stack

#### Dashboard Home
Required widgets:
- KPI cards
- alerts feed
- live signals list
- 7-day revenue chart
- payment mode breakdown
- top products today
- category breakdown
- insights cards

KPI card anatomy:
- title
- value
- delta
- inline icon arrow
- sparkline
- tap/hover affordance to open detail

#### Alerts Center
Data:
- dashboard alerts
- inventory alerts
- active incidents if enabled

Actions:
- acknowledge or dismiss if supported
- deep-link into source entity

#### Live Signals Rail
Fields:
- product
- region
- delta
- recommendation
- timestamp

### C. Analytics Stack

#### Revenue View
- date range controls
- day/week/month grouping
- area or bar chart
- moving average line
- summary cards

#### Profit View
- trend chart
- gross margin chip
- daily table

#### Contribution View
- Pareto chart
- SKU contribution table
- price-volume decomposition cards

#### Category Breakdown View
- donut chart
- legend table

#### Payment Mode View
- channel mix chart
- txn share and revenue share

#### Customer Summary View
- identified vs anonymous
- new vs returning
- avg revenue per customer

#### Diagnostics View
- deviation flag timeline
- rolling variance table
- margin drift warning card

### D. Inventory Stack

#### Inventory List
View types:
- dense table
- card grid

Controls:
- search by name/SKU/barcode
- category filter
- low-stock toggle
- slow-moving toggle
- active toggle
- pagination

Columns:
- image
- name
- SKU
- category
- stock
- reorder
- cost
- selling
- margin
- badges
- actions

#### Product Create/Edit
Form groups:
- identity
- pricing
- stock
- categorization
- supplier
- barcode/media

Warnings:
- selling below cost
- missing category
- inactive category usage

#### Product Detail
Tabs:
- overview
- price history
- stock movements
- linked supplier
- barcode data

#### Stock Intake Modal
Fields:
- quantity_added
- purchase_price
- date
- supplier_name
- update_cost_price

#### Stock Audit Screen
Structure:
- mode header
- product count list
- expected vs actual columns
- discrepancy summary
- submit confirmation

### E. POS Stack

#### POS Shell
Primary zones:
- scan/search bar
- product quick-add tray
- cart
- customer strip
- payment controls
- totals
- sync badge

Core behaviors:
- client-generated transaction UUID
- client-generated timestamp
- optimistic totals
- repeated scan increments quantity
- offline buffer enabled

#### Cart Line Item
- product name
- qty stepper
- unit price
- discount
- line subtotal
- remove

#### Checkout Footer
- subtotal
- discount
- tax estimate
- grand total
- payment mode chips
- place order CTA

#### Return Flow
- search by transaction ID
- fetch line items
- partial return selection
- reason entry
- confirmation summary

### F. Transactions Stack

#### Transactions List
Controls:
- date range
- payment mode
- customer
- min/max amount
- pagination

Rows:
- transaction ID
- created_at
- payment_mode
- customer
- return flag

#### Transaction Detail
Sections:
- header summary
- line items
- notes
- linked receipt/print actions

### G. Customers Stack

#### Customer List
- search by name/mobile
- created date filters
- create customer CTA
- loyalty and credit badges

#### Customer Profile
Sections:
- identity
- contact
- notes
- summary KPIs
- recent transactions

#### Customer Loyalty Tab
- points balance
- redeemable points
- lifetime earned
- recent loyalty transactions
- redeem action

#### Customer Credit Tab
- outstanding balance
- credit limit
- recent repayments and debits
- repayment action

### H. Pricing Stack

#### Suggestion Inbox
- sortable list of pending suggestions
- margin comparison
- confidence indicator
- apply/dismiss actions

#### Pricing Rules
- rules list
- create/update rule form
- active toggle

#### Pricing History
- price timeline
- table of old/new/reason/changed_by

### I. Supplier and Procurement Stack

#### Supplier List
- analytics cards in row:
  - fill rate
  - lead time
  - recent price change
- table/grid of suppliers

#### Supplier Profile
Sections:
- contact
- payment terms
- performance analytics
- sourced products
- recent purchase orders

#### Supplier Product Link Modal
Fields:
- product_id
- quoted_price
- lead_time_days
- is_preferred_supplier

#### Purchase Orders List
- status filter
- supplier filter if desired
- create PO

#### Purchase Order Detail
- supplier
- status
- expected delivery
- notes
- item lines
- send/receive/cancel actions

#### Receive PO Flow
- ordered vs received comparison
- received quantity inputs
- GRN notes
- fulfillment result

### J. Store and Settings Stack

#### Store Profile
Fields:
- store_name
- store_type
- city
- state
- gst_number
- currency_symbol
- working_days
- opening_time
- closing_time
- timezone

#### Categories
- create/edit/deactivate categories
- color tags
- GST rate chips
- active/inactive state

#### Tax Config
- bulk editor for category rates
- save summary

### K. GST Stack

#### GST Config
- gstin
- registration_type
- state_code
- is_gst_enabled

#### HSN Search
- search box
- results table
- apply-to-product shortcut

#### GST Summary
- period selector
- taxable, CGST, SGST, IGST totals
- invoice count
- status

#### GSTR1 Viewer
- period selector
- JSON viewer/download

#### Liability Slabs
- slab summary cards or table by rate

### L. Tax Engine Stack

#### Country Tax Config
- country selector
- tax registration card

#### Tax Calculator Preview
- input items
- country code
- taxable result
- tax amount
- breakdown

#### Filing Summary
- period
- country code
- invoice count
- pending status

### M. Finance Stack

#### Finance Dashboard
- cash on hand
- treasury balance
- total debt
- credit score

#### KYC
- business type
- tax ID
- document URL inputs or upload abstraction
- status tracker

#### Credit Score Detail
- radial gauge
- risk tier chip
- factors cards
- refresh score CTA

#### Accounts
- operating and reserve cards
- balances

#### Ledger
- account filter
- transaction table

#### Loans
- current applications
- amount/status/outstanding
- apply modal
- disburse action where appropriate

#### Treasury
- available balance
- yield
- sweep strategy form

### N. Payments Stack

#### Provider Picker
- provider code
- provider name
- supported methods

#### Payment Intent Creator
- transaction lookup
- provider selection
- phone number
- method

### O. Receipts and Barcodes Stack

#### Receipt Template
- header_text
- footer_text
- show_gstin
- paper_width_mm
- preview pane

#### Print Queue
- create print job
- poll status
- pending/completed/error badges

#### Barcode Lookup
- barcode input
- product result card

#### Barcode Registration
- product selector
- barcode value
- barcode type

### P. Vision Stack

#### OCR Upload
- drag/drop or capture
- file validation
- queued state

#### OCR Review
- parsed rows
- product match selectors
- quantity edits
- unit price edits
- confirm or dismiss

#### Shelf Scan
- live or uploaded image analysis result
- gaps or mismatch overlay summary

#### Receipt Digitization
- image upload
- extracted structured result

### Q. AI Assistant Stack

#### Assistant Panel
- chat transcript
- query input
- suggestion prompts
- recommendation side cards

#### Forecast Detail
- product selector
- forecast chart
- confidence display

#### Price Optimization
- product multi-select
- objective selection if enabled
- recommended price list

### R. Marketplace Stack

#### Search Marketplace
- filters:
  - query
  - category
  - price min/max
  - supplier rating
  - MOQ
  - sort

#### Recommendations
- procurement recommendation cards

#### RFQ Builder
- items array editor
- submit
- response comparison

#### Marketplace Orders
- list
- detail
- tracking

#### Supplier Onboarding
- business_name
- business_type
- categories
- payment_terms

### S. Staff Stack

#### Staff Session Widget
- start session
- current session status
- end session
- target revenue display

#### Staff Performance Overview
- owner only
- staff cards with:
  - today revenue
  - txn count
  - discount total
  - average discount percentage
  - target revenue
  - target achieved

#### Staff Detail
- 30-day history chart
- daily targets overlay

#### Staff Target Editor
- user
- target_date
- revenue_target
- transaction_count_target

### T. Events Stack

#### Events Calendar/List
- filter by date range
- event type display
- impact percentage
- recurrence fields

#### Event Create/Edit
Fields:
- event_name
- event_type
- start_date
- end_date
- expected_impact_pct
- is_recurring
- recurrence_rule

#### Upcoming Events
- horizon filter

#### Demand Sensing
- product selector
- event-aware forecast card

### U. WhatsApp Stack

#### WhatsApp Config
Fields:
- phone_number_id
- waba_id
- webhook_verify_token
- access_token
- is_active

#### Alert Send Flow
- choose alert
- send via WhatsApp

#### Purchase Order Send Flow
- choose PO
- resolve supplier phone
- queue message

#### Templates View
- template list

#### Message Log
- paginated log
- status badges

### V. Chain Operations Stack

#### Chain Group Creation
- name

#### Chain Dashboard
- total revenue today
- best store
- worst store
- total open alerts
- per-store table
- pending transfer suggestions

#### Store Comparison
- period switch: today/week/month
- relative-to-average labels

#### Transfer Suggestions
- list
- confirm action

### W. Internationalization Stack

#### Translation Catalog Loader
- locale selector
- module selector
- catalog prefetch

#### Currency Metadata
- supported currency list

#### Country Metadata
- supported countries
- locale defaults

## 15. Endpoint-to-Screen Mapping

### Auth
- `/api/v1/auth/register`
- `/api/v1/auth/verify-otp`
- `/api/v1/auth/resend-otp`
- `/api/v1/auth/login`
- `/api/v1/auth/mfa/setup`
- `/api/v1/auth/mfa/verify`
- `/api/v1/auth/refresh`
- `/api/v1/auth/logout`
- `/api/v1/auth/forgot-password`
- `/api/v1/auth/reset-password`

### Dashboard and Analytics
- `/api/v1/dashboard/overview`
- `/api/v1/dashboard/alerts`
- `/api/v1/dashboard/alerts/feed`
- `/api/v1/dashboard/live-signals`
- `/api/v1/dashboard/incidents/active`
- `/api/v1/analytics/revenue`
- `/api/v1/analytics/profit`
- `/api/v1/analytics/top-products`
- `/api/v1/analytics/category-breakdown`
- `/api/v1/analytics/contribution`
- `/api/v1/analytics/payment-modes`
- `/api/v1/analytics/customers/summary`
- `/api/v1/analytics/diagnostics`
- `/api/v1/analytics/dashboard`

### Inventory
- `/api/v1/inventory`
- `/api/v1/inventory/:productId`
- `/api/v1/inventory/:productId/stock`
- `/api/v1/inventory/audit`
- `/api/v1/inventory/:productId/price-history`
- `/api/v1/inventory/alerts`
- `/api/v1/inventory/alerts/:alertId`

### POS and Transactions
- `/api/v1/transactions`
- `/api/v1/transactions/batch`
- `/api/v1/transactions/:id`
- `/api/v1/transactions/:id/return`
- `/api/v1/transactions/summary/daily`

### Customers, Loyalty, Credit
- `/api/v1/customers`
- `/api/v1/customers/top`
- `/api/v1/customers/analytics`
- `/api/v1/customers/:id`
- `/api/v1/customers/:id/transactions`
- `/api/v1/customers/:id/summary`
- `/api/v1/loyalty/program`
- `/api/v1/loyalty/customers/:id/account`
- `/api/v1/loyalty/customers/:id/transactions`
- `/api/v1/loyalty/customers/:id/redeem`
- `/api/v1/credit/customers/:id/account`
- `/api/v1/credit/customers/:id/transactions`
- `/api/v1/credit/customers/:id/repay`
- `/api/v1/loyalty/analytics`

### Store and Pricing
- `/api/v1/store/profile`
- `/api/v1/store/categories`
- `/api/v1/store/categories/:categoryId`
- `/api/v1/store/tax-config`
- `/api/v1/pricing/suggestions`
- `/api/v1/pricing/suggestions/:id/apply`
- `/api/v1/pricing/suggestions/:id/dismiss`
- `/api/v1/pricing/history`
- `/api/v1/pricing/rules`

### Suppliers and POs
- `/api/v1/suppliers`
- `/api/v1/suppliers/:id`
- `/api/v1/suppliers/:id/products`
- `/api/v1/purchase-orders`
- `/api/v1/purchase-orders/:id`
- `/api/v1/purchase-orders/:id/send`
- `/api/v1/purchase-orders/:id/receive`
- `/api/v1/purchase-orders/:id/cancel`

### Finance and Payments
- `/api/v2/finance/kyc/submit`
- `/api/v2/finance/kyc/status`
- `/api/v2/finance/credit-score`
- `/api/v2/finance/credit-score/refresh`
- `/api/v2/finance/accounts`
- `/api/v2/finance/ledger`
- `/api/v2/finance/loans/apply`
- `/api/v2/finance/loans`
- `/api/v2/finance/loans/:loanId/disburse`
- `/api/v2/finance/payments/process`
- `/api/v2/finance/treasury/balance`
- `/api/v2/finance/treasury/sweep-config`
- `/api/v2/finance/dashboard`
- `/api/v1/payments/providers`
- `/api/v1/payments/intent`

### Receipts, Vision, AI
- `/api/v1/receipts/template`
- `/api/v1/receipts/print`
- `/api/v1/receipts/print/:jobId`
- `/api/v1/barcodes/lookup`
- `/api/v1/barcodes/register`
- `/api/v1/barcodes/list`
- `/api/v1/vision/ocr/upload`
- `/api/v1/vision/ocr/:jobId`
- `/api/v1/vision/ocr/:jobId/confirm`
- `/api/v1/vision/ocr/:jobId/dismiss`
- `/api/v1/vision/shelf-scan`
- `/api/v1/vision/receipt`
- `/api/v2/ai/forecast`
- `/api/v2/ai/pricing/optimize`
- `/api/v2/ai/vision/shelf-scan`
- `/api/v2/ai/vision/receipt`
- `/api/v2/ai/nlp/query`
- `/api/v2/ai/recommend`

### Marketplace, Staff, Events, WhatsApp, Chain, Offline, i18n
- `/api/v2/marketplace/*`
- `/api/v1/staff/*`
- `/api/v1/events*`
- `/api/v1/whatsapp/*`
- `/api/v1/chain/*`
- `/api/v1/offline/snapshot`
- `/api/v1/i18n/translations`
- `/api/v1/i18n/currencies`
- `/api/v1/i18n/countries`

## 16. Forms and Validation Catalog

### Product
- `name`: required, 1-255
- `uom`: `pieces | kg | litre | pack`
- `cost_price`: required number
- `selling_price`: required number, `>= cost_price` on create

### Transaction
- `transaction_id`: required UUID
- `timestamp`: required ISO datetime
- `payment_mode`: `CASH | UPI | CARD | CREDIT`
- `line_items`: at least 1

### Customer
- `mobile_number`: 10-15 digits
- `gender`: `male | female | other`

### Store Type
- `grocery | pharmacy | general | electronics | clothing | other`

### GST
- GSTIN validation enforced backend-side if provided

### Event Type
- `HOLIDAY | FESTIVAL | PROMOTION | SALE_DAY | CLOSURE`

### Loyalty
- minimum redemption threshold enforced by active program

## 17. Role and Permission Matrix

### Owner
- full access
- config updates
- inventory audits
- returns
- finance configuration
- WhatsApp config
- staff targets

### Staff
- POS
- own sessions
- likely limited transaction viewing
- no owner-only config actions

### Chain Owner
- chain dashboard
- transfer confirmation
- group management

Frontend requirement:

- hide unauthorized actions
- still handle backend `403`
- expose role badges and mode indicators

## 18. Real-Time Strategy

Docs mention websocket alerts, but backend implementation is placeholder-level.

Frontend strategy:

- abstraction with transports:
  - websocket preferred
  - polling fallback
- alert feed polling interval
- snackbar for incoming stock refresh rather than destructive auto-refresh

## 19. Canonical Frontend Decisions for Backend Inconsistencies

### Inventory list path
Use `/api/v1/inventory` as canonical.

### Checkout path
Use `/api/v1/transactions` as canonical create endpoint.

### Finance base path
Use `/api/v2/finance`.

### Marketplace base path
Use `/api/v2/marketplace`.

### Barcode list/register
Use actual implemented endpoints:
- `/api/v1/barcodes/register`
- `/api/v1/barcodes/list`

### Vision receipt/shelf scan
Prefer v2 AI namespace where image URLs are available.
Fallback to v1 multipart flows for local uploads.

### Runtime config
Because the documented invariants endpoint is absent, bootstrap from local config files and allow server override later.

## 20. Data Fixtures Needed Before UI Freeze

To fully validate the frontend, gather or generate fixtures for:

- zero-data store
- newly onboarded owner before OTP
- verified owner with empty inventory
- store with 100+ products
- low-stock and slow-moving alerts
- active loyalty program
- customer with credit ledger
- multiple staff users and targets
- purchase orders in DRAFT, SENT, FULFILLED, CANCELLED
- OCR job in QUEUED, REVIEW, APPLIED, FAILED
- finance accounts and loans
- WhatsApp configured and unconfigured
- chain group with multiple stores

## 21. Remaining Unknowns

These are the pieces the repo does not fully answer:

- exact pixel layout and spacing
- typography hierarchy beyond rough token guidance
- brand asset set and iconography
- precise websocket event contracts
- final mobile-specific navigation priorities
- whether some v1 and v2 duplicate endpoints are legacy or both expected
- exact tax invariant boot endpoint referenced in docs
- exact receipt rendering format expected by printers

## 22. Build Phases

### Phase 1
- auth
- app shell
- dashboard
- inventory
- transactions

### Phase 2
- POS
- customers
- pricing
- receipts
- suppliers and POs

### Phase 3
- finance
- GST and tax
- OCR and AI
- staff
- events

### Phase 4
- marketplace
- WhatsApp
- chain
- i18n
- offline conflict resolution center

## 23. Definition of “Frontend Complete”

A React frontend should be considered functionally complete when:

1. every inspected backend route has either a UI, a deliberate internal-only classification, or a documented exclusion
2. all owner/staff/chain-owner role gates are enforced
3. POS works online and offline with replay
4. all money math is decimal-safe
5. empty, loading, and failure states exist for each primary screen
6. long-running jobs such as OCR and print polling have observable state
7. duplicate backend contracts are normalized behind a single frontend API layer

## 24. Companion Docs

This master spec should be used with:

- [react-frontend-extraction.md](/D:/Files/Desktop/RetailIQ-Final-Workspace/RetailIQ/frontend-specs/react-frontend-extraction.md)
- [frontend-requirements-and-specs.txt](/D:/Files/Desktop/RetailIQ-Final-Workspace/RetailIQ/frontend-specs/frontend-requirements-and-specs.txt)
- [UI-Design-System.md](/D:/Files/Desktop/RetailIQ-Final-Workspace/RetailIQ/frontend-specs/UI-Design-System.md)
- [System-Integrity-Policy.md](/D:/Files/Desktop/RetailIQ-Final-Workspace/RetailIQ/frontend-specs/System-Integrity-Policy.md)

## 25. Final Assessment

Yes, this is enough to start building a serious full frontend in React.

No, it is still not enough for a perfect visual clone of an unseen original interface.

But it is now exhaustive enough for engineering:

- routes are mapped
- screens are enumerated
- forms are defined
- states are modeled
- business invariants are captured
- backend inconsistencies are called out with canonical frontend choices

The next meaningful step is no longer “more extraction.” It is either:

- generate typed frontend API contracts and route modules, or
- scaffold the React application itself from this master spec.
