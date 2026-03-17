import { Link } from 'react-router-dom'
import { ArrowRight, Package, TrendingUp, Users, Shield } from 'lucide-react'

export function WelcomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-primary to-primary/80 text-white">
      <div className="container mx-auto px-4 py-16 lg:py-24">
        <div className="max-w-4xl mx-auto text-center">
          {/* Logo and Title */}
          <div className="mb-12">
            <h1 className="text-4xl lg:text-6xl font-bold mb-4">
              RetailIQ
            </h1>
            <p className="text-xl lg:text-2xl text-primary-foreground/90">
              Planet-scale Retail Operations Intelligence
            </p>
          </div>

          {/* Features Grid */}
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8 mb-16">
            <div className="bg-white/10 backdrop-blur-sm rounded-xl p-6">
              <Package className="h-12 w-12 mb-4 mx-auto" />
              <h3 className="font-semibold mb-2">Smart Inventory</h3>
              <p className="text-sm text-primary-foreground/80">
                Real-time stock tracking and AI-powered demand forecasting
              </p>
            </div>
            <div className="bg-white/10 backdrop-blur-sm rounded-xl p-6">
              <TrendingUp className="h-12 w-12 mb-4 mx-auto" />
              <h3 className="font-semibold mb-2">Dynamic Pricing</h3>
              <p className="text-sm text-primary-foreground/80">
                Automated pricing strategies based on market intelligence
              </p>
            </div>
            <div className="bg-white/10 backdrop-blur-sm rounded-xl p-6">
              <Users className="h-12 w-12 mb-4 mx-auto" />
              <h3 className="font-semibold mb-2">Customer Loyalty</h3>
              <p className="text-sm text-primary-foreground/80">
                Built-in loyalty programs and customer relationship management
              </p>
            </div>
            <div className="bg-white/10 backdrop-blur-sm rounded-xl p-6">
              <Shield className="h-12 w-12 mb-4 mx-auto" />
              <h3 className="font-semibold mb-2">Enterprise Security</h3>
              <p className="text-sm text-primary-foreground/80">
                Bank-grade security with role-based access control
              </p>
            </div>
          </div>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/auth/register"
              className="btn bg-white text-primary hover:bg-white/90 btn-lg inline-flex items-center gap-2"
            >
              Get Started Free
              <ArrowRight className="h-5 w-5" />
            </Link>
            <Link
              to="/auth/login"
              className="btn bg-transparent border-2 border-white text-white hover:bg-white hover:text-primary btn-lg"
            >
              Sign In
            </Link>
          </div>

          {/* Trust Indicators */}
          <div className="mt-16 pt-8 border-t border-white/20">
            <p className="text-sm text-primary-foreground/60 mb-4">
              Trusted by 10,000+ retailers across India
            </p>
            <div className="flex justify-center items-center gap-8 text-sm text-primary-foreground/40">
              <span>✓ GST Compliant</span>
              <span>✓ UPI Ready</span>
              <span>✓ 99.9% Uptime</span>
              <span>✓ 24/7 Support</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
