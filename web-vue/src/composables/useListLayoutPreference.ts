import { computed, ref } from 'vue'

import { getStringPreference, preferenceKeys, setStringPreference } from '@/lib/preferences'

export type ListLayoutMode = 'workspace' | 'page'

function normalizeListLayoutMode(value: unknown): ListLayoutMode {
  return value === 'page' ? 'page' : 'workspace'
}

const storedListLayoutMode = ref<ListLayoutMode>(normalizeListLayoutMode(
  getStringPreference(preferenceKeys.listLayoutMode, 'workspace'),
))

export function useListLayoutPreference() {
  function setListLayoutMode(value: ListLayoutMode) {
    const next = normalizeListLayoutMode(value)
    storedListLayoutMode.value = next
    setStringPreference(preferenceKeys.listLayoutMode, next)
  }

  const listLayoutMode = computed<ListLayoutMode>({
    get: () => storedListLayoutMode.value,
    set: setListLayoutMode,
  })
  const isWorkspaceLayout = computed(() => storedListLayoutMode.value === 'workspace')

  return {
    listLayoutMode,
    isWorkspaceLayout,
    setListLayoutMode,
  }
}
