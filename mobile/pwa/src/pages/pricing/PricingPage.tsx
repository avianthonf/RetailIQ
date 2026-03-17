import { DollarSign, TrendingUp, Search, Plus, Filter, Download } from 'lucide-react'

export function PricingPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Pricing & Intelligence</h1>
          <p className="text-muted-foreground">Dynamic pricing, forecasts, and market insights</p>
        </div>
        
        <div className="flex items-center gap-2">
          <button className="btn-primary btn-md inline-flex items-center gap-2">
            <Plus className="h-4 w-4" />
            New Pricing Rule
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Active Rules</h3>
          <p className="text-2xl font-bold text-foreground mt-1">24</p>
          <p className="text-xs text-success mt-1">3 running today</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Price Changes</h3>
          <p className="text-2xl font-bold text-foreground mt-1">156</p>
          <p className="text-xs text-success mt-1">+12% this week</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Margin Improvement</h3>
          <p className="text-2xl font-bold text-success mt-1">+2.4%</p>
          <p className="text-xs text-muted-foreground mt-1">From optimizations</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">AI Suggestions</h3>
          <p className="text-2xl font-bold text-accent mt-1">8</p>
          <p className="text-xs text-muted-foreground mt-1">Pending review</p>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search products or rules..."
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

      {/* Pricing Content Placeholder */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Pricing Intelligence</h3>
        </div>
        <div className="card-content">
          <div className="text-center py-12">
            <DollarSign className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">Pricing Module Coming Soon</h3>
            <p className="text-muted-foreground mb-4">
              Advanced pricing and intelligence features will be implemented in the next phase
            </p>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>✓ Dynamic pricing rules</p>
              <p>✓ AI-powered recommendations</p>
              <p>✓ Competitor price tracking</p>
              <p>✓ Demand forecasting</p>
              <p>✓ Promotion management</p>
              <p>✓ Market intelligence</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
