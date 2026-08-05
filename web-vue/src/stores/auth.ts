import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  authApi,
  type AuthCapabilities,
  type AuthCapability,
  type AuthSubject,
  type AuthView,
} from '@/api/auth'
import { getAuthToken } from '@/api/client'

const AUTH_CACHE_MS = 60000

function emptyCapabilities(): AuthCapabilities {
  return { admin_console: false, studio: false }
}

export const useAuthStore = defineStore('auth', () => {
  const isLoggedIn = ref(false)
  const isLoading = ref(false)
  const subject = ref<AuthSubject | null>(null)
  const capabilities = ref<AuthCapabilities>(emptyCapabilities())
  const homeRoute = ref<AuthView['home_route']>('/login')
  const version = ref('')
  const lastCheckedAt = ref(0)
  let checkPromise: Promise<boolean> | null = null

  const role = computed(() => subject.value?.role || '')
  const subjectId = computed(() => subject.value?.id || '')
  const name = computed(() => subject.value?.name || '')
  const isAdmin = computed(() => capabilities.value.admin_console)

  function hasCapability(capability: AuthCapability) {
    return capabilities.value[capability] === true
  }

  function applyStatus(status: AuthView) {
    if (!status.authenticated || !status.subject) {
      clearIdentity()
      version.value = status.version
      return false
    }
    isLoggedIn.value = true
    subject.value = status.subject
    capabilities.value = {
      admin_console: status.capabilities.admin_console === true,
      studio: status.capabilities.studio === true,
    }
    homeRoute.value = status.home_route
    version.value = status.version
    return true
  }

  function clearIdentity() {
    isLoggedIn.value = false
    subject.value = null
    capabilities.value = emptyCapabilities()
    homeRoute.value = '/login'
  }

  async function login(password: string) {
    isLoading.value = true
    try {
      const status = await authApi.login({ password })
      const authenticated = applyStatus(status)
      lastCheckedAt.value = Date.now()
      return authenticated
    } catch (error) {
      clearIdentity()
      throw error
    } finally {
      isLoading.value = false
    }
  }

  async function logout() {
    try {
      await authApi.logout()
    } finally {
      clearIdentity()
      lastCheckedAt.value = 0
    }
  }

  async function checkAuth() {
    if (!getAuthToken()) {
      clearIdentity()
      lastCheckedAt.value = 0
      checkPromise = null
      return false
    }
    const now = Date.now()
    if (now - lastCheckedAt.value < AUTH_CACHE_MS) {
      return isLoggedIn.value
    }
    if (checkPromise) {
      return checkPromise
    }
    try {
      checkPromise = (async () => {
        const status = await authApi.checkAuth()
        const authenticated = applyStatus(status)
        lastCheckedAt.value = Date.now()
        return authenticated
      })()
      return await checkPromise
    } catch {
      clearIdentity()
      lastCheckedAt.value = 0
      return false
    } finally {
      checkPromise = null
    }
  }

  return {
    isLoggedIn,
    isLoading,
    subject,
    capabilities,
    homeRoute,
    version,
    role,
    subjectId,
    name,
    isAdmin,
    hasCapability,
    login,
    logout,
    checkAuth,
    clearIdentity,
  }
})
