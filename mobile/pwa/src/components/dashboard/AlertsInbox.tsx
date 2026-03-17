import { useState } from 'react'
import { AlertTriangle, Info, CheckCircle, X, ChevronRight, Bell } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'
import { formatDateTime } from '@/lib/utils'
import type { Alert } from '@/types/api'

// Mock API function
const fetchAlerts = async () => {
  // In production, this would be a real API call
  return {
    data: [
      {
        id: '1',
        type: 'warning' as const,
        title: 'Low Stock Alert',
        message: 'Premium Coffee Beans is running low on stock (5 units remaining)',
        timestamp: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
        read: false,
        action_url: '/inventory',
      },
      {
        id: '2',
        type: 'error' as const,
        title: 'Payment Gateway Issue',
        message: 'UPI payments are experiencing delays. Please check your payment provider.',
        timestamp: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
        read: false,
        action_url: '/settings',
      },
      {
        id: '3',
        type: 'success' as const,
        title: 'Sales Milestone',
        message: 'Congratulations! You\'ve achieved 100 sales today.',
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
        read: true,
      },
      {
        id: '4',
        type: 'info' as const,
        title: 'System Update',
        message: 'New features have been added to your dashboard. Check them out!',
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
        read: true,
      },
    ],
  }
}

const alertIcons = {
  error: AlertTriangle,
  warning: AlertTriangle,
  success: CheckCircle,
  info: Info,
}

const alertColors = {
  error: 'text-error bg-error/10',
  warning: 'text-warning bg-warning/10',
  success: 'text-success bg-success/10',
  info: 'text-info bg-info/10',
}

export function AlertsInbox() {
  const [selectedAlerts, setSelectedAlerts] = useState<string[]>([])
  const { data: alertsData, isLoading } = useQuery({
    queryKey: ['alerts'],
    queryFn: fetchAlerts,
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  const alerts = alertsData?.data || []

  const handleSelectAll = () => {
    if (selectedAlerts.length === alerts.length) {
      setSelectedAlerts([])
    } else {
      setSelectedAlerts(alerts.map(a => a.id))
    }
  }

  const handleMarkAsRead = (alertId: string) => {
    // TODO: API call to mark as read
    console.log('Mark as read:', alertId)
  }

  const handleDeleteSelected = () => {
    // TODO: API call to delete selected alerts
    console.log('Delete selected:', selectedAlerts)
    setSelectedAlerts([])
  }

  const unreadCount = alerts.filter(a => !a.read).length

  return (
    <div className="card">
      <div className="card-header">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="card-title">Alerts</h3>
            {unreadCount > 0 && (
              <span className="inline-flex items-center justify-center w-5 h-5 text-xs font-medium bg-error text-error-foreground rounded-full">
                {unreadCount}
              </span>
            )}
          </div>
          <button className="btn-ghost btn-sm">
            <Bell className="h-4 w-4" />
          </button>
        </div>
      </div>
      
      <div className="card-content p-0">
        {/* Actions Bar */}
        {selectedAlerts.length > 0 && (
          <div className="px-4 py-2 border-b border-border bg-muted/50 flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {selectedAlerts.length} selected
            </span>
            <div className="flex items-center gap-2">
              <button 
                onClick={() => selectedAlerts.forEach(handleMarkAsRead)}
                className="btn-ghost btn-sm"
              >
                Mark as Read
              </button>
              <button 
                onClick={handleDeleteSelected}
                className="btn-ghost btn-sm text-error"
              >
                Delete
              </button>
            </div>
          </div>
        )}

        {/* Alerts List */}
        <div className="divide-y divide-border">
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="p-4 space-y-2">
                <div className="h-4 w-2/3 bg-muted animate-pulse rounded" />
                <div className="h-3 w-full bg-muted animate-pulse rounded" />
                <div className="h-3 w-1/4 bg-muted animate-pulse rounded" />
              </div>
            ))
          ) : alerts.length === 0 ? (
            <div className="p-8 text-center">
              <Info className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
              <p className="text-muted-foreground">No alerts at this time</p>
            </div>
          ) : (
            alerts.map((alert) => {
              const Icon = alertIcons[alert.type]
              return (
                <div
                  key={alert.id}
                  className={cn(
                    'p-4 hover:bg-muted/50 transition-colors cursor-pointer',
                    !alert.read && 'bg-primary/5'
                  )}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={selectedAlerts.includes(alert.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedAlerts([...selectedAlerts, alert.id])
                        } else {
                          setSelectedAlerts(selectedAlerts.filter(id => id !== alert.id))
                        }
                      }}
                      className="mt-1 rounded border-border"
                    />
                    
                    <div className={cn('p-2 rounded-lg flex-shrink-0', alertColors[alert.type])}>
                      <Icon className="h-4 w-4" />
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1">
                          <h4 className="text-sm font-medium text-foreground">
                            {alert.title}
                          </h4>
                          <p className="text-sm text-muted-foreground mt-1">
                            {alert.message}
                          </p>
                          <p className="text-xs text-muted-foreground mt-2">
                            {formatDateTime(alert.timestamp)}
                          </p>
                        </div>
                        
                        {alert.action_url && (
                          <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                        )}
                      </div>
                    </div>
                    
                    {!alert.read && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleMarkAsRead(alert.id)
                        }}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
      
      {/* Footer */}
      <div className="card-footer">
        <button className="btn-ghost btn-sm w-full">
          View All Alerts
        </button>
      </div>
    </div>
  )
}
