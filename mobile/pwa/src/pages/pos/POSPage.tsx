import { useState } from 'react'
import { CreditCard, ShoppingCart, Plus, Search, User, Tag } from 'lucide-react'

export function POSPage() {
  const [cartItems, setCartItems] = useState<any[]>([])

  return (
    <div className="min-h-screen bg-background">
      <div className="flex flex-col lg:flex-row h-[calc(100vh-8rem)] gap-4">
        {/* Left Side - Product Catalog */}
        <div className="flex-1 space-y-4">
          {/* Search Bar */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search products..."
              className="input pl-10"
            />
          </div>

          {/* Product Categories */}
          <div className="flex gap-2 overflow-x-auto pb-2">
            <button className="btn-primary btn-sm whitespace-nowrap">All</button>
            <button className="btn-outline btn-sm whitespace-nowrap">Beverages</button>
            <button className="btn-outline btn-sm whitespace-nowrap">Snacks</button>
            <button className="btn-outline btn-sm whitespace-nowrap">Dairy</button>
            <button className="btn-outline btn-sm whitespace-nowrap">Bakery</button>
          </div>

          {/* Products Grid */}
          <div className="card flex-1 overflow-hidden">
            <div className="card-header">
              <h3 className="card-title">Products</h3>
            </div>
            <div className="card-content p-0">
              <div className="text-center py-12">
                <ShoppingCart className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-foreground mb-2">POS Module Coming Soon</h3>
                <p className="text-muted-foreground mb-4">
                  Full point-of-sale features will be implemented in the next phase
                </p>
                <div className="text-sm text-muted-foreground space-y-1">
                  <p>✓ Product search and quick add</p>
                  <p>✓ Cart management</p>
                  <p>✓ Multiple payment methods</p>
                  <p>✓ Receipt generation</p>
                  <p>✓ Customer management</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Side - Cart */}
        <div className="w-full lg:w-96 space-y-4">
          {/* Customer Info */}
          <div className="card">
            <div className="card-content">
              <div className="flex items-center gap-2">
                <User className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Walk-in Customer</span>
                <button className="btn-ghost btn-sm ml-auto">Change</button>
              </div>
            </div>
          </div>

          {/* Cart Items */}
          <div className="card flex-1">
            <div className="card-header">
              <h3 className="card-title">Cart (0)</h3>
            </div>
            <div className="card-content">
              <div className="text-center py-8">
                <ShoppingCart className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">Cart is empty</p>
              </div>
            </div>
          </div>

          {/* Cart Summary */}
          <div className="card">
            <div className="card-content space-y-3">
              <div className="flex justify-between text-sm">
                <span>Subtotal</span>
                <span>₹0.00</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Tax (GST)</span>
                <span>₹0.00</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Discount</span>
                <span>₹0.00</span>
              </div>
              <div className="border-t pt-3">
                <div className="flex justify-between font-semibold">
                  <span>Total</span>
                  <span>₹0.00</span>
                </div>
              </div>
              
              <button className="btn-primary btn-md w-full" disabled>
                Proceed to Payment
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
