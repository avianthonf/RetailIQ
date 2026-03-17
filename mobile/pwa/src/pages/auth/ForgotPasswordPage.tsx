import { useState, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, AlertCircle, CheckCircle } from 'lucide-react'
import { apiClient } from '@/lib/api/client'

export function ForgotPasswordPage() {
  const navigate = useNavigate()
  
  const [mobile, setMobile] = useState('')
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')

    try {
      await apiClient.post('/auth/forgot-password', {
        mobile_number: mobile,
      })
      setIsSubmitted(true)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to send reset code')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <Link to="/auth/login" className="inline-flex items-center text-muted-foreground hover:text-foreground mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Login
          </Link>
          <h1 className="text-3xl font-bold text-foreground">Reset Password</h1>
          <p className="text-muted-foreground mt-2">
            Enter your mobile number to receive a reset code
          </p>
        </div>

        {!isSubmitted ? (
          <>
            {/* Error Alert */}
            {error && (
              <div className="mb-6 p-4 bg-error/10 border border-error/20 rounded-lg flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-error flex-shrink-0 mt-0.5" />
                <p className="text-sm text-error">{error}</p>
              </div>
            )}

            {/* Forgot Password Form */}
            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label htmlFor="mobile" className="block text-sm font-medium text-foreground mb-2">
                  Mobile Number
                </label>
                <input
                  type="tel"
                  id="mobile"
                  value={mobile}
                  onChange={(e) => setMobile(e.target.value)}
                  placeholder="9876543210"
                  className="input"
                  required
                  pattern="[6-9][0-9]{9}"
                  maxLength={10}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Enter your 10-digit mobile number
                </p>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="btn-primary btn-md w-full"
              >
                {isLoading ? 'Sending...' : 'Send Reset Code'}
              </button>
            </form>
          </>
        ) : (
          {/* Success State */}
          <div className="text-center py-8">
            <div className="w-16 h-16 bg-success/10 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="h-8 w-8 text-success" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Reset Code Sent
            </h2>
            <p className="text-muted-foreground mb-6">
              We've sent a password reset code to {mobile}. 
              Please check your messages and enter the code on the next screen.
            </p>
            <Link
              to="/auth/reset-password"
              state={{ mobile }}
              className="btn-primary btn-md"
            >
              Enter Reset Code
            </Link>
          </div>
        )}

        {/* Footer */}
        <div className="mt-6 text-center">
          <p className="text-sm text-muted-foreground">
            Remember your password?{' '}
            <Link to="/auth/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
