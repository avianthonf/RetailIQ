import { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface KpiCardProps {
  title: string
  value: string
  change: number
  changeType: 'increase' | 'decrease'
  icon: LucideIcon
  color: 'primary' | 'secondary' | 'accent' | 'success' | 'warning' | 'error' | 'info'
  isLoading?: boolean
}

const colorVariants = {
  primary: 'bg-primary/10 text-primary',
  secondary: 'bg-secondary/10 text-secondary',
  accent: 'bg-accent/10 text-accent',
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
  error: 'bg-error/10 text-error',
  info: 'bg-info/10 text-info',
}

export function KpiCard({ 
  title, 
  value, 
  change, 
  changeType, 
  icon: Icon, 
  color,
  isLoading 
}: KpiCardProps) {
  return (
    <div className="card p-4">
      <div className="flex items-start justify-between mb-3">
        <div className={cn('p-2 rounded-lg', colorVariants[color])}>
          <Icon className="h-5 w-5" />
        </div>
        <span
          className={cn(
            'inline-flex items-center text-xs font-medium',
            changeType === 'increase' ? 'text-success' : 'text-error'
          )}
        >
          {changeType === 'increase' ? '↑' : '↓'} {Math.abs(change)}%
        </span>
      </div>
      
      <div className="space-y-1">
        <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
        <p className="text-2xl font-bold text-foreground">
          {isLoading ? (
            <span className="inline-block h-8 w-20 bg-muted animate-pulse rounded" />
          ) : (
            value
          )}
        </p>
      </div>
      
      {/* Mini sparkline placeholder */}
      <div className="mt-3 h-8 flex items-end gap-0.5">
        {isLoading ? (
          <div className="w-full h-full bg-muted animate-pulse rounded" />
        ) : (
          Array.from({ length: 12 }).map((_, i) => (
            <div
              key={i}
              className={cn(
                'flex-1 rounded-t-sm',
                changeType === 'increase' ? 'bg-success/20' : 'bg-error/20'
              )}
              style={{
                height: `${Math.random() * 100}%`,
              }}
            />
          ))
        )}
      </div>
    </div>
  )
}
