import { AlertTriangle } from 'lucide-react'

export function MaintenanceBanner() {
  return (
    <div className="bg-error text-error-foreground px-4 py-3 flex items-center gap-3">
      <AlertTriangle className="h-5 w-5 flex-shrink-0" />
      <div className="flex-1">
        <p className="text-sm font-medium">System Maintenance</p>
        <p className="text-xs opacity-90">Some features may be temporarily unavailable.</p>
      </div>
    </div>
  )
}
