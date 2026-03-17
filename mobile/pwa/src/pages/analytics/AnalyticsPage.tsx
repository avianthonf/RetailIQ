import { BarChart3, Search, Plus, Filter, Download, TrendingUp, PieChart, Activity } from 'lucide-react'

export function AnalyticsPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Analytics & Reports</h1>
          <p className="text-muted-foreground">Business insights, reports, and AI-powered analytics</p>
        </div>
        
        <div className="flex items-center gap-2">
          <button className="btn-primary btn-md inline-flex items-center gap-2">
            <Plus className="h-4 w-4" />
            New Report
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Revenue Growth</h3>
          <p className="text-2xl font-bold text-success mt-1">+23.5%</p>
          <p className="text-xs text-muted-foreground mt-1">vs last month</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Top Product</h3>
          <p className="text-2xl font-bold text-foreground mt-1">Coffee</p>
          <p className="text-xs text-muted-foreground mt-1">₹2.4L revenue</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Avg Order Value</h3>
          <p className="text-2xl font-bold text-primary mt-1">₹485</p>
          <p className="text-xs text-success mt-1">+12% increase</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Reports Generated</h3>
          <p className="text-2xl font-bold text-accent mt-1">142</p>
          <p className="text-xs text-muted-foreground mt-1">This month</p>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search reports..."
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

      {/* Quick Reports */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card p-4 text-center hover:shadow-md transition-shadow cursor-pointer">
          <BarChart3 className="h-8 w-8 text-primary mx-auto mb-2" />
          <h3 className="font-medium text-foreground">Sales Report</h3>
          <p className="text-xs text-muted-foreground mt-1">Daily/weekly/monthly</p>
        </div>
        <div className="card p-4 text-center hover:shadow-md transition-shadow cursor-pointer">
          <PieChart className="h-8 w-8 text-accent mx-auto mb-2" />
          <h3 className="font-medium text-foreground">Category Analysis</h3>
          <p className="text-xs text-muted-foreground mt-1">Product performance</p>
        </div>
        <div className="card p-4 text-center hover:shadow-md transition-shadow cursor-pointer">
          <TrendingUp className="h-8 w-8 text-success mx-auto mb-2" />
          <h3 className="font-medium text-foreground">Trend Analysis</h3>
          <p className="text-xs text-muted-foreground mt-1">Growth patterns</p>
        </div>
        <div className="card p-4 text-center hover:shadow-md transition-shadow cursor-pointer">
          <Activity className="h-8 w-8 text-warning mx-auto mb-2" />
          <h3 className="font-medium text-foreground">Custom Report</h3>
          <p className="text-xs text-muted-foreground mt-1">Build your own</p>
        </div>
      </div>

      {/* Analytics Content Placeholder */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Analytics Dashboard</h3>
        </div>
        <div className="card-content">
          <div className="text-center py-12">
            <BarChart3 className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">Analytics Module Coming Soon</h3>
            <p className="text-muted-foreground mb-4">
              Advanced analytics and reporting features will be implemented in the next phase
            </p>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>✓ Interactive dashboards</p>
              <p>✓ Custom report builder</p>
              <p>✓ AI-powered insights</p>
              <p>✓ Data visualization</p>
              <p>✓ Scheduled reports</p>
              <p>✓ Export to PDF/Excel</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
