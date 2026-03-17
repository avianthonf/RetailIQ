import { useState, useEffect } from 'react'
import { Activity, Wifi, WifiOff, AlertCircle, TrendingUp } from 'lucide-react'
import { formatDateTime } from '@/lib/utils'
import type { LiveSignal } from '@/types/api'

// Mock WebSocket service
class WebSocketService {
  private ws: WebSocket | null = null
  private listeners: ((signal: LiveSignal) => void)[] = []
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000

  connect() {
    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:5000/ws'
    
    try {
      this.ws = new WebSocket(wsUrl)
      
      this.ws.onopen = () => {
        console.log('WebSocket connected')
        this.reconnectAttempts = 0
        this.notifyListeners({
          id: 'connection',
          type: 'connection',
          message: 'Connected to live signals',
          timestamp: new Date().toISOString(),
        })
      }
      
      this.ws.onmessage = (event) => {
        try {
          const signal = JSON.parse(event.data)
          this.notifyListeners(signal)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }
      
      this.ws.onclose = () => {
        console.log('WebSocket disconnected')
        this.notifyListeners({
          id: 'disconnection',
          type: 'connection',
          message: 'Disconnected from live signals',
          timestamp: new Date().toISOString(),
        })
        
        // Attempt to reconnect
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          setTimeout(() => {
            this.reconnectAttempts++
            this.connect()
          }, this.reconnectDelay * this.reconnectAttempts)
        }
      }
      
      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }
    } catch (error) {
      console.error('Failed to connect to WebSocket:', error)
      // Fallback to mock signals
      this.startMockSignals()
    }
  }
  
  disconnect() {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }
  
  subscribe(listener: (signal: LiveSignal) => void) {
    this.listeners.push(listener)
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener)
    }
  }
  
  private notifyListeners(signal: LiveSignal) {
    this.listeners.forEach(listener => listener(signal))
  }
  
  private startMockSignals() {
    // Mock signals for development
    const mockSignals: LiveSignal[] = [
      {
        id: '1',
        type: 'sale',
        message: 'New sale: ₹1,250 at Store #1',
        timestamp: new Date().toISOString(),
        metadata: { store_id: 1, amount: 1250 },
      },
      {
        id: '2',
        type: 'inventory',
        message: 'Stock updated: Premium Coffee Beans +50 units',
        timestamp: new Date().toISOString(),
        metadata: { product_id: 1, quantity: 50 },
      },
      {
        id: '3',
        type: 'customer',
        message: 'New customer registered: John Doe',
        timestamp: new Date().toISOString(),
        metadata: { customer_id: 123 },
      },
    ]
    
    let index = 0
    const interval = setInterval(() => {
      if (this.listeners.length > 0) {
        const signal = mockSignals[index % mockSignals.length]
        signal.id = Date.now().toString()
        signal.timestamp = new Date().toISOString()
        this.notifyListeners(signal)
        index++
      }
    }, 5000)
    
    // Cleanup on disconnect
    setTimeout(() => {
      clearInterval(interval)
    }, 60000)
  }
}

const wsService = new WebSocketService()

export function LiveSignalsLane() {
  const [signals, setSignals] = useState<LiveSignal[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')

  useEffect(() => {
    wsService.connect()
    
    const unsubscribe = wsService.subscribe((signal) => {
      if (signal.type === 'connection') {
        setIsConnected(signal.message.includes('Connected'))
        setConnectionStatus(signal.message.includes('Connected') ? 'connected' : 'disconnected')
      } else {
        setSignals(prev => [signal, ...prev.slice(0, 9)]) // Keep last 10 signals
      }
    })
    
    return () => {
      unsubscribe()
      wsService.disconnect()
    }
  }, [])

  const getSignalIcon = (type: string) => {
    switch (type) {
      case 'sale':
        return <TrendingUp className="h-4 w-4 text-success" />
      case 'inventory':
        return <Activity className="h-4 w-4 text-primary" />
      case 'customer':
        return <Activity className="h-4 w-4 text-secondary" />
      default:
        return <AlertCircle className="h-4 w-4 text-warning" />
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <div className="flex items-center justify-between">
          <h3 className="card-title">Live Signals</h3>
          <div className="flex items-center gap-2">
            <div className={cn(
              'w-2 h-2 rounded-full',
              isConnected ? 'bg-success' : 'bg-error'
            )} />
            <span className="text-xs text-muted-foreground">
              {connectionStatus}
            </span>
          </div>
        </div>
      </div>
      
      <div className="card-content p-0">
        {connectionStatus === 'connecting' ? (
          <div className="p-4 text-center">
            <Wifi className="h-8 w-8 text-muted-foreground mx-auto mb-2 animate-pulse" />
            <p className="text-sm text-muted-foreground">Connecting to live signals...</p>
          </div>
        ) : connectionStatus === 'disconnected' ? (
          <div className="p-4 text-center">
            <WifiOff className="h-8 w-8 text-error mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">Unable to connect to live signals</p>
            <button 
              onClick={() => wsService.connect()}
              className="btn-primary btn-sm mt-2"
            >
              Reconnect
            </button>
          </div>
        ) : signals.length === 0 ? (
          <div className="p-4 text-center">
            <Activity className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">Waiting for signals...</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {signals.map((signal) => (
              <div key={signal.id} className="p-3 hover:bg-muted/50 transition-colors animate-slide-down">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">
                    {getSignalIcon(signal.type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-foreground break-words">
                      {signal.message}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {formatDateTime(signal.timestamp)}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* Footer */}
      {isConnected && (
        <div className="card-footer">
          <button className="btn-ghost btn-sm w-full">
            View All Signals
          </button>
        </div>
      )}
    </div>
  )
}

function cn(...classes: string[]) {
  return classes.filter(Boolean).join(' ')
}
