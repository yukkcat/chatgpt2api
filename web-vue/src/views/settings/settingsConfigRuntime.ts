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
    log_retention_days: settings.log_retention_days,
    image_retention_days: settings.image_retention_days,
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
    `按当前保留策略检测到 ${result.total_removed} 项可清理数据，预计释放 ${formatBytes(result.total_size_bytes)}。`,
    `日志：${result.logs.removed || 0} 条，保留 ${result.logs.retention_days} 天。`,
    `图片：${result.images.removed || 0} 个，保留 ${result.images.retention_days} 天。`,
    '是否立即删除这些过期数据？',
  ].join('\n')
}

function cleanupDoneMessage(result: RetentionCleanupResult): string {
  return `清理完成：删除 ${result.total_removed || 0} 项，释放 ${formatBytes(result.total_size_bytes)}`
}

function accountCleanupMessage(result: AccountCleanupResult): string {
  return [
    `按当前账号策略检测到 ${result.total_removed} 个可移除账号。`,
    `确认鉴权失效账号：${result.invalid || 0} 个。`,
    `额度耗尽账号：${result.rate_limited || 0} 个。`,
    '是否立即移除这些账号？正常账号不会受影响。',
  ].join('\n')
}

function accountCleanupDoneMessage(result: AccountCleanupResult): string {
  return `账号清理完成：移除 ${result.total_removed || 0} 个账号`
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
    errorMessage: '设置加载失败',
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
      toast.warning(`请先保存设置，再${actionLabel}`)
      return false
    }
    return true
  }

  async function persistSettings(showToast = false) {
    if (!localSettings.value) {
      throw new Error('设置尚未加载，请刷新设置后重试')
    }
    if (!savedSettingsBaseline.value) {
      throw new Error('设置基线尚未加载，请刷新设置后重试')
    }
    const payload = prepareSettingsPatch(localSettings.value, savedSettingsBaseline.value)
    const result = await settingsStore.updateSettingsPatch(payload)
    applySettings(result.settings, false)
    await options.afterSave?.()
    if (showToast) toast.success('设置保存成功')
    return result
  }

  async function offerRetentionCleanup() {
    if (!localSettings.value) return
    const payload = cleanupRequest(localSettings.value)
    let preview: RetentionCleanupResult
    try {
      preview = await settingsApi.previewRetentionCleanup(payload)
    } catch (error) {
      toast.warning(`清理检测失败：${errorMessage(error, '无法检测日志和图片清理项')}`)
      return
    }
    if (!hasRetentionCleanupTargets(preview)) return

    const confirmed = await confirmDialog.ask({
      title: '检测到可清理数据',
      message: retentionCleanupMessage(preview),
      confirmText: '立即清理',
      cancelText: '稍后处理',
    })
    if (!confirmed) return

    try {
      const result = await settingsApi.runRetentionCleanup(payload)
      toast.success(cleanupDoneMessage(result))
    } catch (error) {
      toast.error(`清理失败：${errorMessage(error, '无法删除过期日志和图片')}`)
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
      toast.warning(`账号清理检测失败：${errorMessage(error, '无法检测可移除账号')}`)
      return
    }
    if (!hasAccountCleanupTargets(preview)) return

    const confirmed = await confirmDialog.ask({
      title: '检测到可移除账号',
      message: accountCleanupMessage(preview),
      confirmText: '立即移除',
      cancelText: '稍后处理',
    })
    if (!confirmed) return

    try {
      const result = await settingsApi.runAccountCleanup(payload)
      toast.success(accountCleanupDoneMessage(result))
    } catch (error) {
      toast.error(`账号清理失败：${errorMessage(error, '无法移除账号')}`)
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
      title: '确认保存系统设置',
      message: '即将保存当前系统设置，可能影响接口地址、并发、存储和备份策略。是否继续？',
      confirmText: '保存',
      cancelText: '取消',
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
            ? '配置已被其他操作更新，当前编辑已保留；已刷新版本，请确认后再次保存'
            : '配置已被其他操作更新，当前编辑已保留；刷新版本失败，请手动刷新后重试',
        )
        return
      }
      toast.error(errorMessage(error, '保存失败'))
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
