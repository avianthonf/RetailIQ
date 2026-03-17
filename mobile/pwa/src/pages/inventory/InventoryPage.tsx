import { useState } from 'react'
import { Package, Search, Plus, Filter, Download, Barcode } from 'lucide-react'

export function InventoryPage() {
  const [searchQuery, setSearchQuery] = useState('')

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Inventory Management</h1>
          <p className="text-muted-foreground">Manage your products, stock, and categories</p>
        </div>
        
        <div className="flex items-center gap-2">
          <button className="btn-primary btn-md inline-flex items-center gap-2">
            <Plus className="h-4 w-4" />
            Add Product
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Total Products</h3>
          <p className="text-2xl font-bold text-foreground mt-1">1,248</p>
          <p className="text-xs text-success mt-1">+12% from last month</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Low Stock Items</h3>
          <p className="text-2xl font-bold text-warning mt-1">23</p>
          <p className="text-xs text-muted-foreground mt-1">Needs attention</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Total Value</h3>
          <p className="text-2xl font-bold text-foreground mt-1">₹12.4L</p>
          <p className="text-xs text-success mt-1">+8% from last month</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Categories</h3>
          <p className="text-2xl font-bold text-foreground mt-1">15</p>
          <p className="text-xs text-muted-foreground mt-1">Active categories</p>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search products by name, SKU, or barcode..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input pl-10"
          />
        </div>
        
        <div className="flex items-center gap-2">
          <button className="btn-outline btn-md inline-flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Filters
          </button>
          <button className="btn-outline btn-md inline-flex items-center gap-2">
            <Barcode className="h-4 w-4" />
            Scan
          </button>
          <button className="btn-outline btn-md inline-flex items-center gap-2">
            <Download className="h-4 w-4" />
            Export
          </button>
        </div>
      </div>

      {/* Inventory Table Placeholder */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Products</h3>
        </div>
        <div className="card-content">
          <div className="text-center py-12">
            <Package className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">Inventory Module Coming Soon</h3>
            <p className="text-muted-foreground mb-4">
              Full inventory management features will be implemented in the next phase
            </p>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>✓ Product catalog management</p>
              <p>✓ Stock tracking and adjustments</p>
              <p>✓ Barcode scanning</p>
              <p>✓ Low stock alerts</p>
              <p>✓ Supplier management</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
