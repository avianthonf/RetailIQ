import { Heart, Search, Plus, Filter, Download, Users, Gift, Star } from 'lucide-react'

export function LoyaltyPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Customer Loyalty</h1>
          <p className="text-muted-foreground">Manage loyalty programs, rewards, and customer relationships</p>
        </div>
        
        <div className="flex items-center gap-2">
          <button className="btn-primary btn-md inline-flex items-center gap-2">
            <Plus className="h-4 w-4" />
            Add Customer
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Total Members</h3>
          <p className="text-2xl font-bold text-foreground mt-1">3,847</p>
          <p className="text-xs text-success mt-1">+124 this week</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Active Today</h3>
          <p className="text-2xl font-bold text-primary mt-1">284</p>
          <p className="text-xs text-muted-foreground mt-1">7.4% engagement</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Points Issued</h3>
          <p className="text-2xl font-bold text-accent mt-1">48.2K</p>
          <p className="text-xs text-success mt-1">+18% this month</p>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Rewards Redeemed</h3>
          <p className="text-2xl font-bold text-success mt-1">156</p>
          <p className="text-xs text-muted-foreground mt-1">This week</p>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search customers..."
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

      {/* Quick Actions */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card p-4 text-center hover:shadow-md transition-shadow cursor-pointer">
          <Gift className="h-8 w-8 text-primary mx-auto mb-2" />
          <h3 className="font-medium text-foreground">Create Campaign</h3>
          <p className="text-xs text-muted-foreground mt-1">Launch new loyalty offers</p>
        </div>
        <div className="card p-4 text-center hover:shadow-md transition-shadow cursor-pointer">
          <Star className="h-8 w-8 text-accent mx-auto mb-2" />
          <h3 className="font-medium text-foreground">Rewards Store</h3>
          <p className="text-xs text-muted-foreground mt-1">Manage reward catalog</p>
        </div>
        <div className="card p-4 text-center hover:shadow-md transition-shadow cursor-pointer">
          <Users className="h-8 w-8 text-success mx-auto mb-2" />
          <h3 className="font-medium text-foreground">Segments</h3>
          <p className="text-xs text-muted-foreground mt-1">Customer segmentation</p>
        </div>
      </div>

      {/* Customers Table Placeholder */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Recent Customers</h3>
        </div>
        <div className="card-content">
          <div className="text-center py-12">
            <Heart className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">Loyalty Module Coming Soon</h3>
            <p className="text-muted-foreground mb-4">
              Complete customer loyalty features will be implemented in the next phase
            </p>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>✓ Customer profiles with 360° view</p>
              <p>✓ Points and rewards system</p>
              <p>✓ Tier management</p>
              <p>✓ Campaign management</p>
              <p>✓ Analytics and insights</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
