import { useState } from 'react'
import { AlertTriangle, Clock, CheckCircle, X, MessageSquare } from 'lucide-react'
import { formatDateTime } from '@/lib/utils'
import type { Incident } from '@/types/api'

// Mock incident data
const mockIncidents: Incident[] = [
  {
    id: '1',
    severity: 'high',
    title: 'Payment Gateway Delays',
    description: 'We are experiencing intermittent delays with UPI payments. Our team is actively working on a resolution.',
    status: 'investigating',
    created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    updated_at: new Date(Date.now() - 1000 * 60 * 10).toISOString(),
    communications: [
      {
        message: 'We are investigating reports of UPI payment delays',
        timestamp: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
        author: 'System',
      },
      {
        message: 'Our engineering team has identified the issue and is working on a fix',
        timestamp: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
        author: 'Engineering Team',
      },
      {
        message: 'We expect to resolve this within the next 30 minutes',
        timestamp: new Date(Date.now() - 1000 * 60 * 10).toISOString(),
        author: 'Engineering Team',
      },
    ],
  },
]

export function IncidentOverlay() {
  const [incidents] = useState<Incident[]>(mockIncidents)
  const [expandedIncident, setExpandedIncident] = useState<string | null>(null)
  const [dismissedIncidents, setDismissedIncidents] = useState<string[]>([])

  const activeIncidents = incidents.filter(i => i.status !== 'resolved' && !dismissedIncidents.includes(i.id))

  if (activeIncidents.length === 0) {
    return null
  }

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'border-error bg-error/5'
      case 'high':
        return 'border-warning bg-warning/5'
      case 'medium':
        return 'border-accent bg-accent/5'
      case 'low':
        return 'border-info bg-info/5'
      default:
        return 'border-muted bg-muted/5'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'investigating':
        return <AlertTriangle className="h-4 w-4 text-warning" />
      case 'identified':
        return <Clock className="h-4 w-4 text-accent" />
      case 'resolved':
        return <CheckCircle className="h-4 w-4 text-success" />
      default:
        return <AlertTriangle className="h-4 w-4 text-muted-foreground" />
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-md">
      {activeIncidents.map((incident) => (
        <div
          key={incident.id}
          className={cn(
            'mb-2 border-2 rounded-lg shadow-lg animate-slide-up',
            getSeverityColor(incident.severity)
          )}
        >
          <div className="p-4">
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                {getStatusIcon(incident.status)}
                <span className="text-xs font-medium uppercase text-muted-foreground">
                  {incident.severity} Severity
                </span>
              </div>
              <button
                onClick={() => setDismissedIncidents([...dismissedIncidents, incident.id])}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            
            <h3 className="font-semibold text-foreground mb-1">
              {incident.title}
            </h3>
            
            <p className="text-sm text-muted-foreground mb-3">
              {incident.description}
            </p>
            
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Last updated: {formatDateTime(incident.updated_at)}
              </span>
              
              <button
                onClick={() => setExpandedIncident(
                  expandedIncident === incident.id ? null : incident.id
                )}
                className="btn-ghost btn-sm inline-flex items-center gap-1"
              >
                <MessageSquare className="h-3 w-3" />
                {expandedIncident === incident.id ? 'Hide' : 'View'} Updates
              </button>
            </div>
            
            {expandedIncident === incident.id && (
              <div className="mt-3 pt-3 border-t border-border space-y-2">
                <h4 className="text-xs font-medium text-foreground uppercase">Updates</h4>
                {incident.communications.map((comm, index) => (
                  <div key={index} className="text-xs space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-foreground">{comm.author}</span>
                      <span className="text-muted-foreground">
                        {formatDateTime(comm.timestamp)}
                      </span>
                    </div>
                    <p className="text-muted-foreground">{comm.message}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function cn(...classes: string[]) {
  return classes.filter(Boolean).join(' ')
}
