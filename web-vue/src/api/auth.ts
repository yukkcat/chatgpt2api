import apiClient, { clearAuthToken, setAuthToken } from './client'

export type AuthRole = 'admin' | 'user' | 'unknown'
export type AuthCapability = 'admin_console' | 'studio'

export interface AuthSubject {
  id: string
  name: string
  role: AuthRole
}

export interface AuthCapabilities {
  admin_console: boolean
  studio: boolean
}

export interface AuthView {
  schema_version: 1
  authenticated: boolean
  version: string
  subject: AuthSubject | null
  capabilities: AuthCapabilities
  home_route: '/login' | '/' | '/studio'
}

export interface LoginRequest {
  password: string
}

export const authApi = {
  async login(data: LoginRequest) {
    setAuthToken(data.password)
    try {
      return await apiClient.post<never, AuthView>('/auth/login')
    } catch (error) {
      clearAuthToken()
      throw error
    }
  },

  logout: () => {
    clearAuthToken()
    return Promise.resolve({ ok: true })
  },

  checkAuth: () => apiClient.get<never, AuthView>('/auth/status', { timeout: 8000 }),
}
