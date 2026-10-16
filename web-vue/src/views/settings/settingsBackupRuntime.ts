import { ref } from 'vue'

import { settingsApi, type BackupItem, type BackupState, type BackupTestResult } from '@/api/settings'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useOperationProgressRuntime } from '@/composables/useOperationProgressRuntime'
import type { usePageRuntime } from '@/composables/usePageRuntime'
import { usePageQuery } from '@/composables/usePageQuery'
import { useToast } from '@/composables/useToast'
import { errorMessage } from '@/lib/errorMessage'

type SettingsBackupRuntimeOptions = {
  runtime: ReturnType<typeof usePageRuntime>
  requestKey: string
  requireSavedSettings: (actionLabel: string) => boolean
}

export function useSettingsBackupRuntime(options: SettingsBackupRuntimeOptions) {
  const backupsLoaded = ref(false)
  const backupBusy = ref('')
  const backupLoading = ref(false)
  const backupState = ref<BackupState | null>(null)
  const backupItems = ref<BackupItem[]>([])
  const backupTestResult = ref<BackupTestResult | null>(null)
  const toast = useToast()
  const confirmDialog = useConfirmDialog()
  const progressRuntime = useOperationProgressRuntime()
  const operationProgress = progressRuntime.state

  const backupsQuery = usePageQuery({
    runtime: options.runtime,
    key: options.requestKey,
    loading: backupLoading,
    errorMessage: 'Failed to load backup history',
  })

  async function loadBackups() {
    await backupsQuery.run(
      () => settingsApi.listBackups(),
      {
        apply: (response) => {
          backupItems.value = Array.isArray(response.items) ? response.items : []
          backupState.value = response.state || null
          backupsLoaded.value = true
        },
        onError: (message) => {
          backupItems.value = []
          backupState.value = null
          toast.error(message)
        },
      },
    )
  }

  async function testBackupConnection() {
    if (!options.requireSavedSettings('test the backup connection')) return
    const confirmed = await confirmDialog.ask({
      title: 'Confirm backup connection test',
      message: 'This will test the saved R2/backup storage configuration and may access an external storage service. Continue?',
      confirmText: 'Start test',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    backupBusy.value = 'test'
    backupTestResult.value = null
    try {
      const response = await settingsApi.testBackup()
      backupTestResult.value = response.result
      if (response.result.ok) toast.success('Backup connection test passed')
      else toast.warning(response.result.error || 'Backup connection test failed')
    } catch (error) {
      const message = errorMessage(error, 'Backup connection test failed')
      backupTestResult.value = { ok: false, error: message }
      toast.error(message)
    } finally {
      backupBusy.value = ''
    }
  }

  async function runBackupNow() {
    if (!options.requireSavedSettings('run an immediate backup')) return
    const confirmed = await confirmDialog.ask({
      title: 'Confirm immediate backup',
      message: 'This will write the current configuration and runtime data to backup storage and may upload data externally. Continue?',
      confirmText: 'Start backup',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    backupBusy.value = 'run'
    await progressRuntime.start({
      title: 'Immediate backup',
      subtitle: 'R2 / backup storage',
      message: 'Packing and uploading runtime data...',
    })
    try {
      const response = await settingsApi.runBackup()
      progressRuntime.record({ label: 'Refreshing history', message: 'Backup complete; refreshing history...' })
      await loadBackups()
      progressRuntime.succeed(`Backup complete: ${response.result.key}`)
    } catch (error) {
      progressRuntime.fail(errorMessage(error, 'Backup failed'))
    } finally {
      backupBusy.value = ''
    }
  }

  async function deleteBackupItem(item: BackupItem) {
    const confirmed = await confirmDialog.ask({
      title: 'Delete backup',
      message: `Delete backup ${item.name || item.key}?`,
      confirmText: 'Delete',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    backupBusy.value = item.key
    await progressRuntime.start({
      title: 'Delete backup',
      subtitle: item.name || item.key,
      message: 'Deleting backup file...',
    })
    try {
      await settingsApi.deleteBackup(item.key)
      progressRuntime.record({ label: 'Refreshing history', message: 'Backup deleted; refreshing history...' })
      await loadBackups()
      progressRuntime.succeed('Backup deleted')
    } catch (error) {
      progressRuntime.fail(errorMessage(error, 'Failed to delete backup'))
    } finally {
      backupBusy.value = ''
    }
  }

  function invalidate() {
    backupsQuery.invalidate()
    backupsLoaded.value = false
  }

  return {
    backupsLoaded,
    backupBusy,
    backupLoading,
    backupState,
    backupItems,
    backupTestResult,
    operationProgress,
    closeOperationProgress: progressRuntime.close,
    loadBackups,
    testBackupConnection,
    runBackupNow,
    deleteBackupItem,
    invalidate,
  }
}
