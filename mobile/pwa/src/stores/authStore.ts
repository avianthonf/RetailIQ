import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'
import { devtools } from 'zustand/middleware'
import { apiClient } from '@/lib/api/client'
import type { User, LoginResponse, RegisterResponse } from '@/types/api'

interface AuthState {
  // State
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  isMaintenance: boolean
  error: string | null

  // Actions
  login: (mobile: string, password: string) => Promise<void>
  register: (data: RegisterData) => Promise<void>
  verifyOTP: (mobile: string, otp: string) => Promise<void>
  logout: () => Promise<void>
  refreshAccessToken: () => Promise<void>
  checkMaintenance: () => Promise<void>
  clearError: () => void
}

interface RegisterData {
  mobile_number: string
  password: string
  full_name: string
  email?: string
  store_name?: string
  role?: 'owner' | 'staff'
}

export const useAuthStore = create<AuthState>()(
  devtools(
    persist(
      immer((set, get) => ({
        // Initial state
        user: null,
        accessToken: null,
        refreshToken: null,
        isAuthenticated: false,
        isLoading: false,
        isMaintenance: false,
        error: null,

        // Login action
        login: async (mobile: string, password: string) => {
          set((state) => {
            state.isLoading = true
            state.error = null
          })

          try {
            const response = await apiClient.post<LoginResponse>('/auth/login', {
              mobile_number: mobile,
              password,
            })

            const { user, access_token, refresh_token } = response.data.data

            set((state) => {
              state.user = user
              state.accessToken = access_token
              state.refreshToken = refresh_token
              state.isAuthenticated = true
              state.isLoading = false
            })

            // Set default auth header for future requests
            apiClient.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
          } catch (error: any) {
            set((state) => {
              state.isLoading = false
              state.error = error.response?.data?.error?.message || 'Login failed'
            })
            throw error
          }
        },

        // Register action
        register: async (data: RegisterData) => {
          set((state) => {
            state.isLoading = true
            state.error = null
          })

          try {
            await apiClient.post<RegisterResponse>('/auth/register', data)
            
            set((state) => {
              state.isLoading = false
            })
          } catch (error: any) {
            set((state) => {
              state.isLoading = false
              state.error = error.response?.data?.error?.message || 'Registration failed'
            })
            throw error
          }
        },

        // Verify OTP action
        verifyOTP: async (mobile: string, otp: string) => {
          set((state) => {
            state.isLoading = true
            state.error = null
          })

          try {
            const response = await apiClient.post<LoginResponse>('/auth/verify-otp', {
              mobile_number: mobile,
              otp,
            })

            const { user, access_token, refresh_token } = response.data.data

            set((state) => {
              state.user = user
              state.accessToken = access_token
              state.refreshToken = refresh_token
              state.isAuthenticated = true
              state.isLoading = false
            })

            // Set default auth header
            apiClient.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
          } catch (error: any) {
            set((state) => {
              state.isLoading = false
              state.error = error.response?.data?.error?.message || 'OTP verification failed'
            })
            throw error
          }
        },

        // Logout action
        logout: async () => {
          try {
            if (get().refreshToken) {
              await apiClient.delete('/auth/logout', {
                data: { refresh_token: get().refreshToken },
              })
            }
          } catch (error) {
            // Continue with logout even if API call fails
            console.error('Logout API failed:', error)
          }

          // Clear state
          set((state) => {
            state.user = null
            state.accessToken = null
            state.refreshToken = null
            state.isAuthenticated = false
            state.isLoading = false
            state.error = null
          })

          // Clear auth header
          delete apiClient.defaults.headers.common['Authorization']
        },

        // Refresh access token
        refreshAccessToken: async () => {
          const { refreshToken } = get()
          if (!refreshToken) {
            throw new Error('No refresh token available')
          }

          try {
            const response = await apiClient.post<{ data: { access_token: string; refresh_token: string } }>(
              '/auth/refresh',
              { refresh_token: refreshToken }
            )

            const { access_token, refresh_token: new_refresh_token } = response.data.data

            set((state) => {
              state.accessToken = access_token
              state.refreshToken = new_refresh_token
            })

            // Update auth header
            apiClient.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
          } catch (error) {
            // Refresh failed, logout user
            get().logout()
            throw error
          }
        },

        // Check maintenance status
        checkMaintenance: async () => {
          try {
            const response = await apiClient.get('/ops/maintenance')
            const maintenanceData = response.data.data
            
            set((state) => {
              state.isMaintenance = maintenanceData.system_status !== 'healthy'
            })
          } catch (error) {
            // If we can't check maintenance, assume not in maintenance
            set((state) => {
              state.isMaintenance = false
            })
          }
        },

        // Clear error
        clearError: () => {
          set((state) => {
            state.error = null
          })
        },
      })),
      {
        name: 'auth-storage',
        storage: createJSONStorage(() => localStorage),
        partialize: (state) => ({
          user: state.user,
          accessToken: state.accessToken,
          refreshToken: state.refreshToken,
          isAuthenticated: state.isAuthenticated,
        }),
      }
    ),
    {
      name: 'auth-store',
    }
  )
)
