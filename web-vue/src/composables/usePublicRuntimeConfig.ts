import { computed, ref } from 'vue'
import { settingsApi, type PublicThirdPartyAppsView } from '@/api/settings'

const sharedView = ref<PublicThirdPartyAppsView | null>(null)
const isLoading = ref(false)
const loadError = ref<Error | null>(null)

const PUBLIC_RUNTIME_TTL_MS = 30_000
let loadedAt = 0
let generation = 0
let inflight: {
  generation: number
  promise: Promise<PublicThirdPartyAppsView | null>
} | null = null

function normalizeBaseUrl(value: string) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  try {
    const base = typeof window !== 'undefined' ? window.location.origin : undefined
    return new URL(raw, base).toString().replace(/\/+$/, '')
  } catch {
    return raw.replace(/\/+$/, '')
  }
}

function fallbackBaseUrl() {
  const configured = String(import.meta.env.VITE_API_URL || '').trim()
  if (configured) return normalizeBaseUrl(configured)
  return typeof window !== 'undefined' ? normalizeBaseUrl(window.location.origin) : ''
}

export function usePublicRuntimeConfig() {
  const apiBaseUrl = computed(() => (
    normalizeBaseUrl(sharedView.value?.api_base_url || '') || fallbackBaseUrl()
  ))
  const thirdPartyApps = computed(() => sharedView.value?.third_party_apps || null)

  async function loadPublicRuntimeConfig(force = false) {
    if (!force && sharedView.value && Date.now() - loadedAt < PUBLIC_RUNTIME_TTL_MS) {
      return sharedView.value
    }
    if (!force && inflight?.generation === generation) return inflight.promise
    if (force) generation += 1

    const requestGeneration = generation
    isLoading.value = true
    const request = (async () => {
      try {
        const response = await settingsApi.getThirdPartyApps()
        if (requestGeneration === generation) {
          sharedView.value = response
          loadedAt = Date.now()
          loadError.value = null
        }
        return requestGeneration === generation ? response : sharedView.value
      } catch (error) {
        if (requestGeneration === generation) {
          loadError.value = error instanceof Error ? error : new Error('Failed to load public runtime config')
        }
        return sharedView.value
      }
    })()
    inflight = { generation: requestGeneration, promise: request }

    try {
      return await request
    } finally {
      if (inflight?.promise === request) {
        inflight = null
        isLoading.value = false
      }
    }
  }

  return {
    apiBaseUrl,
    thirdPartyApps,
    isLoading,
    loadError,
    loadPublicRuntimeConfig,
  }
}
