import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import {
  prepareSettingsForEdit,
  prepareSettingsPatch,
  settingsApi,
  type AccountCleanupRequest,
  type AccountCleanupResult,
  type RetentionCleanupRequest,
  type RetentionCleanupResult,
} from '@/api/settings'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { usePageQuery } from '@/composables/usePageQuery'
import type { usePageRuntime } from '@/composables/usePageRuntime'
import { errorMessage } from '@/lib/errorMessage'
import { useSettingsStore } from '@/stores/settings'
import { useToast } from '@/composables/useToast'
import type { Settings } from '@/types/api'
import { settingsFingerprint } from '@/views/settings/settingsView'

type SettingsConfigRuntimeOptions = {
  runtime: ReturnType<typeof usePageRuntime>
  requestKey: string
  afterReload?: () => void | Promise<void>
  afterSave?: () => void | Promise<void>
}

function formatBytes(value: unknown): string {
  const bytes = Number(value || 0)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = bytes
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`
}

function cleanupRequest(settings: Settings): RetentionCleanupRequest {
  return {
    log_retention_hours: settings.log_retention_hours,
    image_retention_hours: settings.image_retention_hours,
  }
}

function accountCleanupRequest(settings: Settings): AccountCleanupRequest {
  return {
    auto_remove_invalid_accounts: Boolean(settings.auto_remove_invalid_accounts),
    auto_remove_rate_limited_accounts: Boolean(settings.auto_remove_rate_limited_accounts),
  }
}

function hasRetentionCleanupTargets(result: RetentionCleanupResult): boolean {
  return Number(result.total_removed || 0) > 0
}

function hasAccountCleanupTargets(result: AccountCleanupResult): boolean {
  return Number(result.total_removed || 0) > 0
}

function retentionCleanupMessage(result: RetentionCleanupResult): string {
  return [
    `The current retention policy found ${result.total_removed} items to clean up, freeing an estimated ${formatBytes(result.total_size_bytes)}.`,
    `Logs: ${result.logs.removed || 0} entries; retain for ${result.logs.retention_hours} hours.`,
    `Images: ${result.images.removed || 0}; retain for ${result.images.retention_hours} hours.`,
    'Delete these expired items now?',
  ].join('\n')
}

function cleanupDoneMessage(result: RetentionCleanupResult): string {
  return `Cleanup complete: removed ${result.total_removed || 0} items, freed ${formatBytes(result.total_size_bytes)}`
}

function accountCleanupMessage(result: AccountCleanupResult): string {
  return [
    `The current account policy found ${result.total_removed} accounts that can be removed.`,
    `Accounts with confirmed invalid authentication: ${result.invalid || 0}.`,
    `Accounts with exhausted quota: ${result.rate_limited || 0}.`,
    'Remove these accounts now? Normal accounts will not be affected.',
  ].join('\n')
}

function accountCleanupDoneMessage(result: AccountCleanupResult): string {
  return `Account cleanup complete: removed ${result.total_removed || 0} accounts`
}

export function useSettingsConfigRuntime(options: SettingsConfigRuntimeOptions) {
  const settingsStore = useSettingsStore()
  const { settings, isLoading: settingsLoading } = storeToRefs(settingsStore)
  const toast = useToast()
  const confirmDialog = useConfirmDialog()

  const localSettings = ref<Settings | null>(null)
  const savedSettingsBaseline = ref<Settings | null>(null)
  const activeSettingsTab = ref('basic')
  const isSaving = ref(false)
  const settingsLoadError = ref('')

  const settingsReloadQuery = usePageQuery({
    runtime: options.runtime,
    key: options.requestKey,
    loading: settingsLoading,
    error: settingsLoadError,
    errorMessage: 'Failed to load settings',
  })

  const hasUnsavedSettings = computed(() => {
    if (!localSettings.value || !savedSettingsBaseline.value) return false
    return settingsFingerprint(localSettings.value) !== settingsFingerprint(savedSettingsBaseline.value)
  })

  function applySettings(value: Settings | null | undefined, preserveUnsaved = true) {
    if (!value) return
    const next = prepareSettingsForEdit(value)
    if (
      preserveUnsaved &&
      localSettings.value &&
      savedSettingsBaseline.value &&
      hasUnsavedSettings.value
    ) {
      return
    }
    localSettings.value = next
    savedSettingsBaseline.value = prepareSettingsForEdit(next)
  }

  watch(settings, (value) => {
    applySettings(value)
  }, { immediate: true })

  function requireSavedSettings(actionLabel: string) {
    if (!localSettings.value) return false
    if (hasUnsavedSettings.value) {
      toast.warning(`Save your settings before you ${actionLabel}`)
      return false
    }
    return true
  }

  async function persistSettings(showToast = false) {
    if (!localSettings.value) {
      throw new Error('Settings have not loaded. Refresh the settings and try again.')
    }
    if (!savedSettingsBaseline.value) {
      throw new Error('The settings baseline has not loaded. Refresh the settings and try again.')
    }
    const payload = prepareSettingsPatch(localSettings.value, savedSettingsBaseline.value)
    const result = await settingsStore.updateSettingsPatch(payload)
    applySettings(result.settings, false)
    await options.afterSave?.()
    if (showToast) toast.success('Settings saved')
    return result
  }

  async function offerRetentionCleanup() {
    if (!localSettings.value) return
    const payload = cleanupRequest(localSettings.value)
    let preview: RetentionCleanupResult
    try {
      preview = await settingsApi.previewRetentionCleanup(payload)
    } catch (error) {
      toast.warning(`Cleanup preview failed: ${errorMessage(error, 'Unable to check for expired logs and images')}`)
      return
    }
    if (!hasRetentionCleanupTargets(preview)) return

    const confirmed = await confirmDialog.ask({
      title: 'Items can be cleaned up',
      message: retentionCleanupMessage(preview),
      confirmText: 'Clean up now',
      cancelText: 'Later',
    })
    if (!confirmed) return

    try {
      const result = await settingsApi.runRetentionCleanup(payload)
      toast.success(cleanupDoneMessage(result))
    } catch (error) {
      toast.error(`Cleanup failed: ${errorMessage(error, 'Unable to delete expired logs and images')}`)
    }
  }

  async function offerAccountCleanup() {
    if (!localSettings.value) return
    const payload = accountCleanupRequest(localSettings.value)
    if (!payload.auto_remove_invalid_accounts && !payload.auto_remove_rate_limited_accounts) return

    let preview: AccountCleanupResult
    try {
      preview = await settingsApi.previewAccountCleanup(payload)
    } catch (error) {
      toast.warning(`Account cleanup preview failed: ${errorMessage(error, 'Unable to check for removable accounts')}`)
      return
    }
    if (!hasAccountCleanupTargets(preview)) return

    const confirmed = await confirmDialog.ask({
      title: 'Accounts can be removed',
      message: accountCleanupMessage(preview),
      confirmText: 'Remove now',
      cancelText: 'Later',
    })
    if (!confirmed) return

    try {
      const result = await settingsApi.runAccountCleanup(payload)
      toast.success(accountCleanupDoneMessage(result))
    } catch (error) {
      toast.error(`Account cleanup failed: ${errorMessage(error, 'Unable to remove accounts')}`)
    }
  }

  async function reloadSettings() {
    await settingsReloadQuery.run(
      async () => {
        await settingsStore.loadSettings()
        await options.afterReload?.()
      },
      {
        onError: (message) => {
          toast.error(message)
        },
      },
    )
  }

  async function handleSave() {
    if (!localSettings.value) return
    const confirmed = await confirmDialog.ask({
      title: 'Confirm system settings',
      message: 'This will save the current system settings and may affect API addresses, concurrency, storage, and backup policies. Continue?',
      confirmText: 'Save',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    isSaving.value = true
    try {
      await persistSettings(true)
      await offerAccountCleanup()
      await offerRetentionCleanup()
    } catch (error) {
      if ((error as { status?: number })?.status === 409) {
        let revisionRefreshed = false
        try {
          await settingsStore.loadSettings()
          revisionRefreshed = true
        } catch {
          // Keep the local edits even when the follow-up refresh fails.
        }
        toast.warning(
          revisionRefreshed
            ? 'The configuration was updated elsewhere. Your edits are preserved and the latest version was loaded. Review and save again.'
            : 'The configuration was updated elsewhere. Your edits are preserved, but the latest version could not be loaded. Refresh and try again.',
        )
        return
      }
      toast.error(errorMessage(error, 'Failed to save settings'))
    } finally {
      isSaving.value = false
    }
  }

  function invalidate() {
    settingsReloadQuery.invalidate()
    settingsLoadError.value = ''
  }

  return {
    settingsStore,
    settingsLoading,
    localSettings,
    activeSettingsTab,
    isSaving,
    settingsLoadError,
    hasUnsavedSettings,
    requireSavedSettings,
    persistSettings,
    reloadSettings,
    handleSave,
    invalidate,
  }
}
