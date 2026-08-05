import { watch, type Ref } from 'vue'

import { usePageDebouncedAction, usePageVisibilityReload } from '@/composables/usePageQuery'
import type { PageRuntime } from '@/composables/usePageRuntime'
import {
  getNumberPreference,
  getStringPreference,
  preferenceKeys,
  setNumberPreference,
  setStringPreference,
} from '@/lib/preferences'

type AccountsViewMode = 'list' | 'cards'

type AccountPageLifecycleRuntimeOptions = {
  runtime: PageRuntime
  viewMode: Ref<AccountsViewMode>
  pageSize: Ref<number>
  currentPage: Ref<number>
  keyword: Ref<string>
  statusFilter: Ref<string>
  groupFilter: Ref<string>
  pageSizeDefault: number
  pageSizeOptions: readonly number[]
  reloadTimerKey: string
  loadData: (options?: { silentErrorToast?: boolean }) => Promise<void> | void
  loadGroups: (options?: { silentErrorToast?: boolean }) => Promise<void> | void
  invalidateData: () => void
  invalidateGroups: () => void
  clearSelection: () => void
  clearPageSelection: () => void
  shouldSkipRefresh: () => boolean
}

export function useAccountPageLifecycleRuntime(options: AccountPageLifecycleRuntimeOptions) {
  let ready = false
  const listReloadDebounce = usePageDebouncedAction({
    runtime: options.runtime,
    key: options.reloadTimerKey,
    delayMs: 0,
    shouldRun: () => ready,
    action: () => {
      void options.loadData({ silentErrorToast: true })
    },
  })

  function scheduleListReload(delay = 0) {
    listReloadDebounce.schedule(delay)
  }

  function clearListReloadTimer() {
    listReloadDebounce.clear()
  }

  function applyPreferences() {
    const storedViewMode = getStringPreference(preferenceKeys.accountsViewMode)
    if (storedViewMode === 'list' || storedViewMode === 'cards') {
      options.viewMode.value = storedViewMode
    }
    options.pageSize.value = getNumberPreference(preferenceKeys.accountsPageSize, options.pageSizeDefault, {
      allowed: options.pageSizeOptions,
    })
  }

  function setViewMode(mode: AccountsViewMode) {
    options.viewMode.value = mode
    setStringPreference(preferenceKeys.accountsViewMode, mode)
  }

  function invalidate() {
    options.invalidateData()
    options.invalidateGroups()
    clearListReloadTimer()
  }

  async function refresh(silentErrorToast = true) {
    await Promise.all([
      options.loadData({ silentErrorToast }),
      options.loadGroups({ silentErrorToast }),
    ])
  }

  watch(
    [options.keyword, options.statusFilter, options.groupFilter],
    () => {
      options.clearSelection()
      if (options.currentPage.value !== 1) {
        options.currentPage.value = 1
        return
      }
      scheduleListReload(200)
    },
  )

  watch(options.pageSize, () => {
    setNumberPreference(preferenceKeys.accountsPageSize, options.pageSize.value)
    options.clearSelection()
    if (options.currentPage.value !== 1) {
      options.currentPage.value = 1
      return
    }
    scheduleListReload()
  })

  watch(options.currentPage, () => {
    options.clearPageSelection()
  })

  options.runtime.onActivate(({ initial }) => {
    if (initial) {
      void (async () => {
        applyPreferences()
        await refresh(true)
        ready = true
      })()
      return
    }
    if (options.shouldSkipRefresh()) return
    void refresh(true)
  })

  options.runtime.onDeactivate(() => {
    invalidate()
  })

  usePageVisibilityReload({
    runtime: options.runtime,
    invalidate,
    reload: () => refresh(true),
    shouldReload: () => !options.shouldSkipRefresh(),
  })

  return {
    setViewMode,
    scheduleListReload,
    clearListReloadTimer,
    invalidate,
    refresh,
  }
}
