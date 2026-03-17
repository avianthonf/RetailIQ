import { useState, useEffect, FormEvent } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { ArrowLeft, AlertCircle, RefreshCw } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'

export function OTPPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { verifyOTP, isLoading, error, clearError } = useAuthStore()
  
  const [otp, setOtp] = useState(['', '', '', '', '', ''])
  const [resendTimer, setResendTimer] = useState(30)
  const [canResend, setCanResend] = useState(false)
  
  const mobile = location.state?.mobile || ''

  useEffect(() => {
    if (!mobile) {
      navigate('/auth/login')
    }
  }, [mobile, navigate])

  useEffect(() => {
    if (resendTimer > 0) {
      const timer = setTimeout(() => setResendTimer(resendTimer - 1), 1000)
      return () => clearTimeout(timer)
    } else {
      setCanResend(true)
    }
  }, [resendTimer])

  const handleOtpChange = (index: number, value: string) => {
    if (value.length > 1) return
    
    const newOtp = [...otp]
    newOtp[index] = value
    setOtp(newOtp)

    // Auto-focus next input
    if (value && index < 5) {
      const nextInput = document.getElementById(`otp-${index + 1}`) as HTMLInputElement
      nextInput?.focus()
    }
  }

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !otp[index] && index > 0) {
      const prevInput = document.getElementById(`otp-${index - 1}`) as HTMLInputElement
      prevInput?.focus()
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault()
    const pastedData = e.clipboardData.getData('text').slice(0, 6)
    const newOtp = pastedData.split('')
    setOtp([...newOtp, ...Array(6 - newOtp.length).fill('')])
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const otpString = otp.join('')
    
    if (otpString.length !== 6) {
      return
    }

    clearError()
    
    try {
      await verifyOTP(mobile, otpString)
      navigate('/dashboard')
    } catch (err) {
      // Error is handled in store
    }
  }

  const handleResend = async () => {
    if (!canResend) return
    
    setCanResend(false)
    setResendTimer(30)
    setOtp(['', '', '', '', '', ''])
    
    // TODO: Call resend OTP API
    console.log('Resending OTP to:', mobile)
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <Link to="/auth/login" className="inline-flex items-center text-muted-foreground hover:text-foreground mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Link>
          <h1 className="text-3xl font-bold text-foreground">Verify OTP</h1>
          <p className="text-muted-foreground mt-2">
            Enter the 6-digit code sent to {mobile}
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 bg-error/10 border border-error/20 rounded-lg flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-error flex-shrink-0 mt-0.5" />
            <p className="text-sm text-error">{error}</p>
          </div>
        )}

        {/* OTP Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <div className="flex justify-center gap-2 sm:gap-3">
              {otp.map((digit, index) => (
                <input
                  key={index}
                  id={`otp-${index}`}
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleOtpChange(index, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(index, e)}
                  onPaste={index === 0 ? handlePaste : undefined}
                  className="w-12 h-12 text-center text-lg font-semibold border-2 border-input rounded-lg focus:border-primary focus:outline-none"
                  required
                />
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading || otp.join('').length !== 6}
            className="btn-primary btn-md w-full"
          >
            {isLoading ? 'Verifying...' : 'Verify OTP'}
          </button>
        </form>

        {/* Resend OTP */}
        <div className="mt-6 text-center">
          <button
            type="button"
            onClick={handleResend}
            disabled={!canResend}
            className="text-sm text-primary hover:underline disabled:text-muted-foreground disabled:cursor-not-allowed inline-flex items-center gap-2"
          >
            {canResend ? (
              <>
                <RefreshCw className="h-4 w-4" />
                Resend OTP
              </>
            ) : (
              `Resend OTP in ${resendTimer}s`
            )}
          </button>
        </div>

        {/* Development Note */}
        {import.meta.env.DEV && (
          <div className="mt-8 p-4 bg-muted rounded-lg">
            <p className="text-xs text-muted-foreground">
              <strong>Development Mode:</strong> Check the backend console for the OTP code.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
