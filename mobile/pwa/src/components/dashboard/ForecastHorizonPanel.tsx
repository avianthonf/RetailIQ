import { useState } from 'react'
import { TrendingUp, Calendar, BarChart3, Eye } from 'lucide-react'
import { formatCurrency } from '@/lib/utils'

// Mock forecast data
const forecastData = {
  summary: {
    projected_revenue: 2450000,
    growth_rate: 15.3,
    confidence: 87,
    period: 'Next 30 days',
  },
  categories: [
    {
      name: 'Beverages',
      current: 450000,
      projected: 520000,
      growth: 15.6,
      confidence: 92,
    },
    {
      name: 'Snacks',
      current: 320000,
      projected: 355000,
      growth: 10.9,
      confidence: 85,
    },
    {
      name: 'Dairy',
      current: 280000,
      projected: 310000,
      growth: 10.7,
      confidence: 88,
    },
    {
      name: 'Bakery',
      current: 190000,
      projected: 225000,
      growth: 18.4,
      confidence: 79,
    },
  ],
  recommendations: [
    {
      type: 'stock',
      title: 'Increase Coffee Bean Stock',
      description: 'Expected 35% increase in demand for premium coffee beans',
      priority: 'high',
    },
    {
      type: 'pricing',
      title: 'Adjust Dairy Prices',
      description: 'Market analysis suggests 5% price increase opportunity',
      priority: 'medium',
    },
    {
      type: 'promotion',
      title: 'Weekend Bakery Promotion',
      description: 'Historical data shows 40% higher weekend sales',
      priority: 'low',
    },
  ],
}

export function ForecastHorizonPanel() {
  const [selectedPeriod, setSelectedPeriod] = useState('30d')
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null)

  const periods = [
    { value: '7d', label: '7 Days' },
    { value: '30d', label: '30 Days' },
    { value: '90d', label: '90 Days' },
  ]

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high':
        return 'text-error bg-error/10'
      case 'medium':
        return 'text-warning bg-warning/10'
      case 'low':
        return 'text-success bg-success/10'
      default:
        return 'text-muted-foreground bg-muted'
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <div className="flex items-center justify-between">
          <h3 className="card-title">Forecast Horizon</h3>
          <div className="flex items-center gap-2">
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
              className="input btn-sm"
            >
              {periods.map(period => (
                <option key={period.value} value={period.value}>
                  {period.label}
                </option>
              ))}
            </select>
            <button className="btn-ghost btn-sm">
              <Eye className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
      
      <div className="card-content space-y-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="text-center p-4 bg-primary/5 rounded-lg">
            <p className="text-sm text-muted-foreground mb-1">Projected Revenue</p>
            <p className="text-2xl font-bold text-primary">
              {formatCurrency(forecastData.summary.projected_revenue)}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {forecastData.summary.period}
            </p>
          </div>
          
          <div className="text-center p-4 bg-success/5 rounded-lg">
            <p className="text-sm text-muted-foreground mb-1">Growth Rate</p>
            <p className="text-2xl font-bold text-success">
              +{forecastData.summary.growth_rate}%
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              vs last period
            </p>
          </div>
          
          <div className="text-center p-4 bg-accent/5 rounded-lg">
            <p className="text-sm text-muted-foreground mb-1">Confidence</p>
            <p className="text-2xl font-bold text-accent">
              {forecastData.summary.confidence}%
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              AI confidence
            </p>
          </div>
        </div>

        {/* Category Forecasts */}
        <div>
          <h4 className="text-sm font-medium text-foreground mb-3">Category Forecasts</h4>
          <div className="space-y-2">
            {forecastData.categories.map((category) => (
              <div
                key={category.name}
                className="p-3 border border-border rounded-lg hover:bg-muted/50 transition-colors cursor-pointer"
                onClick={() => setExpandedCategory(expandedCategory === category.name ? null : category.name)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-foreground">
                        {category.name}
                      </span>
                      <span className="text-sm text-success">
                        +{category.growth}%
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>Current: {formatCurrency(category.current)}</span>
                      <span>Projected: {formatCurrency(category.projected)}</span>
                      <span>Confidence: {category.confidence}%</span>
                    </div>
                  </div>
                  <BarChart3 className="h-4 w-4 text-muted-foreground" />
                </div>
                
                {/* Mini Chart Placeholder */}
                <div className="mt-2 h-8 flex items-end gap-0.5">
                  {Array.from({ length: 12 }).map((_, i) => (
                    <div
                      key={i}
                      className="flex-1 bg-primary/20 rounded-t-sm"
                      style={{
                        height: `${Math.random() * 100}%`,
                      }}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recommendations */}
        <div>
          <h4 className="text-sm font-medium text-foreground mb-3">AI Recommendations</h4>
          <div className="space-y-2">
            {forecastData.recommendations.map((rec, index) => (
              <div key={index} className="p-3 border border-border rounded-lg">
                <div className="flex items-start gap-3">
                  <div className={cn('px-2 py-1 rounded text-xs font-medium', getPriorityColor(rec.priority))}>
                    {rec.priority.toUpperCase()}
                  </div>
                  <div className="flex-1">
                    <h5 className="text-sm font-medium text-foreground mb-1">
                      {rec.title}
                    </h5>
                    <p className="text-xs text-muted-foreground">
                      {rec.description}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function cn(...classes: string[]) {
  return classes.filter(Boolean).join(' ')
}
