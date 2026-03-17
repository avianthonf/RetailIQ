import axios, { AxiosInstance, AxiosError } from 'axios'
import { useAuthStore } from '@/stores/authStore'

// Create base axios instance
export const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request ID interceptor
apiClient.interceptors.request.use(
  (config) => {
    // Add correlation ID for tracking
    config.headers['X-Correlation-ID'] = crypto.randomUUID()
    
    // Add device metadata
    config.headers['X-Device-Platform'] = navigator.platform
    config.headers['X-Device-User-Agent'] = navigator.userAgent
    config.headers['X-App-Version'] = import.meta.env.VITE_APP_VERSION || '1.0.0'
    
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Auth interceptor
apiClient.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().accessToken
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for token refresh and error handling
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as any

    // Handle 401 Unauthorized
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        const authStore = useAuthStore.getState()
        if (authStore.refreshToken) {
          await authStore.refreshAccessToken()
          
          // Retry the original request with new token
          const token = useAuthStore.getState().accessToken
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${token}`
          }
          return apiClient(originalRequest)
        }
      } catch (refreshError) {
        // Refresh failed, logout user
        useAuthStore.getState().logout()
        return Promise.reject(refreshError)
      }
    }

    // Handle 429 Rate Limit
    if (error.response?.status === 429) {
      const retryAfter = error.response.headers['Retry-After']
      if (retryAfter) {
        // Convert seconds to milliseconds
        const delay = parseInt(retryAfter) * 1000
        await new Promise((resolve) => setTimeout(resolve, delay))
        return apiClient(originalRequest)
      }
    }

    return Promise.reject(error)
  }
)

// Export types for use in components
export interface ApiError {
  code: string
  message: string
  details?: any
}

// Helper function to extract error message
export const getApiError = (error: unknown): ApiError => {
  if (axios.isAxiosError(error) && error.response?.data?.error) {
    return error.response.data.error as ApiError
  }
  
  if (error instanceof Error) {
    return {
      code: 'UNKNOWN_ERROR',
      message: error.message,
    }
  }
  
  return {
    code: 'UNKNOWN_ERROR',
    message: 'An unexpected error occurred',
  }
}
