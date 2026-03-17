// Generated types from OpenAPI spec
// This is a simplified version - in production, generate from openapi.json

export interface User {
  user_id: number
  mobile_number: string
  full_name: string
  email?: string
  role: 'owner' | 'staff'
  store_id?: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Store {
  store_id: number
  store_name: string
  store_type: string
  address?: string
  phone?: string
  gst_number?: string
  currency: string
  owner_user_id: number
  created_at: string
  updated_at: string
}

export interface LoginResponse {
  success: boolean
  data: {
    access_token: string
    refresh_token: string
    user: User
    role: string
    store_id?: number
  }
  message?: string
}

export interface RegisterResponse {
  success: boolean
  data: {
    message: string
  }
  message?: string
}

export interface OTPResponse {
  success: boolean
  data: {
    message: string
  }
  message?: string
}

// Dashboard types
export interface DashboardOverview {
  sales_today: number
  sales_this_week: number
  sales_this_month: number
  gross_margin_today: number
  gross_margin_this_week: number
  gross_margin_this_month: number
  transactions_today: number
  transactions_this_week: number
  transactions_this_month: number
  inventory_at_risk: number
  pos_pending: number
  loyalty_redemptions: number
  online_orders: number
}

export interface Alert {
  id: string
  type: 'info' | 'warning' | 'error' | 'success'
  title: string
  message: string
  timestamp: string
  read: boolean
  action_url?: string
}

export interface LiveSignal {
  id: string
  type: string
  message: string
  timestamp: string
  metadata?: Record<string, any>
}

export interface Incident {
  id: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  title: string
  description: string
  status: 'active' | 'investigating' | 'resolved'
  created_at: string
  updated_at: string
  communications: Array<{
    message: string
    timestamp: string
    author: string
  }>
}

// Inventory types
export interface Product {
  product_id: number
  sku: string
  name: string
  description?: string
  category_id: number
  cost_price: number
  selling_price: number
  stock_quantity: number
  min_stock_level: number
  barcode?: string
  image_url?: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Category {
  category_id: number
  name: string
  gst_rate: number
  is_active: boolean
}

export interface StockAdjustment {
  adjustment_id: number
  product_id: number
  quantity: number
  reason: string
  type: 'increase' | 'decrease'
  created_by: number
  created_at: string
}

// POS/Transaction types
export interface CartItem {
  product_id: number
  name: string
  sku: string
  quantity: number
  unit_price: number
  total_price: number
  discount?: number
}

export interface Cart {
  items: CartItem[]
  subtotal: number
  tax: number
  discount: number
  total: number
  customer_id?: number
}

export interface Payment {
  id: string
  type: 'cash' | 'card' | 'upi' | 'wallet'
  amount: number
  status: 'pending' | 'completed' | 'failed'
  reference?: string
}

export interface Transaction {
  transaction_id: number
  type: 'sale' | 'refund'
  items: CartItem[]
  payments: Payment[]
  subtotal: number
  tax: number
  discount: number
  total: number
  customer_id?: number
  staff_id: number
  store_id: number
  status: 'pending' | 'completed' | 'cancelled'
  created_at: string
  updated_at: string
}

// Supplier types
export interface Supplier {
  supplier_id: number
  name: string
  contact_person?: string
  email?: string
  phone?: string
  address?: string
  gst_number?: string
  is_active: boolean
  created_at: string
}

export interface PurchaseOrder {
  po_id: number
  supplier_id: number
  order_number: string
  status: 'draft' | 'sent' | 'partial' | 'received' | 'cancelled'
  items: Array<{
    product_id: number
    quantity: number
    unit_price: number
    total_price: number
  }>
  subtotal: number
  tax: number
  total: number
  expected_delivery_date?: string
  created_at: string
  updated_at: string
}

// Pricing types
export interface PricingRule {
  rule_id: number
  name: string
  type: 'markup' | 'discount' | 'promotion'
  conditions: Record<string, any>
  actions: Record<string, any>
  is_active: boolean
  created_at: string
}

export interface PricingSuggestion {
  id: number
  product_id: number
  product_name: string
  current_price: number
  suggested_price: number
  price_change_pct: number
  reason: string
  confidence: number
  status: 'pending' | 'applied' | 'dismissed'
  created_at: string
}

// Standard API response wrapper
export interface ApiResponse<T = any> {
  success: boolean
  data: T
  error?: {
    code: string
    message: string
  }
  message?: string
  timestamp: string
}

// Pagination types
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  limit: number
  has_next: boolean
  has_prev: boolean
}

export interface PaginationParams {
  page?: number
  limit?: number
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}
