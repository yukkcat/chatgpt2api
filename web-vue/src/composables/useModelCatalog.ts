import { computed, ref } from 'vue'
import { modelsApi } from '@/api/models'
import type { ModelCatalogResponse } from '@/api/models'

const sharedCatalog = ref<ModelCatalogResponse | null>(null)
const loadError = ref<Error | null>(null)
const isLoading = ref(false)

const MODEL_CATALOG_TTL_MS = 30_000
let hasAuthoritativeCatalog = false
let catalogGeneration = 0
let loadedAt = 0
let inflight: {
  generation: number
  promise: Promise<ModelCatalogResponse | null>
} | null = null

function validateCatalog(payload: ModelCatalogResponse | null | undefined): ModelCatalogResponse {
  if (
    !payload
    || payload.object !== 'model_catalog'
    || payload.schema_version !== 1
    || !Array.isArray(payload.chat_models)
    || !Array.isArray(payload.image_models)
    || !Array.isArray(payload.all_models)
    || !payload.defaults
    || !payload.capabilities
    || !payload.source
  ) {
    throw new Error('Invalid model catalog response')
  }
  return payload
}

export function useModelCatalog() {
  const chatModels = computed(() => sharedCatalog.value?.chat_models || [])
  const imageModels = computed(() => sharedCatalog.value?.image_models || [])

  return {
    catalog: sharedCatalog,
    chatModels,
    imageModels,
    isLoading,
    loadError,
    loadModelCatalog,
  }
}

export async function loadModelCatalog(force = false) {
  if (force) invalidateModelCatalog()
  if (
    hasAuthoritativeCatalog
    && Date.now() - loadedAt < MODEL_CATALOG_TTL_MS
  ) return sharedCatalog.value
  if (inflight?.generation === catalogGeneration) return inflight.promise

  const generation = catalogGeneration
  isLoading.value = true
  const request = (async () => {
    try {
      const catalog = validateCatalog(await modelsApi.catalog())
      if (generation === catalogGeneration) {
        sharedCatalog.value = catalog
        loadError.value = null
        hasAuthoritativeCatalog = true
        loadedAt = Date.now()
      }
      return generation === catalogGeneration ? catalog : sharedCatalog.value
    } catch (error) {
      if (generation === catalogGeneration) {
        loadError.value = error instanceof Error ? error : new Error('Failed to load model catalog')
        hasAuthoritativeCatalog = false
        console.error('Failed to load model catalog:', error)
      }
      return sharedCatalog.value
    }
  })()
  inflight = { generation, promise: request }

  try {
    return await request
  } finally {
    if (inflight?.promise === request) {
      isLoading.value = false
      inflight = null
    }
  }
}

export function invalidateModelCatalog() {
  catalogGeneration += 1
  hasAuthoritativeCatalog = false
  loadedAt = 0
  loadError.value = null
}
