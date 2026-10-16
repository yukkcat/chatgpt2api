import { ref } from 'vue'

import { settingsApi, type ImageStorageTestResult } from '@/api/settings'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useOperationProgressRuntime } from '@/composables/useOperationProgressRuntime'
import { useToast } from '@/composables/useToast'
import { errorMessage } from '@/lib/errorMessage'

type SettingsImageStorageRuntimeOptions = {
  requireSavedSettings: (actionLabel: string) => boolean
}

export function useSettingsImageStorageRuntime(options: SettingsImageStorageRuntimeOptions) {
  const imageStorageBusy = ref('')
  const imageStorageTestResult = ref<ImageStorageTestResult | null>(null)
  const toast = useToast()
  const confirmDialog = useConfirmDialog()
  const progressRuntime = useOperationProgressRuntime()
  const operationProgress = progressRuntime.state

  async function testImageStorageConnection() {
    if (!options.requireSavedSettings('test WebDAV')) return
    const confirmed = await confirmDialog.ask({
      title: 'Confirm WebDAV test',
      message: 'A WebDAV connection test will use the saved image storage settings and may contact an external storage service. Continue?',
      confirmText: 'Start test',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    imageStorageBusy.value = 'test'
    imageStorageTestResult.value = null
    try {
      const response = await settingsApi.testImageStorage()
      imageStorageTestResult.value = response.result
      if (response.result.ok) toast.success('WebDAV test passed.')
      else toast.warning(response.result.error || 'WebDAV test failed.')
    } catch (error) {
      const message = errorMessage(error, 'WebDAV test failed.')
      imageStorageTestResult.value = { ok: false, error: message }
      toast.error(message)
    } finally {
      imageStorageBusy.value = ''
    }
  }

  async function syncImageStorageFiles() {
    if (!options.requireSavedSettings('sync local images')) return
    const confirmed = await confirmDialog.ask({
      title: 'Confirm image storage sync',
      message: 'Local images will be scanned and synced to the configured WebDAV storage. This may upload data externally. Continue?',
      confirmText: 'Start sync',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    imageStorageBusy.value = 'sync'
    await progressRuntime.start({
      title: 'Sync all images',
      subtitle: 'Local → WebDAV',
      message: 'Scanning and uploading local images…',
    })
    try {
      const response = await settingsApi.syncImageStorage()
      const summary = `Uploaded ${response.result.uploaded}, skipped ${response.result.skipped}, failed ${response.result.failed}`
      if (response.result.failed > 0) progressRuntime.warn(summary)
      else progressRuntime.succeed(summary)
    } catch (error) {
      progressRuntime.fail(errorMessage(error, 'Failed to sync images.'))
    } finally {
      imageStorageBusy.value = ''
    }
  }

  return {
    imageStorageBusy,
    imageStorageTestResult,
    operationProgress,
    closeOperationProgress: progressRuntime.close,
    testImageStorageConnection,
    syncImageStorageFiles,
  }
}
