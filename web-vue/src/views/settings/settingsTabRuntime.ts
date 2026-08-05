import { watch, type Ref } from 'vue'

import type { usePageRuntime } from '@/composables/usePageRuntime'
import { usePageVisibilityReload } from '@/composables/usePageQuery'

type SettingsTabLoader = {
  tabs: readonly string[]
  loaded: Ref<boolean>
  load: () => Promise<void> | void
}

type SettingsTabRuntimeOptions = {
  runtime: ReturnType<typeof usePageRuntime>
  activeTab: Ref<string>
  reloadSettings: () => Promise<void> | void
  shouldSkipActivateReload: () => boolean
  tabLoaders: SettingsTabLoader[]
  invalidators: Array<() => void>
}

export function useSettingsTabRuntime(options: SettingsTabRuntimeOptions) {
  function invalidate() {
    options.invalidators.forEach((invalidateRuntime) => {
      invalidateRuntime()
    })
  }

  async function loadActiveTabData(force = false) {
    const activeLoader = options.tabLoaders.find((loader) => loader.tabs.includes(options.activeTab.value))
    if (!activeLoader) return
    if (!force && activeLoader.loaded.value) return
    await activeLoader.load()
  }

  options.runtime.onActivate(({ initial }) => {
    if (initial) {
      void (async () => {
        await options.reloadSettings()
        await loadActiveTabData()
      })()
      return
    }
    if (options.shouldSkipActivateReload()) return
    void options.reloadSettings()
    void loadActiveTabData(true)
  })

  watch(options.activeTab, () => {
    if (!options.runtime.canRun.value) return
    void loadActiveTabData()
  })

  options.runtime.onDeactivate(() => {
    invalidate()
  })

  usePageVisibilityReload({
    runtime: options.runtime,
    invalidate,
    reload: async () => {
      await options.reloadSettings()
      await loadActiveTabData(true)
    },
    shouldReload: () => !options.shouldSkipActivateReload(),
  })

  return {
    invalidate,
    loadActiveTabData,
  }
}
