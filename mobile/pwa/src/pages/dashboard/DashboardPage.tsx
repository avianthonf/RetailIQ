import { useState } from 'react'
import { 
  TrendingUp, 
  TrendingDown, 
  Package, 
  ShoppingCart, 
  Users, 
  CreditCard,
  AlertTriangle,
  Activity,
  Calendar,
  Filter,
  Download,
  RefreshCw
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'
import { formatCurrency, formatNumber } from '@/lib/utils'
import { KpiCard } from '@/components/dashboard/KpiCard'
import { AlertsInbox } from '@/components/dashboard/AlertsInbox'
import { LiveSignalsLane } from '@/components/dashboard/LiveSignalsLane'
import { ForecastHorizonPanel } from '@/components/dashboard/ForecastHorizonPanel'
import { IncidentOverlay } from '@/components/dashboard/IncidentOverlay'

// API function
const fetchDashboardOverview = async () => {
  const { data } = await apiClient.get('/dashboard/overview')
  return data.data
}

export function DashboardPage() {
  const [selectedTimeRange, setSelectedTimeRange] = useState('today')
  const [isRefreshing, setIsRefreshing] = useState(false)

  const { data: overview, isLoading, error, refetch } = useQuery({
    queryKey: ['dashboard-overview', selectedTimeRange],
    queryFn: fetchDashboardOverview,
    staleTime: 60000, // 1 minute
  })

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await refetch()
    setIsRefreshing(false)
  }

  const kpis = [
    {
      title: 'Sales',
      value: formatCurrency(overview?.sales_today || 0),
      change: overview?.sales_today > 0 ? 12.5 : -5.2,
      changeType: overview?.sales_today > 0 ? 'increase' : 'decrease',
      icon: TrendingUp,
      color: 'primary',
    },
    {
      title: 'Gross Margin',
      value: `${overview?.gross_margin_today || 0}%`,
      change: overview?.gross_margin_today > 0 ? 2.1 : -1.3,
      changeType: overview?.gross_margin_today > 0 ? 'increase' : 'decrease',
      icon: TrendingDown,
      color: 'success',
    },
    {
      title: 'Inventory at Risk',
      value: formatNumber(overview?.inventory_at_risk || 0),
      change: -8.4,
      changeType: 'decrease',
      icon: Package,
      color: 'warning',
    },
    {
      title: 'POs Pending',
      value: formatNumber(overview?.pos_pending || 0),
      change: 3,
      changeType: 'increase',
      icon: ShoppingCart,
      color: 'accent',
    },
    {
      title: 'Loyalty Redemptions',
      value: formatNumber(overview?.loyalty_redemptions || 0),
      change: 15.3,
      changeType: 'increase',
      icon: Users,
      color: 'secondary',
    },
    {
      title: 'Online Orders',
      value: formatNumber(overview?.online_orders || 0),
      change: -2.5,
      changeType: 'decrease',
      icon: CreditCard,
      color: 'info',
    },
  ]

  if (error) {
    return (
      <div className="text-center py-12">
        <AlertTriangle className="h-12 w-12 text-error mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-foreground">Failed to load dashboard</h3>
        <p className="text-muted-foreground mb-4">Please try again later</p>
        <button onClick={() => refetch()} className="btn-primary btn-md">
          Try Again
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
          <p className="text-muted-foreground">Welcome back! Here's your business overview.</p>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="btn-ghost btn-sm inline-flex items-center gap-2"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          
          <select
            value={selectedTimeRange}
            onChange={(e) => setSelectedTimeRange(e.target.value)}
            className="input btn-sm"
          >
            <option value="today">Today</option>
            <option value="week">This Week</option>
            <option value="month">This Month</option>
            <option value="quarter">This Quarter</option>
          </select>
          
          <button className="btn-ghost btn-sm inline-flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Filters
          </button>
          
          <button className="btn-ghost btn-sm inline-flex items-center gap-2">
            <Download className="h-4 w-4" />
            Export
          </button>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {kpis.map((kpi, index) => (
          <KpiCard key={index} {...kpi} isLoading={isLoading} />
        ))}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - 2 columns wide */}
        <div className="lg:col-span-2 space-y-6">
          {/* Forecast Horizon */}
          <ForecastHorizonPanel />
          
          {/* Alerts Inbox */}
          <AlertsInbox />
        </div>

        {/* Right Column - 1 column */}
        <div className="space-y-6">
          {/* Live Signals */}
          <LiveSignalsLane />
          
          {/* Quick Actions */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Quick Actions</h3>
            </div>
            <div className="card-content space-y-3">
              <button className="btn-outline btn-md w-full justify-start">
                <Package className="h-4 w-4 mr-2" />
                Add New Product
              </button>
              <button className="btn-outline btn-md w-full justify-start">
                <ShoppingCart className="h-4 w-4 mr-2" />
                Create Purchase Order
              </button>
              <button className="btn-outline btn-md w-full justify-start">
                <Users className="h-4 w-4 mr-2" />
                Add Customer
              </button>
              <button className="btn-outline btn-md w-full justify-start">
                <Calendar className="h-4 w-4 mr-2" />
                View Reports
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Incident Overlay */}
      <IncidentOverlay />
    </div>
  )
}

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}
