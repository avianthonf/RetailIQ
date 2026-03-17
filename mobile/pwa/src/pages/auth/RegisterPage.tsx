import { useState, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Eye, EyeOff, AlertCircle, CheckCircle } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'

interface RegisterData {
  mobile_number: string
  password: string
  confirmPassword: string
  full_name: string
  email: string
  store_name: string
  role: 'owner' | 'staff'
}

export function RegisterPage() {
  const navigate = useNavigate()
  const { register, isLoading, error, clearError } = useAuthStore()
  
  const [step, setStep] = useState(1)
  const [formData, setFormData] = useState<RegisterData>({
    mobile_number: '',
    password: '',
    confirmPassword: '',
    full_name: '',
    email: '',
    store_name: '',
    role: 'owner',
  })
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

  const passwordRequirements = [
    { regex: /.{6,}/, text: 'At least 6 characters' },
    { regex: /[A-Z]/, text: 'One uppercase letter' },
    { regex: /[0-9]/, text: 'One number' },
  ]

  const isPasswordValid = passwordRequirements.every(req => req.regex.test(formData.password))
  const isStep1Valid = formData.mobile_number.length === 10 && isPasswordValid && formData.password === formData.confirmPassword
  const isStep2Valid = formData.full_name.trim() !== '' && formData.store_name.trim() !== ''

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (step === 1) {
      setStep(2)
      return
    }

    clearError()
    
    try {
      await register({
        mobile_number: formData.mobile_number,
        password: formData.password,
        full_name: formData.full_name,
        email: formData.email || undefined,
        store_name: formData.store_name,
        role: formData.role,
      })
      navigate('/auth/otp', { state: { mobile: formData.mobile_number } })
    } catch (err) {
      // Error is handled in store
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <Link to="/auth/welcome" className="inline-flex items-center text-muted-foreground hover:text-foreground mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Link>
          <h1 className="text-3xl font-bold text-foreground">Create Account</h1>
          <p className="text-muted-foreground mt-2">
            Step {step} of 2: {step === 1 ? 'Account Details' : 'Store Information'}
          </p>
        </div>

        {/* Progress Bar */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div className={`flex items-center ${step >= 1 ? 'text-primary' : 'text-muted-foreground'}`}>
              <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-sm font-medium ${
                step >= 1 ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground'
              }`}>
                {step > 1 ? <CheckCircle className="h-5 w-5" /> : '1'}
              </div>
              <span className="ml-2 text-sm font-medium">Account</span>
            </div>
            <div className={`flex-1 h-0.5 mx-2 ${step >= 2 ? 'bg-primary' : 'bg-muted'}`} />
            <div className={`flex items-center ${step >= 2 ? 'text-primary' : 'text-muted-foreground'}`}>
              <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-sm font-medium ${
                step >= 2 ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground'
              }`}>
                2
              </div>
              <span className="ml-2 text-sm font-medium">Store</span>
            </div>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 bg-error/10 border border-error/20 rounded-lg flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-error flex-shrink-0 mt-0.5" />
            <p className="text-sm text-error">{error}</p>
          </div>
        )}

        {/* Registration Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          {step === 1 ? (
            <>
              {/* Step 1: Account Details */}
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
                <p className="text-xs text-muted-foreground mt-1">
                  Enter your 10-digit mobile number
                </p>
              </div>

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-foreground mb-2">
                  Password
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    id="password"
                    name="password"
                    value={formData.password}
                    onChange={handleChange}
                    placeholder="Create a password"
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
                {formData.password && (
                  <div className="mt-2 space-y-1">
                    {passwordRequirements.map((req, index) => (
                      <div key={index} className="flex items-center gap-2 text-xs">
                        {req.regex.test(formData.password) ? (
                          <CheckCircle className="h-3 w-3 text-success" />
                        ) : (
                          <div className="h-3 w-3 rounded-full border border-muted-foreground" />
                        )}
                        <span className={req.regex.test(formData.password) ? 'text-success' : 'text-muted-foreground'}>
                          {req.text}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-foreground mb-2">
                  Confirm Password
                </label>
                <div className="relative">
                  <input
                    type={showConfirmPassword ? 'text' : 'password'}
                    id="confirmPassword"
                    name="confirmPassword"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    placeholder="Confirm your password"
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
                {formData.confirmPassword && formData.password !== formData.confirmPassword && (
                  <p className="text-xs text-error mt-1">Passwords do not match</p>
                )}
              </div>
            </>
          ) : (
            <>
              {/* Step 2: Store Information */}
              <div>
                <label htmlFor="full_name" className="block text-sm font-medium text-foreground mb-2">
                  Full Name
                </label>
                <input
                  type="text"
                  id="full_name"
                  name="full_name"
                  value={formData.full_name}
                  onChange={handleChange}
                  placeholder="John Doe"
                  className="input"
                  required
                />
              </div>

              <div>
                <label htmlFor="email" className="block text-sm font-medium text-foreground mb-2">
                  Email (Optional)
                </label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="john@example.com"
                  className="input"
                />
              </div>

              <div>
                <label htmlFor="store_name" className="block text-sm font-medium text-foreground mb-2">
                  Store Name
                </label>
                <input
                  type="text"
                  id="store_name"
                  name="store_name"
                  value={formData.store_name}
                  onChange={handleChange}
                  placeholder="My Retail Store"
                  className="input"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Account Type
                </label>
                <div className="grid grid-cols-2 gap-4">
                  <label className="relative">
                    <input
                      type="radio"
                      name="role"
                      value="owner"
                      checked={formData.role === 'owner'}
                      onChange={handleChange}
                      className="peer sr-only"
                    />
                    <div className="p-4 border-2 rounded-lg cursor-pointer peer-checked:border-primary peer-checked:bg-primary/5">
                      <p className="font-medium">Owner</p>
                      <p className="text-xs text-muted-foreground">Full access to all features</p>
                    </div>
                  </label>
                  <label className="relative">
                    <input
                      type="radio"
                      name="role"
                      value="staff"
                      checked={formData.role === 'staff'}
                      onChange={handleChange}
                      className="peer sr-only"
                    />
                    <div className="p-4 border-2 rounded-lg cursor-pointer peer-checked:border-primary peer-checked:bg-primary/5">
                      <p className="font-medium">Staff</p>
                      <p className="text-xs text-muted-foreground">Limited access</p>
                    </div>
                  </label>
                </div>
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={isLoading || (step === 1 ? !isStep1Valid : !isStep2Valid)}
            className="btn-primary btn-md w-full"
          >
            {isLoading ? 'Creating Account...' : step === 1 ? 'Continue' : 'Create Account'}
          </button>
        </form>

        {/* Footer Links */}
        <div className="mt-6 text-center">
          <p className="text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link to="/auth/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
