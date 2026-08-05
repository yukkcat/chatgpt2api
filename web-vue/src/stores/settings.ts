import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  prepareSettingsForEdit,
  PUBLIC_SETTINGS_CHANGED_EVENT,
  settingsApi,
  type SettingsPatch,
} from '@/api/settings'
import { loadModelCatalog } from '@/composables/useModelCatalog'
import type { Settings, SettingsMutationResult, SettingsView } from '@/types/api'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<Settings | null>(null)
  const view = ref<SettingsView | null>(null)
  const isLoading = ref(false)
  let loadSeq = 0

  async function loadSettings() {
    const seq = ++loadSeq
    isLoading.value = true
    try {
      const nextView = await settingsApi.get()
      if (seq === loadSeq) {
        view.value = nextView
        settings.value = prepareSettingsForEdit(nextView.settings)
      }
    } finally {
      if (seq === loadSeq) isLoading.value = false
    }
  }

  async function updateSettingsPatch(patch: SettingsPatch): Promise<SettingsMutationResult> {
    const revision = view.value?.revision
    if (!revision) {
      throw new Error('设置版本尚未加载，请刷新设置后重试')
    }
    loadSeq += 1
    const response = await settingsApi.updatePartial({
      ...patch,
      revision,
    })
    view.value = response
    settings.value = prepareSettingsForEdit(response.settings)
    isLoading.value = false
    void loadModelCatalog(true)
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event(PUBLIC_SETTINGS_CHANGED_EVENT))
    }
    return response
  }

  return {
    settings,
    view,
    isLoading,
    loadSettings,
    updateSettingsPatch,
  }
})
