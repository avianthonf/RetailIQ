# RetailIQ — Frontend API Guide

> **Base URL**: `http://<host>:5000/api/v1`
> **Content-Type**: `application/json`
> **Authentication**: Bearer token (JWT RS256)

---

## Table of Contents

1. [Response Format](#response-format)
2. [Authentication](#1-authentication)
3. [Store Management](#2-store-management)
4. [Inventory & Products](#3-inventory--products)
5. [Transactions](#4-transactions)
6. [Customers](#5-customers)
7. [Analytics](#6-analytics)
8. [Forecasting](#7-forecasting)
9. [AI Recommendations](#8-ai-recommendations)
10. [Natural Language Query](#9-natural-language-query)
11. [System](#10-system)
12. [Error Codes Reference](#error-codes-reference)

---

## Response Format

All endpoints return a consistent JSON envelope:

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": { ... }
}
```

On error:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description"
  }
}
```

> **Note**: Store module uses a slightly different envelope (`status`/`message`/`data`). Both will be documented per endpoint.

---

## 1. Authentication

**Prefix**: `/api/v1/auth`

Authentication uses **JWT RS256** tokens. The access token is short-lived (include in `Authorization: Bearer <token>` header) and the refresh token is stored server-side in Redis.

### POST `/auth/register`

Register a new user + optionally create a store.

**Body**:

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `mobile_number` | string | ✅ | 10–15 chars | Unique per user |
| `password` | string | ✅ | min 6 chars | |
| `full_name` | string | ✅ | 2–100 chars | |
| `store_name` | string | ❌ | max 100 chars | Auto-generated if role=owner |
| `email` | string | ❌ | Valid email | |
| `role` | string | ❌ | `owner` or `staff` | Default: `owner` |

**Response** `201`:

```json
{
  "success": true,
  "data": { "message": "OTP sent successfully." }
}
```

**Errors**: `400` VALIDATION_ERROR, `400` DUPLICATE_MOBILE

---

### POST `/auth/verify-otp`

Verify the OTP sent during registration to activate the account.

**Body**:

| Field | Type | Required | Validation |
|---|---|---|---|
| `mobile_number` | string | ✅ | 10–15 chars |
| `otp` | string | ✅ | Exactly 6 chars |

**Response** `200`:

```json
{
  "success": true,
  "data": { "message": "Account verified successfully." }
}
```

**Errors**: `400` INVALID_OTP, `404` USER_NOT_FOUND

---

### POST `/auth/login`

Login with mobile number and password. Rate-limited to **5 attempts per 15 minutes** per mobile number.

**Body**:

| Field | Type | Required |
|---|---|---|
| `mobile_number` | string | ✅ |
| `password` | string | ✅ |

**Response** `200`:

```json
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "a1b2c3...",
    "user_id": 1,
    "role": "owner",
    "store_id": 1
  }
}
```

**Errors**: `401` INVALID_CREDENTIALS, `403` INACTIVE_ACCOUNT

---

### POST `/auth/refresh`

Exchange a valid refresh token for a new access + refresh token pair. The old refresh token is invalidated (rotation).

**Body**:

| Field | Type | Required |
|---|---|---|
| `refresh_token` | string | ✅ |

**Response** `200`:

```json
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "new_token..."
  }
}
```

**Errors**: `401` INVALID_TOKEN, `401` UNAUTHORIZED

---

### DELETE `/auth/logout`

🔒 **Requires**: `Authorization: Bearer <access_token>`

Invalidate the refresh token.

**Body** (optional):

| Field | Type | Required |
|---|---|---|
| `refresh_token` | string | ❌ |

**Response** `200`:

```json
{ "success": true, "data": { "message": "Logged out successfully" } }
```

---

### POST `/auth/forgot-password`

Request a password reset token (sent via mobile/email). Always returns 200 regardless of whether the user exists.

**Body**:

| Field | Type | Required |
|---|---|---|
| `mobile_number` | string | ✅ |

**Response** `200`:

```json
{ "success": true, "data": { "message": "If registered, a reset link/token will be generated." } }
```

---

### POST `/auth/reset-password`

Reset password using a valid reset token.

**Body**:

| Field | Type | Required | Validation |
|---|---|---|---|
| `token` | string | ✅ | From forgot-password flow |
| `new_password` | string | ✅ | min 6 chars |

**Response** `200`:

```json
{ "success": true, "data": { "message": "Password reset successfully." } }
```

**Errors**: `400` INVALID_TOKEN, `404` USER_NOT_FOUND

---

## 2. Store Management

**Prefix**: `/api/v1/store`

All endpoints require authentication. Write operations require `owner` role.

### GET `/store/profile`

🔒 **Auth required**

Returns the store profile for the currently authenticated user's store.

**Response** `200`:

```json
{
  "status": "success",
  "message": "Success",
  "data": {
    "store_id": 1,
    "store_name": "My Store",
    "store_type": "grocery",
    "address": "123 Main St",
    "phone": "9876543210",
    "gst_number": "22AAAAA0000A1Z5",
    "currency": "INR"
  }
}
```

---

### PUT `/store/profile`

🔒 **Auth required** | 👤 **Role: owner**

Update store profile. Partial updates allowed.

**Body** (all fields optional):

| Field | Type | Notes |
|---|---|---|
| `store_name` | string | |
| `store_type` | string | `grocery`, `pharmacy`, `electronics`, `clothing`, `general`, `other` |
| `address` | string | |
| `phone` | string | |
| `gst_number` | string | |
| `currency` | string | |

> **Side effect**: Setting `store_type` for the first time auto-creates default categories for that store type.

**Response** `200`:

```json
{
  "status": "success",
  "message": "Store profile updated",
  "data": { ... }
}
```

---

### GET `/store/categories`

🔒 **Auth required**

List all categories for the current store.

**Response** `200`:

```json
{
  "status": "success",
  "data": [
    { "category_id": 1, "name": "Beverages", "gst_rate": 12.0 },
    { "category_id": 2, "name": "Dairy", "gst_rate": 5.0 }
  ]
}
```

---

### POST `/store/categories`

🔒 **Auth required** | 👤 **Role: owner**

Create a new category. Max 50 categories per store.

**Body**:

| Field | Type | Required |
|---|---|---|
| `name` | string | ✅ |
| `gst_rate` | float | ❌ |

**Response** `201`:

```json
{
  "status": "success",
  "message": "Category created",
  "data": { "category_id": 7, "name": "Snacks", "gst_rate": 0.0 }
}
```

---

### PUT `/store/categories/<category_id>`

🔒 **Auth required** | 👤 **Role: owner**

Update a category.

**Body** (partial):

| Field | Type |
|---|---|
| `name` | string |
| `gst_rate` | float |

---

### DELETE `/store/categories/<category_id>`

🔒 **Auth required** | 👤 **Role: owner**

Soft-deletes (deactivates) a category. Fails with `422` if products are still assigned.

---

### GET `/store/tax-config`

🔒 **Auth required**

Returns GST rates for all categories.

```json
{
  "status": "success",
  "data": {
    "taxes": [
      { "category_id": 1, "name": "Beverages", "gst_rate": 12.0 }
    ]
  }
}
```

---

### PUT `/store/tax-config`

🔒 **Auth required** | 👤 **Role: owner**

Bulk update GST rates.

**Body**:

```json
{
  "taxes": [
    { "category_id": 1, "gst_rate": 18.0 },
    { "category_id": 2, "gst_rate": 5.0 }
  ]
}
```

---

## 3. Inventory & Products

**Prefix**: `/api/v1/inventory`

### GET `/inventory/products`

🔒 **Auth required**

List products with filtering, search, and pagination.

**Query Parameters**:

| Param | Type | Default | Notes |
|---|---|---|---|
| `page` | int | 1 | |
| `page_size` | int | 50 | |
| `search` | string | — | Search by name (case-insensitive, partial match) |
| `category_id` | int | — | Filter by category |
| `is_active` | bool | — | Filter active/inactive |
| `sort_by` | string | `name` | `name`, `selling_price`, `current_stock`, `created_at` |
| `sort_order` | string | `asc` | `asc` or `desc` |
| `low_stock` | bool | — | If true, show only products where stock ≤ reorder level |
| `slow_moving` | bool | — | If true, show only products with zero sales for 30 days |

**Response** `200`:

```json
{
  "success": true,
  "data": [
    {
      "product_id": 1,
      "name": "Coca-Cola 500ml",
      "sku_code": "BEV-001",
      "category_id": 1,
      "uom": "pieces",
      "cost_price": 25.0,
      "selling_price": 40.0,
      "current_stock": 150.0,
      "reorder_level": 20.0,
      "supplier_name": "ABC Distributors",
      "barcode": "8901234567890",
      "image_url": null,
      "lead_time_days": 3,
      "is_active": true,
      "is_slow_moving": false,
      "created_at": "2026-01-15T10:30:00"
    }
  ],
  "meta": { "page": 1, "page_size": 50, "total": 230 }
}
```

---

### POST `/inventory/products`

🔒 **Auth required** | 👤 **Role: owner**

Create a new product. SKU code is auto-generated if not provided.

**Body**:

| Field | Type | Required | Validation |
|---|---|---|---|
| `name` | string | ✅ | 1–255 chars |
| `category_id` | int | ❌ | Must belong to store |
| `sku_code` | string | ❌ | Auto-generated if null |
| `uom` | string | ❌ | `pieces`, `kg`, `litre`, `pack` |
| `cost_price` | float | ✅ | |
| `selling_price` | float | ✅ | Must be ≥ cost_price |
| `current_stock` | float | ❌ | Default: 0 |
| `reorder_level` | float | ❌ | Default: 0 |
| `supplier_name` | string | ❌ | |
| `barcode` | string | ❌ | |
| `image_url` | string | ❌ | |
| `lead_time_days` | int | ❌ | Default: 3 |

**Response** `201`:

```json
{
  "success": true,
  "data": { "product_id": 42, ... }
}
```

---

### GET `/inventory/products/<product_id>`

🔒 **Auth required**

Get a single product by ID.

---

### PUT `/inventory/products/<product_id>`

🔒 **Auth required** | 👤 **Role: owner**

Update a product. Partial updates allowed. Price changes are logged in price history.

**Body**: Same fields as create, all optional.

---

### DELETE `/inventory/products/<product_id>`

🔒 **Auth required** | 👤 **Role: owner**

Soft-delete (deactivate) a product.

---

### POST `/inventory/products/<product_id>/stock`

🔒 **Auth required**

Record a stock purchase/update.

**Body**:

| Field | Type | Required | Notes |
|---|---|---|---|
| `quantity_added` | float | ✅ | Can be negative for adjustments |
| `purchase_price` | float | ✅ | Per-unit cost |
| `date` | string | ❌ | `YYYY-MM-DD`, defaults to today |
| `supplier_name` | string | ❌ | |
| `update_cost_price` | bool | ❌ | If true, updates product's cost_price |

**Response** `200`:

```json
{
  "success": true,
  "data": {
    "product_id": 42,
    "new_stock": 200.0,
    "stock_entry_id": 15
  }
}
```

---

### POST `/inventory/audit`

🔒 **Auth required** | 👤 **Role: owner**

Submit a stock audit with actual counts. Records discrepancies.

**Body**:

```json
{
  "items": [
    { "product_id": 1, "actual_qty": 148.0 },
    { "product_id": 2, "actual_qty": 50.0 }
  ],
  "notes": "End of month physical count"
}
```

**Response** `200`:

```json
{
  "success": true,
  "data": {
    "audit_id": 3,
    "adjustments": [
      { "product_id": 1, "expected": 150.0, "actual": 148.0, "difference": -2.0 }
    ]
  }
}
```

---

### GET `/inventory/products/<product_id>/price-history`

🔒 **Auth required**

Returns price change history for a product.

**Response** `200`:

```json
{
  "success": true,
  "data": [
    {
      "cost_price": 25.0,
      "selling_price": 40.0,
      "changed_at": "2026-01-10T08:00:00",
      "changed_by": 1
    }
  ]
}
```

---

### GET `/inventory/alerts`

🔒 **Auth required**

Get active inventory alerts (low stock, margin warnings, slow movers, etc.).

**Query Parameters**:

| Param | Type | Notes |
|---|---|---|
| `alert_type` | string | `LOW_STOCK`, `MARGIN_WARNING`, `SLOW_MOVER`, `REVENUE_DROP`, `SALES_SPIKE` |
| `priority` | string | `CRITICAL`, `HIGH`, `LOW`, `INFO` |

**Response** `200`:

```json
{
  "success": true,
  "data": [
    {
      "alert_id": 5,
      "alert_type": "LOW_STOCK",
      "priority": "CRITICAL",
      "product_id": 42,
      "message": "Low stock: 'Coca-Cola 500ml' has 3.00 units.",
      "created_at": "2026-02-25T06:00:00"
    }
  ]
}
```

---

## 4. Transactions

**Prefix**: `/api/v1/transactions`

### POST `/transactions`

🔒 **Auth required**

Create a single transaction. Automatically deducts stock for each line item.

**Body**:

```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-02-25T10:30:00",
  "payment_mode": "UPI",
  "customer_id": null,
  "notes": "Walk-in customer",
  "line_items": [
    {
      "product_id": 1,
      "quantity": 2,
      "selling_price": 40.0,
      "discount_amount": 0
    },
    {
      "product_id": 5,
      "quantity": 1,
      "selling_price": 120.0,
      "discount_amount": 10
    }
  ]
}
```

| Field | Type | Required | Validation |
|---|---|---|---|
| `transaction_id` | UUID | ✅ | Client-generated, ensures idempotency |
| `timestamp` | datetime | ✅ | ISO 8601 |
| `payment_mode` | string | ✅ | `CASH`, `UPI`, `CARD`, `CREDIT` |
| `customer_id` | int | ❌ | Link to customer record |
| `notes` | string | ❌ | Max 200 chars |
| `line_items` | array | ✅ | Min 1 item |
| `line_items[].product_id` | int | ✅ | Must exist in store |
| `line_items[].quantity` | float | ✅ | Min 0.001 |
| `line_items[].selling_price` | float | ✅ | Min 0 |
| `line_items[].discount_amount` | float | ❌ | Default: 0 |

**Response** `201`:

```json
{
  "success": true,
  "data": { "transaction_id": "550e8400-e29b-41d4-a716-446655440000" }
}
```

---

### POST `/transactions/batch`

🔒 **Auth required**

Create up to 500 transactions in a single request. Used for offline sync.

**Body**:

```json
{
  "transactions": [
    { ... },
    { ... }
  ]
}
```

**Response** `200`:

```json
{
  "success": true,
  "data": {
    "total": 5,
    "succeeded": 4,
    "failed": 1,
    "errors": [
      { "index": 2, "error": "Product not found" }
    ]
  }
}
```

---

### GET `/transactions`

🔒 **Auth required**

List transactions with filtering and pagination. **Staff can only see today's transactions**.

**Query Parameters**:

| Param | Type | Default | Notes |
|---|---|---|---|
| `page` | int | 1 | |
| `page_size` | int | 50 | |
| `start_date` | string | — | `YYYY-MM-DD` (owner only) |
| `end_date` | string | — | `YYYY-MM-DD` (owner only) |
| `payment_mode` | string | — | `CASH`, `UPI`, `CARD`, `CREDIT` |
| `customer_id` | int | — | |
| `min_amount` | float | — | |
| `max_amount` | float | — | |

**Response** `200`:

```json
{
  "success": true,
  "data": [
    {
      "transaction_id": "550e8400-...",
      "created_at": "2026-02-25T10:30:00",
      "payment_mode": "UPI",
      "customer_id": null,
      "is_return": false
    }
  ],
  "meta": { "page": 1, "page_size": 50, "total": 1204 }
}
```

---

### GET `/transactions/<uuid:id>`

🔒 **Auth required**

Get a single transaction with all line items.

**Response** `200`:

```json
{
  "success": true,
  "data": {
    "transaction_id": "550e8400-...",
    "created_at": "2026-02-25T10:30:00",
    "payment_mode": "UPI",
    "customer_id": null,
    "notes": "Walk-in customer",
    "is_return": false,
    "original_transaction_id": null,
    "line_items": [
      {
        "product_id": 1,
        "product_name": "Coca-Cola 500ml",
        "quantity": 2.0,
        "selling_price": 40.0,
        "discount_amount": 0.0
      }
    ]
  }
}
```

---

### POST `/transactions/<uuid:id>/return`

🔒 **Auth required** | 👤 **Role: owner**

Process a return against an existing transaction. Restores stock automatically.

**Body**:

```json
{
  "items": [
    {
      "product_id": 1,
      "quantity_returned": 1,
      "reason": "Damaged packaging"
    }
  ]
}
```

**Response** `201`:

```json
{
  "success": true,
  "data": { "return_transaction_id": "new-uuid-..." }
}
```

---

### GET `/transactions/summary/daily`

🔒 **Auth required**

Get daily business summary.

**Query Parameters**:

| Param | Type | Default |
|---|---|---|
| `date` | string | Today (`YYYY-MM-DD`) |

**Response** `200`:

```json
{
  "success": true,
  "data": {
    "transaction_count": 45,
    "returns_count": 2,
    "avg_basket": 350.50,
    "gross_profit": 4200.00,
    "revenue_by_payment_mode": {
      "CASH": 5000.00,
      "UPI": 8500.00,
      "CARD": 2300.00
    },
    "top_5_products": [
      { "product_id": 1, "name": "Coca-Cola 500ml", "quantity_sold": 45.0 }
    ]
  }
}
```

---

## 5. Customers

**Prefix**: `/api/v1/customers`

### GET `/customers`

🔒 **Auth required**

List customers with search and pagination.

**Query Parameters**:

| Param | Type | Notes |
|---|---|---|
| `page` | int | Default: 1 |
| `page_size` | int | Default: 50 |
| `search` | string | Search by name or mobile |

---

### POST `/customers`

🔒 **Auth required**

Create a new customer.

**Body**:

| Field | Type | Required | Validation |
|---|---|---|---|
| `name` | string | ✅ | 1–255 chars |
| `mobile_number` | string | ✅ | 10–15 digits |
| `email` | string | ❌ | |
| `gender` | string | ❌ | `male`, `female`, `other` |
| `birth_date` | string | ❌ | `YYYY-MM-DD` |
| `address` | string | ❌ | |
| `notes` | string | ❌ | |

---

### GET `/customers/<customer_id>`

🔒 **Auth required**

Get a single customer record.

---

### PUT `/customers/<customer_id>`

🔒 **Auth required**

Update a customer. Partial updates allowed.

---

### GET `/customers/<customer_id>/transactions`

🔒 **Auth required**

Get paginated transaction history for a customer.

**Query Parameters**: `page`, `page_size`, `start_date`, `end_date`

---

### GET `/customers/<customer_id>/summary`

🔒 **Auth required**

Get customer lifetime summary — total spend, visit frequency, average basket, product preferences.

---

### GET `/customers/top`

🔒 **Auth required**

Get top customers ranked by revenue or visit count.

**Query Parameters**:

| Param | Type | Default |
|---|---|---|
| `metric` | string | `revenue` (`revenue` or `visits`) |
| `limit` | int | 10 |

---

### GET `/customers/analytics`

🔒 **Auth required**

Get monthly customer analytics: new customers, returning customers, churn rate, revenue by segment.

---

## 6. Analytics

**Prefix**: `/api/v1/analytics`

All analytics endpoints read from pre-computed aggregation tables. They support date range filtering.

**Common Query Parameters** (all analytics endpoints):

| Param | Type | Default |
|---|---|---|
| `start` | string | 30 days ago (`YYYY-MM-DD`) |
| `end` | string | Today (`YYYY-MM-DD`) |

---

### GET `/analytics/dashboard`

🔒 **Auth required**

**Primary dashboard endpoint.** Returns today's KPIs, 7-day revenue trend, moving average, alerts summary, top products, and AI-generated insight cards — all in a single request (max 5 DB queries).

**Response** `200`:

```json
{
  "success": true,
  "data": {
    "today_kpis": {
      "revenue": 15800.00,
      "profit": 4200.00,
      "transaction_count": 45,
      "avg_basket": 351.11,
      "units_sold": 230
    },
    "revenue_7d": [
      { "date": "2026-02-19", "revenue": 12000.00 },
      { "date": "2026-02-20", "revenue": 14500.00 }
    ],
    "moving_avg_7d": 13500.00,
    "alerts_summary": {
      "critical": 2,
      "high": 1,
      "low": 5,
      "info": 3
    },
    "top_products_today": [
      { "product_id": 1, "name": "Coca-Cola", "revenue": 1200.00, "units": 30 }
    ],
    "insights": [
      {
        "type": "trend",
        "headline": "Revenue Above Average",
        "detail": "Today's revenue is 17% above the 7-day moving average."
      }
    ]
  }
}
```

---

### GET `/analytics/revenue`

🔒 **Auth required**

Daily revenue time series.

**Response**: `{ data: [{ date, revenue, transaction_count, avg_basket }] }`

---

### GET `/analytics/profit`

🔒 **Auth required**

Daily profit time series with margin breakdown.

**Response**: `{ data: [{ date, revenue, cost, profit, margin_pct }] }`

---

### GET `/analytics/top-products`

🔒 **Auth required**

Top products by revenue.

**Query Parameters**: `limit` (default 10)

**Response**: `{ data: [{ product_id, name, revenue, units_sold, profit }] }`

---

### GET `/analytics/category-breakdown`

🔒 **Auth required**

Revenue and units by category.

**Response**: `{ data: [{ category_id, name, revenue, units_sold, profit }] }`

---

### GET `/analytics/contribution`

🔒 **Auth required**

Price-volume-contribution analysis per SKU. Compares current period vs prior period.

**Additional Query Parameters**:

| Param | Type | Notes |
|---|---|---|
| `compare_start` | string | Prior period start (auto-calculated if omitted) |
| `compare_end` | string | Prior period end |

**Response** includes for each SKU: `price_effect`, `volume_effect`, `delta_revenue`.

---

### GET `/analytics/payment-modes`

🔒 **Auth required**

Revenue breakdown by payment mode (CASH, UPI, CARD, CREDIT).

---

### GET `/analytics/customers-summary`

🔒 **Auth required**

Customer analytics: new vs returning, revenue by segment, churn indicators.

---

### GET `/analytics/diagnostics`

🔒 **Auth required**

Advanced diagnostics:
- **Trend deviation**: daily revenue vs 7-day moving average, flagged if >20%
- **Rolling variance**: per-SKU coefficient of variation (14-day and 30-day windows)
- **Margin drift**: gross margin vs prior month, flagged if dropped >3 percentage points

---

## 7. Forecasting

**Prefix**: `/api/v1/forecasting`

Forecasts are **pre-computed** by Celery beat (daily at 2:00 AM). These endpoints serve cached predictions.

### GET `/forecasting/store`

🔒 **Auth required** | 👤 **Role: owner**

Store-level revenue forecast.

**Query Parameters**:

| Param | Type | Default | Max |
|---|---|---|---|
| `horizon` | int | 7 | 90 |

**Response** `200`:

```json
{
  "success": true,
  "data": [
    {
      "date": "2026-02-26",
      "forecast_mean": 14500.00,
      "lower_bound": 12000.00,
      "upper_bound": 17000.00
    }
  ],
  "meta": {
    "regime": "stable",
    "model_type": "prophet",
    "training_window_days": 90,
    "generated_at": "2026-02-25T02:00:00"
  }
}
```

**Errors**: `404` NOT_FOUND (if batch forecast hasn't run yet)

---

### GET `/forecasting/sku/<product_id>`

🔒 **Auth required** | 👤 **Role: owner**

SKU-level demand forecast with reorder suggestion. Only available for top-20% revenue SKUs.

**Query Parameters**: `horizon` (default 7, max 90)

**Response** `200`:

```json
{
  "success": true,
  "data": [
    {
      "date": "2026-02-26",
      "forecast_mean": 12.5,
      "lower_bound": 8.0,
      "upper_bound": 17.0
    }
  ],
  "meta": {
    "product_id": 42,
    "product_name": "Coca-Cola 500ml",
    "regime": "stable",
    "model_type": "prophet",
    "training_window_days": 90,
    "generated_at": "2026-02-25T02:00:00",
    "reorder_suggestion": {
      "should_reorder": true,
      "current_stock": 15.0,
      "forecasted_demand": 87.5,
      "lead_time_days": 3,
      "lead_time_demand": 37.5,
      "suggested_order_qty": 42.5
    }
  }
}
```

---

## 8. AI Recommendations

**Prefix**: `/api/v1/recommendations`

### GET `/recommendations/`

🔒 **Auth required**

Get AI-powered business recommendations. The engine evaluates deterministic rules against current store data (inventory levels, margins, sales trends) and returns prioritized actions.

**Response** `200`:

```json
{
  "status": "success",
  "data": [
    {
      "type": "RESTOCK",
      "priority": "HIGH",
      "product_id": 42,
      "product_name": "Coca-Cola 500ml",
      "message": "Stock will run out in 2 days based on current velocity.",
      "suggested_action": "Order 50 units from ABC Distributors",
      "confidence": 0.92
    },
    {
      "type": "PRICE_OPTIMIZATION",
      "priority": "MEDIUM",
      "product_id": 15,
      "message": "Competitor price data suggests a 5% increase is feasible.",
      "suggested_action": "Increase selling price from ₹120 to ₹126"
    }
  ],
  "meta": {
    "execution_time_ms": 45.2,
    "total_recommendations": 8
  }
}
```

---

## 9. Natural Language Query

**Prefix**: `/api/v1/query`

### POST `/query/`

🔒 **Auth required**

Ask a natural language question about your business. The NLP engine resolves intent and queries the database.

**Body**:

```json
{
  "query_text": "How are my sales doing today?"
}
```

**Supported intents**: `revenue`, `profit`, `inventory`, `forecast`, `top_products`, `default`

**Response** `200`:

```json
{
  "status": "success",
  "data": {
    "intent": "revenue",
    "headline": "Revenue Overview",
    "detail": "Today's revenue is ₹15,800, compared to a 7-day average of ₹13,500.",
    "action": "Revenue is 17.0% above average. Consider maintaining current strategy.",
    "supporting_metrics": {
      "today_revenue": 15800.0,
      "ma_7d": 13500.0,
      "delta_pct": 17.0
    }
  }
}
```

---

## 10. System

### GET `/health`

**No authentication required.** Used by load balancers and container orchestrators.

**Response** `200` (healthy) or `503` (degraded):

```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok"
}
```

### GET `/api/v1/health`

Same as above — backward-compatible path.

### GET `/api/v1/team/ping`

Simple ping endpoint (no auth required).

```json
{ "success": true }
```

---

## Error Codes Reference

| Code | HTTP | Description |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Request body failed schema validation |
| `DUPLICATE_MOBILE` | 400 | Mobile number already registered |
| `INVALID_OTP` | 400 | OTP is wrong or expired |
| `INVALID_DATE` | 400 | Date must be YYYY-MM-DD |
| `BAD_REQUEST` | 400 | Generic bad request |
| `UNAUTHORIZED` | 401 | Missing or invalid auth header |
| `TOKEN_EXPIRED` | 401 | JWT access token expired — refresh it |
| `INVALID_TOKEN` | 401 | JWT is malformed or tampered |
| `INVALID_CREDENTIALS` | 401 | Wrong mobile number or password |
| `INACTIVE_ACCOUNT` | 403 | Account not verified via OTP |
| `FORBIDDEN` | 403 | User role insufficient |
| `NOT_FOUND` | 404 | Resource not found |
| `USER_NOT_FOUND` | 404 | User does not exist |
| `SERVER_ERROR` | 500 | Unexpected server error |

---

## Frontend Integration Notes

### Token Management

1. Store `access_token` and `refresh_token` securely (e.g., `SecureStorage` on mobile)
2. Send `Authorization: Bearer <access_token>` on every authenticated request
3. When you get a `401 TOKEN_EXPIRED`, call `POST /auth/refresh` with the refresh token
4. If refresh also fails with `401`, redirect to login

### Offline Sync Pattern

1. Generate `transaction_id` (UUID) client-side for idempotency
2. Store transactions locally when offline
3. On reconnect, use `POST /transactions/batch` to sync up to 500 at once
4. The batch response tells you which succeeded and which failed

### Date Handling

- All dates in requests and responses use **ISO 8601** format
- Date-only fields: `YYYY-MM-DD`
- DateTime fields: `YYYY-MM-DDTHH:MM:SS`
- Server timezone: `Asia/Kolkata` (for Celery beat schedules)

### Pagination

Paginated endpoints use consistent query parameters:

```
?page=1&page_size=50
```

And return a `meta` object:

```json
{ "meta": { "page": 1, "page_size": 50, "total": 1204 } }
```

### Rate Limiting

- Login: **5 attempts per 15 minutes** per mobile number
- Global: No hard global limit, but Redis-backed rate limiter is active
- Rate limit headers are returned when applicable

### Role-Based Access

| Role | Can do |
|---|---|
| `owner` | Everything — CRUD on products, categories, transactions, returns, tax config, store profile. Access to forecasting, analytics, recommendations |
| `staff` | View products, create transactions, view today's transactions only. Cannot edit products, categories, store profile, or process returns |
