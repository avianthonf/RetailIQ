import { Users, Search, Plus, Filter, Download } from 'lucide-react'

export function SuppliersPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Suppliers & Procurement</h1>
          <p className="text-muted-foreground">Manage suppliers, purchase orders, and goods receipts</p>
        </div>
        
        <div className="flex items-center gap-2">
          <button className="btn-primary btn-md inline-flex items-center gap-2">
            <Plus className="h-4 w-4" />
            Add Supplier
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Active Suppliers</h3>
          <p className="text-2xl font-bold text-foreground mt-1">48</p>
          <p className="text-xs text-success mt-1">+4 this month</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Pending POs</h3>
          <p className="text-2xl font-bold text-warning mt-1">12</p>
          <p className="text-xs text-muted-foreground mt-1">Awaiting delivery</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">This Month Orders</h3>
          <p className="text-2xl font-bold text-foreground mt-1">₹8.4L</p>
          <p className="text-xs text-success mt-1">+15% from last month</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">On-time Delivery</h3>
          <p className="text-2xl font-bold text-success mt-1">94%</p>
          <p className="text-xs text-muted-foreground mt-1">Last 30 days</p>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search suppliers..."
            className="input pl-10"
          />
        </div>
        
        <div className="flex items-center gap-2">
          <button className="btn-outline btn-md inline-flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Filters
          </button>
          <button className="btn-outline btn-md inline-flex items-center gap-2">
            <Download className="h-4 w-4" />
            Export
          </button>
        </div>
      </div>

      {/* Suppliers Table Placeholder */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Suppliers</h3>
        </div>
        <div className="card-content">
          <div className="text-center py-12">
            <Users className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">Suppliers Module Coming Soon</h3>
            <p className="text-muted-foreground mb-4">
              Complete supplier management features will be implemented in the next phase
            </p>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>✓ Supplier directory with ratings</p>
              <p>✓ Purchase order management</p>
              <p>✓ Goods receipt processing</p>
              <p>✓ RFQ and quote comparison</p>
              <p>✓ Supplier performance analytics</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
