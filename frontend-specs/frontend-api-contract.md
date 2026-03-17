# RetailIQ Frontend API Contract

This document defines the canonical API contract the frontend should use, based on the current backend implementation in this repository.

Purpose:

- give the React frontend one stable contract to code against
- normalize inconsistent backend response shapes
- pick canonical endpoints where specs and route handlers diverge
- document request, response, and error expectations per feature

## 1. Base Rules

### Base URLs

- V1 APIs: `/api/v1`
- V2 APIs: `/api/v2`

### Auth Header

Use:

```http
Authorization: Bearer <access_token>
```

### Canonical Response Normalization

The backend returns two patterns.

#### Pattern A: Standard envelope

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": null,
  "timestamp": "2026-03-17T00:00:00Z",
  "message": "optional"
}
```

#### Pattern B: Raw JSON

```json
{
  "score": 720,
  "tier": "PRIME"
}
```

### Frontend-Normalized Result

Frontend should normalize all calls to:

```ts
type ApiError = {
  code: string | null
  message: string | null
}

type ApiResult<T> = {
  ok: boolean
  status: number
  data: T | null
  error: ApiError | null
  meta: Record<string, unknown> | null
  raw: unknown
}
```

### Error Handling

Common statuses:

- `400` bad request
- `401` unauthorized
- `403` forbidden
- `404` not found
- `409` conflict
- `422` validation or business-rule error
- `423` account locked
- `429` rate limited
- `500` server error
- `503` service unavailable

## 2. Canonical Endpoint Decisions

Use these paths even where older docs differ:

- Inventory collection: `GET/POST /api/v1/inventory`
- Transactions create: `POST /api/v1/transactions`
- Finance module: `/api/v2/finance/*`
- Marketplace module: `/api/v2/marketplace/*`
- Barcode register: `POST /api/v1/barcodes/register`
- Barcode list: `GET /api/v1/barcodes/list`

## 3. Shared Types

### Money

Frontend should treat all currency values as decimal-safe strings or `Decimal` internally, even if backend returns JSON numbers.

```ts
type MoneyLike = number
```

### Pagination Meta

```ts
type PaginationMeta = {
  page: number
  page_size?: number
  limit?: number
  total: number
}
```

### Alert

```ts
type AlertItem = {
  id?: string
  alert_id?: number
  type?: string
  alert_type?: string
  severity?: "high" | "medium" | "low"
  priority?: string
  title?: string
  message: string
  source?: string
  product_id?: number
  timestamp?: string
  created_at?: string
  acknowledged?: boolean
  resolved?: boolean
}
```

## 4. Auth Contract

Base: `/api/v1/auth`

### POST `/register`

Request:

```ts
type RegisterRequest = {
  mobile_number: string
  password: string
  full_name: string
  email: string
  store_name?: string
  role?: "owner" | "staff"
}
```

Success:

```ts
type RegisterResponse = {
  message: string
}
```

Errors:

- `422 DUPLICATE_MOBILE`
- `422` validation errors

### POST `/verify-otp`

Request:

```ts
type VerifyOtpRequest = {
  mobile_number: string
  otp: string
}
```

Success:

```ts
type VerifyOtpResponse = {
  access_token: string
  refresh_token: string
  user_id: number
  role: string
  store_id: number | null
}
```

Errors:

- `422 INVALID_OTP`
- `404 USER_NOT_FOUND`

### POST `/resend-otp`

Request:

```ts
type ResendOtpRequest = {
  contact?: string
  mobile_number?: string
  purpose?: string
}
```

Success:

```ts
type ResendOtpResponse = {
  message: string
  contact: string
  otp_ttl: number
  resend_after: number
}
```

### POST `/login`

Request:

```ts
type LoginRequest = {
  mobile_number: string
  password: string
  mfa_code?: string
}
```

Success:

```ts
type LoginResponse =
  | {
      access_token: string
      refresh_token: string
      user_id: number
      role: string
      store_id: number | null
    }
  | {
      mfa_required: true
      message: string
    }
```

Errors:

- `401 INVALID_CREDENTIALS`
- `401 INVALID_MFA`
- `403 INACTIVE_ACCOUNT`
- `423 ACCOUNT_LOCKED`

### POST `/mfa/setup`

Request:

```ts
type MfaSetupRequest = {
  password: string
}
```

Success:

```ts
type MfaSetupResponse = {
  secret: string
  provisioning_uri: string
  message: string
}
```

### POST `/mfa/verify`

Request:

```ts
type MfaVerifyRequest = {
  mfa_code: string
}
```

Success:

```ts
type MfaVerifyResponse = {
  message: string
}
```

### POST `/refresh`

Request:

```ts
type RefreshRequest = {
  refresh_token: string
}
```

Success:

```ts
type RefreshResponse = {
  access_token: string
  refresh_token: string
}
```

Errors:

- `401 INVALID_TOKEN`
- `503 REDIS_UNAVAILABLE`

### DELETE `/logout`

Request:

```ts
type LogoutRequest = {
  refresh_token?: string
}
```

Success:

```ts
type LogoutResponse = {
  message: string
}
```

### POST `/forgot-password`

Request:

```ts
type ForgotPasswordRequest = {
  mobile_number: string
}
```

### POST `/reset-password`

Request:

```ts
type ResetPasswordRequest = {
  token: string
  new_password: string
}
```

## 5. Dashboard Contract

Base: `/api/v1/dashboard`

### GET `/overview`

Success:

```ts
type SparklinePoint = {
  timestamp: string
  value: number
}

type SparklineMetric = {
  metric: string
  points: SparklinePoint[]
}

type DashboardOverview = {
  sales: number
  sales_delta: string
  sales_sparkline: SparklineMetric
  gross_margin: number
  gross_margin_delta: string
  gross_margin_sparkline: SparklineMetric
  inventory_at_risk: number
  inventory_at_risk_delta: string
  inventory_at_risk_sparkline: SparklineMetric
  outstanding_pos: number
  outstanding_pos_delta: string
  outstanding_pos_sparkline: SparklineMetric
  loyalty_redemptions: number
  loyalty_redemptions_delta: string
  loyalty_redemptions_sparkline: SparklineMetric
  online_orders: number
  online_orders_delta: string
  online_orders_sparkline: SparklineMetric
  last_updated: string
}
```

### GET `/alerts`

Success:

```ts
type DashboardAlertsResponse = {
  alerts: AlertItem[]
  has_more: boolean
  next_cursor: string | null
}
```

### GET `/alerts/feed?limit=20`

Success same shape as `/alerts`.

### GET `/live-signals`

Success:

```ts
type LiveSignal = {
  id: string
  sku: string
  product_name: string
  delta: string
  region: string
  insight: string
  recommendation: string
  timestamp: string
}

type LiveSignalsResponse = {
  signals: LiveSignal[]
  last_updated: string
}
```

### GET `/incidents/active`

Success:

```ts
type ActiveIncident = {
  id: string
  title: string
  description: string
  severity: string
  status: string
  impacted_services: string[]
  created_at: string
  updated_at: string
  estimated_resolution: string
}
```

## 6. Analytics Contract

Base: `/api/v1/analytics`

### GET `/revenue`

Query:

```ts
type RevenueQuery = {
  start?: string
  end?: string
  group_by?: "day" | "week" | "month"
}
```

Response:

```ts
type RevenueRow = {
  date: string
  revenue: number
  profit: number
  transactions: number
  moving_avg_7d?: number
}
```

### GET `/profit`

```ts
type ProfitRow = {
  date: string
  profit: number
  revenue: number
  margin_pct: number
  moving_avg_7d?: number
}
```

### GET `/top-products`

Query:

```ts
type TopProductsQuery = {
  start?: string
  end?: string
  metric?: "revenue" | "quantity" | "profit"
  limit?: number
}
```

Response:

```ts
type TopProductRow = {
  rank: number
  product_id: number
  name: string
  revenue: number
  quantity: number
  profit: number
}
```

### GET `/category-breakdown`

```ts
type CategoryBreakdownRow = {
  category_id: number | null
  name: string
  revenue: number
  profit: number
  units: number
  share_pct: number
}
```

### GET `/contribution`

```ts
type ContributionSku = {
  product_id: number
  name: string
  revenue_current: number
  revenue_prior: number
  delta_revenue: number
  contribution: number
  is_pareto: boolean
  price_effect: number
  volume_effect: number
  profit_current: number
}

type ContributionSummary = {
  total_rev_current: number
  total_rev_prior: number
  total_rev_change: number
  period: { start: string; end: string }
  compare: { start: string; end: string }
}

type ContributionResponse = {
  skus: ContributionSku[]
  summary: ContributionSummary
}
```

### GET `/payment-modes`

```ts
type PaymentModeBreakdown = {
  mode: string
  txn_count: number
  revenue: number
  txn_share_pct: number
  rev_share_pct: number
}
```

### GET `/customers/summary`

```ts
type AnalyticsCustomersSummary = {
  identified_customers: number
  new_customers: number
  returning_customers: number
  total_transactions: number
  identified_transactions: number
  anonymous_transactions: number
  total_revenue: number
  avg_revenue_per_customer: number
}
```

### GET `/diagnostics`

```ts
type TrendDeviation = {
  date: string
  revenue: number
  moving_avg_7d: number
  deviation_pct: number
  flagged: boolean
}

type SkuRollingVariance = {
  product_id: number
  cv_14d: number | null
  cv_30d: number | null
}

type MarginDrift = {
  current_month_margin_pct: number
  prior_month_margin_pct: number
  drift_pp: number
  flagged: boolean
} | null

type DiagnosticsResponse = {
  trend_deviations: TrendDeviation[]
  sku_rolling_variance: SkuRollingVariance[]
  margin_drift: MarginDrift
}
```

### GET `/dashboard`

```ts
type AnalyticsDashboardResponse = {
  today_kpis: {
    date: string
    revenue: number
    profit: number
    transactions: number
    avg_basket: number
    units_sold: number
  }
  revenue_7d: Array<Record<string, unknown>>
  moving_avg_7d: Array<{ date: string; moving_avg: number }>
  alerts_summary: Record<string, number>
  top_products_today: Array<{
    product_id: number
    name: string
    revenue: number
    units_sold: number
  }>
  category_breakdown: Array<{
    category_name: string
    revenue: number
    percentage: number
  }>
  payment_mode_breakdown: Array<{
    mode: string
    count: number
    amount: number
  }>
  insights: Array<{
    type: string
    title: string
    body: string
  }>
}
```

## 7. Inventory Contract

Base: `/api/v1/inventory`

### Product Types

```ts
type Product = {
  product_id: number
  store_id: number
  category_id: number | null
  name: string
  sku_code: string | null
  uom: "pieces" | "kg" | "litre" | "pack" | null
  cost_price: number
  selling_price: number
  current_stock: number
  reorder_level: number
  supplier_name: string | null
  barcode: string | null
  image_url: string | null
  is_active: boolean
  lead_time_days: number
}
```

### GET `/`

Query:

```ts
type ListProductsQuery = {
  page?: number
  page_size?: number
  category_id?: number
  is_active?: boolean
  low_stock?: boolean
  slow_moving?: boolean
}
```

Response:

- `data: Product[]`
- `meta: { page, page_size, total }`

### POST `/`

Request:

```ts
type CreateProductRequest = {
  name: string
  category_id?: number | null
  sku_code?: string | null
  uom?: "pieces" | "kg" | "litre" | "pack" | null
  cost_price: number
  selling_price: number
  current_stock?: number
  reorder_level?: number
  supplier_name?: string | null
  barcode?: string | null
  image_url?: string | null
  lead_time_days?: number
  hsn_code?: string | null
}
```

Response:

- `data: Product`

Errors:

- `422` validation

### GET `/:productId`

Response:

- `data: Product`

### PUT `/:productId`

Request is partial `CreateProductRequest`, plus:

```ts
type UpdateProductRequest = Partial<CreateProductRequest> & {
  is_active?: boolean
}
```

### DELETE `/:productId`

Success:

```ts
type DeactivateProductResponse = {
  message: string
}
```

### POST `/:productId/stock`

Request:

```ts
type StockUpdateRequest = {
  quantity_added: number
  purchase_price: number
  date?: string
  supplier_name?: string
  update_cost_price?: boolean
}
```

Response:

- `data: Product`

### POST `/audit`

Request:

```ts
type StockAuditRequest = {
  items: Array<{
    product_id: number
    actual_qty: number
  }>
  notes?: string
}
```

Response:

```ts
type StockAuditResponse = {
  audit_id: number
  audit_date: string
  items: Array<{
    product_id: number
    expected_stock: number
    actual_stock: number
    discrepancy: number
  }>
}
```

### GET `/:productId/price-history`

```ts
type ProductPriceHistoryItem = {
  id: number
  cost_price: number | null
  selling_price: number | null
  changed_at: string | null
  changed_by: number | null
}
```

### GET `/alerts`

Response:

```ts
type InventoryAlert = {
  alert_id: number
  alert_type: string
  priority: string
  product_id: number | null
  message: string
  created_at: string | null
}
```

### DELETE `/alerts/:alertId`

Success:

```ts
type DismissAlertResponse = {
  message: string
}
```

## 8. Transactions Contract

Base: `/api/v1/transactions`

### Shared Types

```ts
type TransactionLineItemInput = {
  product_id: number
  quantity: number
  selling_price: number
  discount_amount?: number
}
```

### POST `/`

Request:

```ts
type CreateTransactionRequest = {
  transaction_id: string
  timestamp: string
  payment_mode: "CASH" | "UPI" | "CARD" | "CREDIT"
  customer_id?: number | null
  notes?: string | null
  line_items: TransactionLineItemInput[]
}
```

Response:

```ts
type CreateTransactionResponse = {
  transaction_id: string
}
```

Errors:

- `422` validation or business-rule errors
- `500` server error

### POST `/batch`

Request:

```ts
type BatchCreateTransactionsRequest = {
  transactions: CreateTransactionRequest[]
}
```

Response:

- implementation-defined object from batch processor
- frontend should treat as opaque and inspect success/failure counts

### GET `/`

Query:

```ts
type ListTransactionsQuery = {
  page?: number
  page_size?: number
  start_date?: string
  end_date?: string
  payment_mode?: string
  customer_id?: number
  min_amount?: number
  max_amount?: number
}
```

Response:

```ts
type TransactionListItem = {
  transaction_id: string
  created_at: string
  payment_mode: string
  customer_id: number | null
  is_return: boolean
}
```

### GET `/:id`

Response:

```ts
type TransactionDetail = {
  transaction_id: string
  created_at: string
  payment_mode: string
  customer_id: number | null
  notes: string | null
  is_return: boolean
  original_transaction_id: string | null
  line_items: Array<{
    product_id: number
    product_name: string | null
    quantity: number
    selling_price: number
    discount_amount: number
  }>
}
```

### POST `/:id/return`

Request:

```ts
type ReturnTransactionRequest = {
  items: Array<{
    product_id: number
    quantity_returned: number
    reason?: string | null
  }>
}
```

Response:

```ts
type ReturnTransactionResponse = {
  return_transaction_id: string
}
```

### GET `/summary/daily`

Query:

```ts
type DailySummaryQuery = {
  date?: string
}
```

Response:

- backend service-defined summary object
- frontend should not hardcode unknown fields without fixture confirmation

## 9. Customers, Loyalty, Credit Contract

Base: `/api/v1/customers`

### Customer

```ts
type Customer = {
  customer_id: number
  store_id: number
  name: string
  mobile_number: string
  email: string | null
  gender: "male" | "female" | "other" | null
  birth_date: string | null
  address: string | null
  notes: string | null
  created_at: string | null
}
```

### GET `/`

Query:

```ts
type ListCustomersQuery = {
  page?: number
  page_size?: number
  name?: string
  mobile?: string
  created_after?: string
  created_before?: string
}
```

### POST `/`

Request:

```ts
type CreateCustomerRequest = {
  name: string
  mobile_number: string
  email?: string | null
  gender?: "male" | "female" | "other" | null
  birth_date?: string | null
  address?: string | null
  notes?: string | null
}
```

Response:

- `data: Customer`

### GET `/:customerId`

- `data: Customer`

### PUT `/:customerId`

- partial `CreateCustomerRequest`

### GET `/:customerId/transactions`

Query:

```ts
type CustomerTransactionsQuery = {
  page?: number
  page_size?: number
  date_from?: string
  date_to?: string
  category_id?: number
  min_amount?: number
  max_amount?: number
}
```

Response:

```ts
type CustomerTransactionItem = {
  transaction_id: string
  created_at: string | null
  payment_mode: string
  notes: string | null
}
```

### GET `/:customerId/summary`

- response is service-defined summary object

### GET `/top`

```ts
type TopCustomersQuery = {
  metric?: "revenue" | "visits"
  limit?: number
}
```

### GET `/analytics`

- service-defined analytics object

### Loyalty Program

Base: `/api/v1/loyalty`

#### GET `/program`

```ts
type LoyaltyProgram = {
  points_per_rupee: number
  redemption_rate: number
  min_redemption_points: number
  expiry_days: number
  is_active: boolean
}
```

#### PUT `/program`

- request shape comes from schema-backed upsert
- frontend should submit partial/full program settings in same shape as `LoyaltyProgram`

#### GET `/customers/:customerId/account`

```ts
type LoyaltyAccount = {
  total_points: number
  redeemable_points: number
  lifetime_earned: number
  last_activity_at: string | null
  recent_transactions: Array<{
    type: string
    points: number
    balance_after: number
    created_at: string
    notes: string | null
  }>
}
```

#### GET `/customers/:customerId/transactions`

```ts
type LoyaltyTransactionItem = {
  id: string
  type: string
  points: number
  balance_after: number
  created_at: string
  notes: string | null
}
```

#### POST `/customers/:customerId/redeem`

Request:

```ts
type RedeemPointsRequest = {
  points_to_redeem: number
  transaction_id?: string | null
}
```

Response:

```ts
type RedeemPointsResponse = {
  message: string
  remaining_points: number
}
```

#### GET `/analytics`

```ts
type LoyaltyAnalytics = {
  enrolled_customers: number
  points_issued_this_month: number
  points_redeemed_this_month: number
  redemption_rate_this_month: number
}
```

### Credit

Base: `/api/v1/credit`

#### GET `/customers/:customerId/account`

```ts
type CreditAccount = {
  balance: number
  credit_limit: number
  updated_at: string | null
  recent_transactions: Array<{
    type: string
    amount: number
    balance_after: number
    created_at: string
    notes: string | null
  }>
}
```

#### GET `/customers/:customerId/transactions`

```ts
type CreditTransactionItem = {
  id: string
  type: string
  amount: number
  balance_after: number
  created_at: string
  notes: string | null
}
```

#### POST `/customers/:customerId/repay`

Request:

```ts
type RepayCreditRequest = {
  amount: number
  notes?: string | null
}
```

Response:

```ts
type RepayCreditResponse = {
  message: string
  remaining_balance: number
}
```

## 10. Store Contract

Base: `/api/v1/store`

### Store Profile

```ts
type StoreProfile = {
  store_id: number
  owner_user_id: number
  store_name?: string
  store_type?: "grocery" | "pharmacy" | "general" | "electronics" | "clothing" | "other"
  city?: string
  state?: string
  gst_number?: string
  currency_symbol?: string
  working_days?: Record<string, boolean>
  opening_time?: string
  closing_time?: string
  timezone?: string
}
```

### GET `/profile`

- `data: StoreProfile`

### PUT `/profile`

- partial `StoreProfile`

### Categories

```ts
type Category = {
  category_id: number
  store_id: number
  name: string
  color_tag: string | null
  is_active: boolean
  gst_rate: number
}
```

#### GET `/categories`

- `data: Category[]`

#### POST `/categories`

```ts
type CreateCategoryRequest = {
  name: string
  color_tag?: string | null
  is_active?: boolean
  gst_rate?: number
}
```

#### PUT `/categories/:categoryId`

- partial `CreateCategoryRequest`

#### DELETE `/categories/:categoryId`

Response:

```ts
type CategoryDeleteResponse = {
  message: string
}
```

### Tax Config

#### GET `/tax-config`

```ts
type StoreTaxConfigResponse = {
  taxes: Array<{
    category_id: number
    name: string
    gst_rate: number
  }>
}
```

#### PUT `/tax-config`

```ts
type UpdateStoreTaxConfigRequest = {
  taxes: Array<{
    category_id: number
    gst_rate: number
  }>
}
```

## 11. Pricing Contract

Base: `/api/v1/pricing`

### GET `/suggestions`

```ts
type PricingSuggestion = {
  id: number
  product_id: number
  product_name: string
  current_price: number | null
  suggested_price: number | null
  price_change_pct: number | null
  suggestion_type: string
  reason: string
  confidence: number | null
  confidence_score: number
  status: string
  created_at: string | null
  current_margin_pct: number | null
  suggested_margin_pct: number | null
}
```

### POST `/suggestions/:suggestionId/apply`

```ts
type ApplyPricingSuggestionResponse = {
  suggestion_id: number
  product_id: number
  old_price: number | null
  new_price: number
  status: "APPLIED"
}
```

### POST `/suggestions/:suggestionId/dismiss`

```ts
type DismissPricingSuggestionResponse = {
  suggestion_id: number
  status: "DISMISSED"
}
```

### GET `/history?product_id=...`

```ts
type PricingHistoryItem = {
  id: number
  product_id: number
  store_id: number
  old_price: number | null
  new_price: number | null
  reason: string | null
  changed_at: string | null
  changed_by: number | null
}
```

### GET `/rules`

```ts
type PricingRule = {
  id: number
  store_id: number
  rule_type: string
  parameters: Record<string, unknown>
  is_active: boolean
  created_at: string | null
}
```

### PUT `/rules`

```ts
type UpsertPricingRuleRequest = {
  rule_type: string
  parameters?: Record<string, unknown>
  is_active?: boolean
}
```

## 12. Suppliers and Purchase Orders Contract

### Suppliers

Base: `/api/v1/suppliers`

```ts
type SupplierListItem = {
  id: string
  name: string
  contact_name: string | null
  email: string | null
  phone: string | null
  payment_terms_days: number | null
  avg_lead_time_days: number | null
  fill_rate_90d: number
  price_change_6m_pct: number | null
}
```

#### POST `/`

```ts
type CreateSupplierRequest = {
  name: string
  contact_name?: string
  phone?: string
  email?: string
  address?: string
  payment_terms_days?: number
}
```

#### GET `/:supplierId`

```ts
type SupplierDetail = {
  id: string
  name: string
  contact: {
    name: string | null
    phone: string | null
    email: string | null
    address: string | null
  }
  payment_terms_days: number | null
  is_active: boolean
  analytics: {
    avg_lead_time_days: number | null
    fill_rate_90d: number
  }
  sourced_products: Array<{
    product_id: number
    name: string
    quoted_price: number
    lead_time_days: number | null
  }>
  recent_purchase_orders: Array<{
    id: string
    status: string
    expected_delivery_date: string | null
    created_at: string
  }>
}
```

#### PUT `/:supplierId`

- partial create request plus `is_active?: boolean`

#### DELETE `/:supplierId`

- soft delete

#### POST `/:supplierId/products`

```ts
type LinkSupplierProductRequest = {
  product_id: number
  quoted_price: number
  lead_time_days?: number
  is_preferred_supplier?: boolean
}
```

### Purchase Orders

Base: `/api/v1/purchase-orders`

#### GET `/`

```ts
type PurchaseOrderListItem = {
  id: string
  supplier_id: string
  status: string
  expected_delivery_date: string | null
  created_at: string
}
```

#### POST `/`

```ts
type CreatePurchaseOrderRequest = {
  supplier_id: string
  expected_delivery_date?: string
  notes?: string
  items: Array<{
    product_id: number
    ordered_qty: number
    unit_price: number
  }>
}
```

#### GET `/:poId`

```ts
type PurchaseOrderDetail = {
  id: string
  supplier_id: string
  status: string
  expected_delivery_date: string | null
  notes: string | null
  created_at: string
  items: Array<{
    product_id: number
    ordered_qty: number
    received_qty: number
    unit_price: number
  }>
}
```

#### POST or PUT `/:poId/send`

```ts
type SendPurchaseOrderResponse = {
  id: string
}
```

#### POST `/:poId/receive`

```ts
type ReceivePurchaseOrderRequest = {
  notes?: string
  items: Array<{
    product_id: number
    received_qty: number
  }>
}
```

Response:

```ts
type ReceivePurchaseOrderResponse = {
  id: string
  status: string
}
```

#### PUT `/:poId/cancel`

```ts
type CancelPurchaseOrderResponse = {
  id: string
}
```

## 13. Finance Contract

Base: `/api/v2/finance`

### KYC

#### POST `/kyc/submit`

```ts
type SubmitKycRequest = {
  business_type?: string
  tax_id?: string
  document_urls?: Record<string, string>
}
```

```ts
type SubmitKycResponse = {
  message: string
  status: string
}
```

#### GET `/kyc/status`

```ts
type KycStatusResponse = {
  status: string
  tax_id?: string
  updated_at?: string | null
}
```

### Credit Score

#### GET `/credit-score`

```ts
type MerchantCreditScore = {
  score: number
  tier: string
  factors: Record<string, unknown>
  last_updated: string
}
```

#### POST `/credit-score/refresh`

```ts
type RefreshCreditScoreResponse = {
  message: string
  score: number
}
```

### Accounts

#### GET `/accounts`

```ts
type FinancialAccount = {
  id: number
  type: string
  balance: number
}
```

### Ledger

#### GET `/ledger`

```ts
type LedgerEntry = {
  id: number
  txn_id: string
  account_id: number
  type: string
  amount: number
  description: string | null
  created_at: string
}
```

### Loans

#### POST `/loans/apply`

```ts
type ApplyLoanRequest = {
  product_id: number
  amount: number
  term_days: number
}
```

```ts
type ApplyLoanResponse = {
  message: string
  application_id: number
  status: string
}
```

#### GET `/loans`

```ts
type LoanItem = {
  id: number
  amount: number
  status: string
  applied_at: string
  outstanding: number
}
```

#### POST `/loans/:loanId/disburse`

```ts
type DisburseLoanResponse = {
  message: string
  ledger_txn_id: string
}
```

### Payments

#### POST `/payments/process`

```ts
type ProcessMerchantPaymentRequest = {
  amount: number
  payment_method?: string
}
```

```ts
type ProcessMerchantPaymentResponse = {
  payment_id: number
  status: string
  net_amount: number
  fees: number
}
```

### Treasury

#### GET `/treasury/balance`

```ts
type TreasuryBalance = {
  available: number
  yield_bps: number
  currency: string
}
```

#### PUT `/treasury/sweep-config`

```ts
type UpdateSweepConfigRequest = {
  strategy: string
  min_balance?: number
}
```

```ts
type UpdateSweepConfigResponse = {
  message: string
  active: boolean
}
```

### Dashboard

#### GET `/dashboard`

```ts
type FinanceDashboard = {
  cash_on_hand: number
  treasury_balance: number
  total_debt: number
  credit_score: number
}
```

## 14. Payments Contract

Base: `/api/v1/payments`

### GET `/providers`

```ts
type PaymentProviderItem = {
  code: string
  name: string
  type: string
  supported_methods: unknown
}
```

### POST `/intent`

```ts
type CreatePaymentIntentRequest = {
  transaction_id: string
  provider_code: string
  phone_number?: string
  method?: string
}
```

Response:

- adapter-defined payload
- frontend should treat provider response as opaque and pass to provider-handling UI

## 15. Receipts and Barcode Contract

### Receipts

Base: `/api/v1/receipts`

#### GET `/template`

```ts
type ReceiptTemplate = {
  id: number | null
  store_id: number
  header_text: string
  footer_text: string
  show_gstin: boolean
  paper_width_mm: number
  updated_at: string | null
}
```

#### PUT `/template`

```ts
type UpdateReceiptTemplateRequest = {
  header_text?: string
  footer_text?: string
  show_gstin?: boolean
  paper_width_mm?: number
}
```

#### POST `/print`

```ts
type CreatePrintJobRequest = {
  transaction_id?: string
  printer_mac_address?: string
}
```

```ts
type CreatePrintJobResponse = {
  job_id: number
}
```

#### GET `/print/:jobId`

```ts
type PrintJobStatus = {
  job_id: number
  store_id: number
  transaction_id: string | null
  job_type: string
  status: string
  created_at: string | null
  completed_at: string | null
}
```

### Barcodes

Base: `/api/v1/barcodes`

#### GET `/lookup?value=...`

```ts
type BarcodeLookupResponse = {
  barcode_value: string
  barcode_type: string
  product_id: number
  product_name: string
  current_stock: number
  price: number
}
```

#### POST `/register`

```ts
type RegisterBarcodeRequest = {
  product_id: number
  barcode_value: string
  barcode_type?: string
}
```

```ts
type RegisterBarcodeResponse = {
  id: number
  product_id: number
  store_id: number
  barcode_value: string
  barcode_type: string
  created_at: string | null
}
```

#### GET `/list?product_id=...`

```ts
type BarcodeListItem = {
  id: number
  barcode_value: string
  barcode_type: string
  created_at: string | null
}
```

## 16. Vision Contract

Base: `/api/v1/vision`

### POST `/ocr/upload`

Multipart:

- field: `invoice_image`

Response:

```ts
type OcrUploadResponse = {
  job_id: string
}
```

Errors:

- `400` no file
- `413` too large
- `415` unsupported media

### GET `/ocr/:jobId`

```ts
type OcrJobStatus = {
  job_id: string
  status: string
  error_message: string | null
  items: Array<{
    item_id: string
    raw_text: string | null
    matched_product_id: number | null
    product_name: string | null
    confidence: number | null
    quantity: number | null
    unit_price: number | null
    is_confirmed: boolean
  }>
}
```

### POST `/ocr/:jobId/confirm`

```ts
type ConfirmOcrJobRequest = {
  confirmed_items: Array<{
    item_id: string
    quantity: number
    matched_product_id: number
    unit_price?: number
  }>
}
```

```ts
type ConfirmOcrJobResponse = {
  message: string
}
```

### POST `/ocr/:jobId/dismiss`

```ts
type DismissOcrJobResponse = {
  message: string
}
```

### POST `/shelf-scan`

```ts
type ShelfScanRequest = {
  image_url: string
  model_type?: string
}
```

Response:

- backend-defined scan result object

### POST `/receipt`

Multipart:

- field: `receipt_image`

Response:

- backend-defined digitized receipt object

## 17. AI Contract

Base: `/api/v2/ai`

### POST `/forecast`

```ts
type ForecastRequest = {
  product_id: number
}
```

Response:

- forecast engine-defined result object

### POST `/pricing/optimize`

```ts
type PricingOptimizeRequest = {
  product_ids: number[]
}
```

Response:

- pricing engine-defined optimization result

### POST `/nlp/query`

```ts
type NlpQueryRequest = {
  query: string
}
```

```ts
type NlpQueryResponse = {
  response: unknown
}
```

### POST `/recommend`

```ts
type AiRecommendRequest = {
  user_id?: number
}
```

```ts
type AiRecommendResponse = {
  recommendations: unknown
}
```

### POST `/vision/shelf-scan`

```ts
type AiShelfScanRequest = {
  image_url: string
}
```

### POST `/vision/receipt`

```ts
type AiReceiptRequest = {
  image_url: string
}
```

## 18. Marketplace Contract

Base: `/api/v2/marketplace`

### GET `/search`

Query:

```ts
type MarketplaceSearchQuery = {
  query?: string
  category?: string
  price_min?: number
  price_max?: number
  supplier_rating_min?: number
  moq_max?: number
  sort_by?: string
  page?: number
}
```

Response:

- service-defined result object

### GET `/recommendations`

```ts
type MarketplaceRecommendationsQuery = {
  category?: string
  urgency?: string
}
```

### POST `/rfq`

```ts
type CreateRfqRequest = {
  items: unknown[]
}
```

### GET `/rfq/:rfqId`

```ts
type RfqDetail = {
  id: number
  items: unknown[]
  status: string
  matched_suppliers_count: number
  created_at: string
  responses: Array<{
    id: number
    supplier_profile_id: number
    quoted_items: unknown
    total_price: number
    delivery_days: number
    status: string
  }>
}
```

### POST `/orders`

```ts
type CreateMarketplaceOrderRequest = {
  supplier_id: number
  items: unknown[]
  payment_terms?: string
  finance_requested?: boolean
}
```

### GET `/orders`

```ts
type MarketplaceOrderListResponse = {
  orders: Array<{
    id: number
    order_number: string
    supplier_profile_id: number
    status: string
    total: number
    payment_status: string
    financed: boolean
    created_at: string
    expected_delivery: string | null
  }>
  total: number
  page: number
  pages: number
}
```

### GET `/orders/:orderId`

```ts
type MarketplaceOrderDetail = {
  id: number
  order_number: string
  supplier_profile_id: number
  status: string
  subtotal: number
  tax: number
  shipping_cost: number
  total: number
  payment_status: string
  financed: boolean
  loan_id: number | null
  created_at: string
  expected_delivery: string | null
  shipping_tracking: unknown
  items: Array<{
    catalog_item_id: number
    quantity: number
    unit_price: number
    subtotal: number
  }>
}
```

### GET `/orders/:orderId/track`

```ts
type MarketplaceTrackingResponse = {
  status: string
  tracking_events: unknown[]
  estimated_delivery?: string | null
  logistics_provider?: string | null
}
```

## 19. Staff Contract

Base: `/api/v1/staff`

### POST `/sessions/start`

```ts
type StartStaffSessionResponse = {
  session_id: string
}
```

### POST `/sessions/end`

```ts
type EndStaffSessionResponse = {
  message: string
}
```

### GET `/sessions/current`

```ts
type CurrentStaffSession =
  | {
      active: false
    }
  | {
      active: true
      session_id: string
      started_at: string
      target_revenue: number | null
    }
```

### GET `/performance`

```ts
type StaffPerformanceItem = {
  user_id: number
  name: string
  today_revenue: number
  today_transaction_count: number
  today_discount_total: number
  avg_discount_pct: number
  target_revenue: number | null
  target_pct_achieved: number | null
}
```

### GET `/performance/:userId`

```ts
type StaffPerformanceDetail = {
  user_id: number
  name: string
  history: Array<{
    date: string
    revenue: number
    transaction_count: number
    target_revenue: number | null
    target_pct_achieved: number | null
  }>
}
```

### PUT or POST `/targets`

```ts
type UpsertStaffTargetRequest = {
  user_id: number
  target_date: string
  revenue_target?: number
  transaction_count_target?: number
}
```

## 20. Events Contract

Base: `/api/v1/events`

### GET `/`

Query:

```ts
type ListEventsQuery = {
  from?: string
  to?: string
}
```

```ts
type BusinessEventItem = {
  id: string
  event_name: string
  event_type: string
  start_date: string | null
  end_date: string | null
  expected_impact_pct: number | null
  is_recurring: boolean
  recurrence_rule: string | null
}
```

### POST `/`

```ts
type CreateEventRequest = {
  event_name: string
  event_type: "HOLIDAY" | "FESTIVAL" | "PROMOTION" | "SALE_DAY" | "CLOSURE"
  start_date: string
  end_date: string
  expected_impact_pct?: number | null
  is_recurring?: boolean
  recurrence_rule?: string | null
}
```

### PUT `/:eventId`

- partial `CreateEventRequest`

### DELETE `/:eventId`

```ts
type DeleteEventResponse = {
  status: "DELETED"
}
```

### GET `/upcoming`

```ts
type UpcomingEventsQuery = {
  days?: number
}
```

### GET `/forecasting/demand-sensing/:productId`

Response:

- forecast engine-defined result

## 21. WhatsApp Contract

Base: `/api/v1/whatsapp`

### GET `/config`

```ts
type WhatsAppConfigResponse = {
  is_active: boolean
  phone_number_id: string | null
  waba_id: string | null
  configured: boolean
}
```

### PUT `/config`

```ts
type UpdateWhatsAppConfigRequest = {
  phone_number_id?: string
  waba_id?: string
  webhook_verify_token?: string
  access_token?: string
  is_active?: boolean
}
```

### POST `/send-alert`

```ts
type SendAlertWhatsAppRequest = {
  alert_id: number
}
```

```ts
type SendAlertWhatsAppResponse = {
  message: string
  message_id: number
}
```

### POST `/send-po`

```ts
type SendPurchaseOrderWhatsAppRequest = {
  po_id: string
}
```

```ts
type SendPurchaseOrderWhatsAppResponse = {
  message: string
  message_id: number
}
```

### GET `/templates`

```ts
type WhatsAppTemplateItem = {
  id: number
  name: string
  category: string
  language: string
  status: string
}
```

### GET `/message-log`

```ts
type WhatsAppMessageLogItem = {
  id: number
  message_type: string
  recipient: string
  status: string
  sent_at: string | null
}
```

## 22. Chain Contract

Base: `/api/v1/chain`

### POST `/groups`

```ts
type CreateStoreGroupRequest = {
  name: string
}
```

```ts
type CreateStoreGroupResponse = {
  group_id: string
  name: string
}
```

### POST `/groups/:groupId/stores`

```ts
type AddStoreToGroupRequest = {
  store_id: number
  manager_user_id?: number
}
```

### GET `/dashboard`

```ts
type ChainDashboard = {
  total_revenue_today: number
  best_store: {
    store_id: number
    name: string
    revenue: number
    transaction_count: number
    alert_count: number
  } | null
  worst_store: {
    store_id: number
    name: string
    revenue: number
    transaction_count: number
    alert_count: number
  } | null
  total_open_alerts: number
  per_store_today: Array<{
    store_id: number
    name: string
    revenue: number
    transaction_count: number
    alert_count: number
  }>
  transfer_suggestions: Array<{
    id: string
    from_store: number
    to_store: number
    product: number
    qty: number
    reason: string
  }>
}
```

### GET `/compare`

```ts
type ChainCompareItem = {
  store_id: number
  revenue: number
  profit: number
  relative_to_avg: "above" | "below" | "near"
}
```

### GET `/transfers`

```ts
type ChainTransferItem = {
  id: string
  from_store: number
  to_store: number
  product: number
  qty: number
  reason: string
  status: string
}
```

### POST `/transfers/:transferId/confirm`

```ts
type ConfirmChainTransferResponse = {
  message: string
  id: string
}
```

## 23. Offline Snapshot Contract

Base: `/api/v1/offline`

### GET `/snapshot`

Success:

```ts
type OfflineSnapshotResponse = {
  built_at: string | null
  size_bytes: number
  snapshot: unknown
}
```

Special:

- `202` means snapshot build in progress

## 24. GST Contract

Base: `/api/v1/gst`

### GET `/config`

```ts
type GstConfig = {
  gstin: string | null
  registration_type: string
  state_code: string | null
  is_gst_enabled: boolean
}
```

### PUT `/config`

```ts
type UpdateGstConfigRequest = {
  gstin?: string | null
  registration_type?: string
  state_code?: string | null
  is_gst_enabled?: boolean
}
```

### GET `/hsn-search?q=...`

```ts
type HsnSearchResult = {
  hsn_code: string
  description: string
  default_gst_rate: number | null
}
```

### GET `/summary?period=YYYY-MM`

```ts
type GstSummary = {
  period: string
  total_taxable: number
  total_cgst: number
  total_sgst: number
  total_igst: number
  invoice_count: number
  status: string
  compiled_at: string | null
}
```

### GET `/gstr1?period=YYYY-MM`

- returns compiled GSTR-1 JSON payload

### GET `/liability-slabs?period=YYYY-MM`

```ts
type GstLiabilitySlab = {
  rate: number
  taxable_value: number
  tax_amount: number
}
```

## 25. Tax Engine Contract

Base: `/api/v1/tax`

### GET `/config`

```ts
type TaxEngineConfig = {
  tax_id: string | null
  registration_type: string
  state_province?: string | null
  is_tax_enabled: boolean
}
```

### POST `/calculate`

```ts
type TaxCalculateRequest = {
  country_code?: string
  items: unknown[]
}
```

```ts
type TaxCalculateResponse = {
  taxable_amount: number
  tax_amount: number
  breakdown: Record<string, number>
}
```

### GET `/filing-summary?period=YYYY-MM`

```ts
type TaxFilingSummary = {
  period: string
  country_code: string
  total_taxable: number
  total_tax: number
  invoice_count: number
  status: string
  compiled_at: string | null
}
```

## 26. i18n Contract

Base: `/api/v1`

### GET `/i18n/translations`

```ts
type GetTranslationsQuery = {
  locale?: string
  module?: string
}
```

```ts
type TranslationCatalogResponse = {
  locale: string
  catalog: Record<string, string>
}
```

### GET `/i18n/currencies`

```ts
type SupportedCurrency = {
  code: string
  name: string
  symbol: string
  decimal_places: number
  symbol_position: string
}
```

### GET `/i18n/countries`

```ts
type SupportedCountry = {
  code: string
  name: string
  default_currency: string
  default_locale: string
  timezone: string
  phone_code: string
  date_format: string
}
```

## 27. Known Opaque or Service-Defined Payloads

These endpoints exist, but their full payload shape is delegated to engine/service functions not fully enumerated here:

- AI forecast responses
- AI pricing optimize responses
- NLP/assistant responses
- offline snapshot `snapshot`
- analytics dashboard `revenue_7d` internals
- daily transaction summary internals
- marketplace search/recommendation service outputs
- shelf scan and receipt digitization result payloads
- demand-sensing result payloads

Frontend guidance:

- wrap these in typed `unknown` or narrow them only after fixture capture
- avoid premature rigid TypeScript interfaces until real payload samples are collected

## 28. Recommended Next Artifact

This contract is enough to generate:

- a `src/api/types.ts`
- per-domain `src/api/*.ts` clients
- Zod validators for critical requests
- TanStack Query hooks

Companion docs:

- [frontend-master-spec.md](/D:/Files/Desktop/RetailIQ-Final-Workspace/RetailIQ/frontend-specs/frontend-master-spec.md)
- [react-frontend-extraction.md](/D:/Files/Desktop/RetailIQ-Final-Workspace/RetailIQ/frontend-specs/react-frontend-extraction.md)
