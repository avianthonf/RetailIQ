import { useState } from 'react'
import { Settings, User, Store, Shield, Bell, Palette, Globe, HelpCircle, ChevronRight } from 'lucide-react'

export function SettingsPage() {
  const [activeSection, setActiveSection] = useState('profile')

  const settingsSections = [
    { id: 'profile', name: 'Profile', icon: User, description: 'Manage your account details' },
    { id: 'store', name: 'Store Settings', icon: Store, description: 'Configure store information' },
    { id: 'security', name: 'Security', icon: Shield, description: 'Password and authentication' },
    { id: 'notifications', name: 'Notifications', icon: Bell, description: 'Email and SMS preferences' },
    { id: 'appearance', name: 'Appearance', icon: Palette, description: 'Theme and display settings' },
    { id: 'language', name: 'Language', icon: Globe, description: 'Language and region' },
    { id: 'help', name: 'Help & Support', icon: HelpCircle, description: 'FAQs and contact support' },
  ]

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Settings</h1>
        <p className="text-muted-foreground">Manage your account and application settings</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Settings Navigation */}
        <div className="lg:col-span-1">
          <nav className="space-y-1">
            {settingsSections.map((section) => {
              const Icon = section.icon
              return (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={cn(
                    'w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors',
                    activeSection === section.id
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="flex-1 text-left">{section.name}</span>
                  <ChevronRight className="h-4 w-4" />
                </button>
              )
            })}
          </nav>
        </div>

        {/* Settings Content */}
        <div className="lg:col-span-3">
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">
                {settingsSections.find(s => s.id === activeSection)?.name}
              </h3>
              <p className="text-sm text-muted-foreground">
                {settingsSections.find(s => s.id === activeSection)?.description}
              </p>
            </div>
            
            <div className="card-content">
              {activeSection === 'profile' && (
                <div className="space-y-6">
                  <div className="flex items-center gap-4">
                    <div className="w-20 h-20 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-2xl font-bold">
                      JD
                    </div>
                    <div>
                      <button className="btn-primary btn-sm">Change Photo</button>
                      <p className="text-xs text-muted-foreground mt-1">JPG, PNG or GIF. Max 2MB</p>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Full Name</label>
                      <input type="text" defaultValue="John Doe" className="input" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Email</label>
                      <input type="email" defaultValue="john@example.com" className="input" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Phone</label>
                      <input type="tel" defaultValue="9876543210" className="input" disabled />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Role</label>
                      <input type="text" defaultValue="Owner" className="input" disabled />
                    </div>
                  </div>
                  
                  <div className="flex justify-end gap-2">
                    <button className="btn-outline btn-md">Cancel</button>
                    <button className="btn-primary btn-md">Save Changes</button>
                  </div>
                </div>
              )}

              {activeSection === 'store' && (
                <div className="space-y-6">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Store Name</label>
                      <input type="text" defaultValue="My Retail Store" className="input" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">GST Number</label>
                      <input type="text" defaultValue="12ABCDE3456F1ZV" className="input" />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="block text-sm font-medium text-foreground mb-2">Address</label>
                      <textarea className="input" rows={3} defaultValue="123 Main Street, Bangalore, Karnataka 560001" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Currency</label>
                      <select className="input">
                        <option>INR - Indian Rupee</option>
                        <option>USD - US Dollar</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Timezone</label>
                      <select className="input">
                        <option>Asia/Kolkata (IST)</option>
                        <option>Asia/Dubai (GST)</option>
                      </select>
                    </div>
                  </div>
                  
                  <div className="flex justify-end gap-2">
                    <button className="btn-outline btn-md">Cancel</button>
                    <button className="btn-primary btn-md">Save Changes</button>
                  </div>
                </div>
              )}

              {activeSection === 'security' && (
                <div className="space-y-6">
                  <div className="card p-4">
                    <h4 className="font-medium text-foreground mb-2">Change Password</h4>
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-foreground mb-2">Current Password</label>
                        <input type="password" className="input" />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-foreground mb-2">New Password</label>
                        <input type="password" className="input" />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-foreground mb-2">Confirm New Password</label>
                        <input type="password" className="input" />
                      </div>
                      <button className="btn-primary btn-md">Update Password</button>
                    </div>
                  </div>
                  
                  <div className="card p-4">
                    <h4 className="font-medium text-foreground mb-2">Two-Factor Authentication</h4>
                    <p className="text-sm text-muted-foreground mb-4">Add an extra layer of security to your account</p>
                    <button className="btn-outline btn-md">Enable 2FA</button>
                  </div>
                </div>
              )}

              {activeSection === 'notifications' && (
                <div className="space-y-6">
                  <div className="space-y-4">
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-foreground">Email Notifications</p>
                        <p className="text-sm text-muted-foreground">Receive updates via email</p>
                      </div>
                      <input type="checkbox" defaultChecked className="toggle" />
                    </label>
                    
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-foreground">SMS Notifications</p>
                        <p className="text-sm text-muted-foreground">Receive updates via SMS</p>
                      </div>
                      <input type="checkbox" defaultChecked className="toggle" />
                    </label>
                    
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-foreground">Low Stock Alerts</p>
                        <p className="text-sm text-muted-foreground">Get notified when inventory is low</p>
                      </div>
                      <input type="checkbox" defaultChecked className="toggle" />
                    </label>
                    
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-foreground">Sales Reports</p>
                        <p className="text-sm text-muted-foreground">Daily/weekly sales summaries</p>
                      </div>
                      <input type="checkbox" className="toggle" />
                    </label>
                  </div>
                  
                  <div className="flex justify-end">
                    <button className="btn-primary btn-md">Save Preferences</button>
                  </div>
                </div>
              )}

              {activeSection === 'appearance' && (
                <div className="space-y-6">
                  <div>
                    <h4 className="font-medium text-foreground mb-4">Theme</h4>
                    <div className="grid grid-cols-3 gap-4">
                      <label className="cursor-pointer">
                        <input type="radio" name="theme" defaultChecked className="sr-only peer" />
                        <div className="p-4 border-2 rounded-lg peer-checked:border-primary peer-checked:bg-primary/5">
                          <div className="w-full h-8 bg-white border rounded mb-2"></div>
                          <p className="text-sm text-center">Light</p>
                        </div>
                      </label>
                      <label className="cursor-pointer">
                        <input type="radio" name="theme" className="sr-only peer" />
                        <div className="p-4 border-2 rounded-lg peer-checked:border-primary peer-checked:bg-primary/5">
                          <div className="w-full h-8 bg-neutral-900 border rounded mb-2"></div>
                          <p className="text-sm text-center">Dark</p>
                        </div>
                      </label>
                      <label className="cursor-pointer">
                        <input type="radio" name="theme" className="sr-only peer" />
                        <div className="p-4 border-2 rounded-lg peer-checked:border-primary peer-checked:bg-primary/5">
                          <div className="w-full h-8 bg-gradient-to-r from-white to-neutral-900 border rounded mb-2"></div>
                          <p className="text-sm text-center">System</p>
                        </div>
                      </label>
                    </div>
                  </div>
                  
                  <div>
                    <h4 className="font-medium text-foreground mb-4">Font Size</h4>
                    <select className="input">
                      <option>Small</option>
                      <option selected>Medium</option>
                      <option>Large</option>
                    </select>
                  </div>
                </div>
              )}

              {activeSection === 'language' && (
                <div className="space-y-6">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-2">Language</label>
                    <select className="input">
                      <option selected>English (India)</option>
                      <option>हिन्दी</option>
                      <option>ಕನ್ನಡ</option>
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-2">Date Format</label>
                    <select className="input">
                      <option>DD/MM/YYYY</option>
                      <option>MM/DD/YYYY</option>
                      <option>YYYY-MM-DD</option>
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-2">Number Format</label>
                    <select className="input">
                      <option>1,234,567.89</option>
                      <option>1.234.567,89</option>
                      <option>1 234 567.89</option>
                    </select>
                  </div>
                </div>
              )}

              {activeSection === 'help' && (
                <div className="space-y-6">
                  <div className="text-center py-8">
                    <HelpCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                    <h3 className="text-lg font-semibold text-foreground mb-2">How can we help you?</h3>
                    <p className="text-muted-foreground mb-6">
                      Find answers, tutorials, and contact support
                    </p>
                    
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <button className="btn-outline btn-md">View Documentation</button>
                      <button className="btn-outline btn-md">Video Tutorials</button>
                      <button className="btn-outline btn-md">Contact Support</button>
                      <button className="btn-outline btn-md">Feature Requests</button>
                    </div>
                  </div>
                  
                  <div className="border-t pt-6">
                    <h4 className="font-medium text-foreground mb-4">Quick Links</h4>
                    <div className="space-y-2">
                      <a href="#" className="block text-sm text-primary hover:underline">Getting Started Guide</a>
                      <a href="#" className="block text-sm text-primary hover:underline">API Documentation</a>
                      <a href="#" className="block text-sm text-primary hover:underline">Privacy Policy</a>
                      <a href="#" className="block text-sm text-primary hover:underline">Terms of Service</a>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function cn(...classes: string[]) {
  return classes.filter(Boolean).join(' ')
}
