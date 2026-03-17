import { useState, FormEvent } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { ArrowLeft, Eye, EyeOff, AlertCircle } from 'lucide-react'
import { apiClient } from '@/lib/api/client'

export function ResetPasswordPage() {
  const navigate = useNavigate()
  const location = useLocation()
  
  const [formData, setFormData] = useState({
    mobile_number: location.state?.mobile || '',
    reset_code: '',
    new_password: '',
    confirm_password: '',
  })
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const passwordRequirements = [
    { regex: /.{6,}/, text: 'At least 6 characters' },
    { regex: /[A-Z]/, text: 'One uppercase letter' },
    { regex: /[0-9]/, text: 'One number' },
  ]

  const isPasswordValid = passwordRequirements.every(req => req.regex.test(formData.new_password))

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    
    if (formData.new_password !== formData.confirm_password) {
      setError('Passwords do not match')
      return
    }

    setIsLoading(true)
    setError('')

    try {
      await apiClient.post('/auth/reset-password', {
        mobile_number: formData.mobile_number,
        reset_code: formData.reset_code,
        new_password: formData.new_password,
      })
      
      navigate('/auth/login', {
        state: { message: 'Password reset successful. Please login with your new password.' }
      })
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to reset password')
    } finally {
      setIsLoading(false)
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <Link to="/auth/forgot-password" className="inline-flex items-center text-muted-foreground hover:text-foreground mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Link>
          <h1 className="text-3xl font-bold text-foreground">Set New Password</h1>
          <p className="text-muted-foreground mt-2">
            Enter your reset code and choose a new password
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 bg-error/10 border border-error/20 rounded-lg flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-error flex-shrink-0 mt-0.5" />
            <p className="text-sm text-error">{error}</p>
          </div>
        )}

        {/* Reset Password Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="mobile_number" className="block text-sm font-medium text-foreground mb-2">
              Mobile Number
            </label>
            <input
              type="tel"
              id="mobile_number"
              name="mobile_number"
              value={formData.mobile_number}
              onChange={handleChange}
              placeholder="9876543210"
              className="input"
              required
              pattern="[6-9][0-9]{9}"
              maxLength={10}
            />
          </div>

          <div>
            <label htmlFor="reset_code" className="block text-sm font-medium text-foreground mb-2">
              Reset Code
            </label>
            <input
              type="text"
              id="reset_code"
              name="reset_code"
              value={formData.reset_code}
              onChange={handleChange}
              placeholder="Enter 6-digit code"
              className="input"
              required
              maxLength={6}
              pattern="[0-9]{6}"
            />
          </div>

          <div>
            <label htmlFor="new_password" className="block text-sm font-medium text-foreground mb-2">
              New Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                id="new_password"
                name="new_password"
                value={formData.new_password}
                onChange={handleChange}
                placeholder="Enter new password"
                className="input pr-10"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
              </button>
            </div>
            
            {/* Password Requirements */}
            {formData.new_password && (
              <div className="mt-2 space-y-1">
                {passwordRequirements.map((req, index) => (
                  <div key={index} className="flex items-center gap-2 text-xs">
                    {req.regex.test(formData.new_password) ? (
                      <div className="h-3 w-3 rounded-full bg-success" />
                    ) : (
                      <div className="h-3 w-3 rounded-full border border-muted-foreground" />
                    )}
                    <span className={req.regex.test(formData.new_password) ? 'text-success' : 'text-muted-foreground'}>
                      {req.text}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <label htmlFor="confirm_password" className="block text-sm font-medium text-foreground mb-2">
              Confirm New Password
            </label>
            <div className="relative">
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                id="confirm_password"
                name="confirm_password"
                value={formData.confirm_password}
                onChange={handleChange}
                placeholder="Confirm new password"
                className="input pr-10"
                required
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showConfirmPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
              </button>
            </div>
            {formData.confirm_password && formData.new_password !== formData.confirm_password && (
              <p className="text-xs text-error mt-1">Passwords do not match</p>
            )}
          </div>

          <button
            type="submit"
            disabled={isLoading || !isPasswordValid || formData.new_password !== formData.confirm_password}
            className="btn-primary btn-md w-full"
          >
            {isLoading ? 'Resetting...' : 'Reset Password'}
          </button>
        </form>

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
