import { computed, ref, shallowRef, watch } from 'vue'
import {
  promptsApi,
  type PromptLibraryItem,
  type PromptLibraryView,
  type PromptSourcePayload,
} from '@/api/prompts'
import { firstPromptPreviewUrl, markPromptPreviewBroken } from '@/lib/promptAssets'
import {
  ALL_PROMPT_CATEGORY,
  ALL_PROMPT_SOURCE,
  categoryOptionsFor,
  filterPromptItems,
  promptSourceLabel,
} from '@/lib/promptLibrary'

type PromptMutationAction = '' | 'toggle-source' | 'refresh-all'

const snapshot = shallowRef<PromptLibraryView | null>(null)
const loading = ref(false)
const loadError = ref('')
const mutationBusy = ref(false)
const mutationAction = ref<PromptMutationAction>('')
const mutationSourceId = ref('')

const prompts = computed(() => snapshot.value?.items ?? [])
const sources = computed(() => snapshot.value?.sources ?? [])
const synced = computed(() => snapshot.value?.synced ?? false)

let loadGeneration = 0
let currentLoad: Promise<boolean> | null = null

function commitSnapshot(result: PromptLibraryView) {
  snapshot.value = result
  loadError.value = ''
}

export async function preloadPromptLibrary(force = false) {
  if (mutationBusy.value) return false
  if (!force && snapshot.value !== null) return true
  if (!force && currentLoad) return currentLoad

  const generation = ++loadGeneration
  loading.value = true
  loadError.value = ''
  const request = (async () => {
    try {
      const result = await promptsApi.list()
      if (generation !== loadGeneration || mutationBusy.value) return false
      commitSnapshot(result)
      return true
    } catch (error: any) {
      if (generation === loadGeneration && !mutationBusy.value) {
        loadError.value = error?.message || '提示词加载失败，请稍后重试。'
      }
      return false
    } finally {
      if (generation === loadGeneration) loading.value = false
    }
  })()
  currentLoad = request
  try {
    return await request
  } finally {
    if (currentLoad === request) currentLoad = null
  }
}

async function mutatePromptLibrary(
  action: Exclude<PromptMutationAction, ''>,
  sourceId: string,
  request: () => Promise<PromptLibraryView>,
) {
  if (mutationBusy.value) throw new Error('提示词源正在更新，请稍后再试。')

  mutationBusy.value = true
  mutationAction.value = action
  mutationSourceId.value = sourceId
  loadGeneration += 1
  loading.value = false
  try {
    const result = await request()
    commitSnapshot(result)
    return result
  } finally {
    mutationBusy.value = false
    mutationAction.value = ''
    mutationSourceId.value = ''
  }
}

export function updatePromptSource(id: string, payload: PromptSourcePayload) {
  return mutatePromptLibrary('toggle-source', id, () => promptsApi.updateSource(id, payload))
}

export function refreshPromptSources() {
  return mutatePromptLibrary('refresh-all', '', () => promptsApi.refreshSources())
}

export function usePromptLibraryRuntime() {
  const keyword = ref('')
  const sourceFilter = ref(ALL_PROMPT_SOURCE)
  const categoryFilter = ref(ALL_PROMPT_CATEGORY)
  const brokenPreviewUrls = ref<Set<string>>(new Set())

  const enabledSourceCount = computed(() => snapshot.value?.enabled_source_count ?? 0)
  const sourceOptions = computed(() => [
    { label: '全部来源', value: ALL_PROMPT_SOURCE },
    ...sources.value
      .filter((source) => source.enabled)
      .map((source) => ({
        label: promptSourceLabel(source),
        value: source.id,
      })),
  ])
  const scopedForCategory = computed(() => filterPromptItems(prompts.value, {
    keyword: '',
    sourceId: sourceFilter.value,
    category: ALL_PROMPT_CATEGORY,
  }))
  const categoryOptions = computed(() => categoryOptionsFor(scopedForCategory.value))
  const filteredPrompts = computed(() => filterPromptItems(prompts.value, {
    keyword: keyword.value,
    sourceId: sourceFilter.value,
    category: categoryFilter.value,
  }))

  function promptPreviewUrl(item: PromptLibraryItem) {
    return firstPromptPreviewUrl(item, brokenPreviewUrls.value)
  }

  function handlePreviewError(event: Event, item: PromptLibraryItem) {
    const primaryUrl = item.preview || item.reference_image_urls[0] || ''
    markPromptPreviewBroken(event, primaryUrl, (url) => {
      brokenPreviewUrls.value = new Set([...brokenPreviewUrls.value, url])
    })
  }

  watch(sourceFilter, () => {
    categoryFilter.value = ALL_PROMPT_CATEGORY
  })

  return {
    snapshot,
    loading,
    loadError,
    mutationBusy,
    mutationAction,
    mutationSourceId,
    prompts,
    sources,
    synced,
    keyword,
    sourceFilter,
    categoryFilter,
    enabledSourceCount,
    sourceOptions,
    categoryOptions,
    filteredPrompts,
    promptPreviewUrl,
    handlePreviewError,
    loadPrompts: preloadPromptLibrary,
    updatePromptSource,
    refreshPromptSources,
  }
}
