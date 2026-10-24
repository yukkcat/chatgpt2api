import { ref, type Ref } from 'vue'

import { galleryApi, type GalleryFile, type ImageStorageStats } from '@/api/gallery'
import { saveBlob } from '@/lib/downloads'
import { errorMessage } from '@/lib/errorMessage'
import { formatMb } from '@/views/gallery/galleryView'
import type { PageRuntime } from '@/composables/usePageRuntime'
import { usePageQuery } from '@/composables/usePageQuery'
import { useOperationProgressRuntime } from '@/composables/useOperationProgressRuntime'

type ConfirmDialog = {
  ask: (options: {
    title: string
    message: string
    confirmText?: string
    cancelText?: string
  }) => Promise<boolean>
}

type Toast = {
  success: (message: string, title?: string) => void
  error: (message: string, title?: string) => void
}

type GalleryOperationsRuntimeOptions = {
  runtime: PageRuntime
  confirmDialog: ConfirmDialog
  toast: Toast
  files: Ref<GalleryFile[]>
  currentPage: Ref<number>
  storageStats: Ref<ImageStorageStats | null>
  selectedPaths: Ref<Set<string>>
  loadGallery: () => Promise<void>
  closePreviewIfPath: (path: string) => void
  closeTagEditorIfPath: (path: string) => void
  clearSelection: () => void
}

export function useGalleryOperationsRuntime(options: GalleryOperationsRuntimeOptions) {
  const isStorageModalOpen = ref(false)
  const isStorageBusy = ref(false)
  const storageActionMessage = ref('')
  const storageActionError = ref('')
  const targetFreeMb = ref('500')
  const batchBusy = ref(false)
  const genboxPushBusyPath = ref<string | null>(null)
  const progressRuntime = useOperationProgressRuntime()
  const operationProgress = progressRuntime.state

  const storageStatsQuery = usePageQuery({
    runtime: options.runtime,
    key: 'gallery:storage',
    error: storageActionError,
    errorMessage: 'Failed to refresh storage statistics',
  })

  async function refreshStorageStats(optionsOverride: { lock?: boolean; silent?: boolean } = {}) {
    if (!options.runtime.isActive.value) return
    const shouldLock = optionsOverride.lock !== false
    if (shouldLock) isStorageBusy.value = true
    if (!optionsOverride.silent) storageActionError.value = ''
    await storageStatsQuery.run(
      () => galleryApi.getStorage(),
      {
        apply: (nextStats) => {
          options.storageStats.value = nextStats
        },
        onError: (message) => {
          options.toast.error(message, 'Refresh failed')
        },
        onSettled: (latest) => {
          if (shouldLock && latest) isStorageBusy.value = false
        },
        silentError: optionsOverride.silent,
      },
    )
  }

  function openStorageModal() {
    isStorageModalOpen.value = true
    storageActionMessage.value = ''
    storageActionError.value = ''
    void refreshStorageStats()
  }

  function closeStorageModal() {
    if (isStorageBusy.value) return
    isStorageModalOpen.value = false
  }

  async function handleCompressStorage() {
    const confirmed = await options.confirmDialog.ask({
      title: 'Compress images',
      message: 'This will attempt to compress local images to free up space. It may take some time. Continue?',
      confirmText: 'Start compression',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    isStorageBusy.value = true
    storageActionMessage.value = 'Compressing images...'
    storageActionError.value = ''
    try {
      const result = await galleryApi.compressStorage()
      storageActionMessage.value = result.message
      options.toast.success(storageActionMessage.value, 'Compression complete')
      await Promise.all([refreshStorageStats({ lock: false }), options.loadGallery()])
    } catch (error: any) {
      storageActionError.value = error?.message || 'Failed to compress images'
      options.toast.error(storageActionError.value, 'Compression failed')
    } finally {
      isStorageBusy.value = false
    }
  }

  async function handleCleanupExpired() {
    const confirmed = await options.confirmDialog.ask({
      title: 'Remove expired images',
      message: 'This will remove local copies of expired images. Gallery records with a WebDAV copy will be retained. This action cannot be undone. Continue?',
      confirmText: 'Remove expired',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    isStorageBusy.value = true
    storageActionMessage.value = 'Removing expired images...'
    storageActionError.value = ''
    try {
      const result = await galleryApi.cleanupExpired()
      storageActionMessage.value = result.message
      options.toast.success(storageActionMessage.value, 'Cleanup complete')
      await Promise.all([refreshStorageStats({ lock: false }), options.loadGallery()])
    } catch (error: any) {
      storageActionError.value = error?.message || 'Failed to remove expired images'
      options.toast.error(storageActionError.value, 'Cleanup failed')
    } finally {
      isStorageBusy.value = false
    }
  }

  async function handleCleanupToTarget(dryRun: boolean) {
    const target = Number(targetFreeMb.value)
    if (!Number.isFinite(target) || target < 1) {
      storageActionError.value = 'Enter a valid target free-space value.'
      options.toast.error(storageActionError.value, 'Invalid parameter')
      return
    }

    const normalizedTarget = Math.floor(target)
    if (!dryRun) {
      const confirmed = await options.confirmDialog.ask({
        title: 'Clean up to target free space',
        message: `Cleanup will start with the oldest images and continue until free disk space is as close as possible to ${formatMb(normalizedTarget)}. This action cannot be undone. Continue?`,
        confirmText: 'Start cleanup',
        cancelText: 'Cancel',
      })
      if (!confirmed) return
    }

    isStorageBusy.value = true
    storageActionMessage.value = dryRun ? 'Estimating removable images...' : 'Cleaning up to the target free-space level...'
    storageActionError.value = ''
    try {
      const result = await galleryApi.cleanupToTarget(normalizedTarget, dryRun)
      storageActionMessage.value = result.message
      if (dryRun) {
        options.toast.success(storageActionMessage.value, 'Estimate complete')
        await refreshStorageStats({ lock: false })
      } else {
        options.toast.success(storageActionMessage.value, 'Cleanup complete')
        await Promise.all([refreshStorageStats({ lock: false }), options.loadGallery()])
      }
    } catch (error: any) {
      storageActionError.value = error?.message || 'Failed to clean up to target free space'
      options.toast.error(storageActionError.value, 'Cleanup failed')
    } finally {
      isStorageBusy.value = false
    }
  }

  async function deleteImages(paths: string[], file: GalleryFile | null = null) {
    if (paths.length === 0) return
    const isBatch = paths.length > 1
    const confirmed = await options.confirmDialog.ask({
      title: isBatch ? 'Delete images' : 'Delete image',
      message: file
        ? `Are you sure you want to delete ${file.filename}? This action cannot be undone.`
        : `Are you sure you want to delete the ${paths.length} selected images? This action cannot be undone.`,
      confirmText: 'Delete',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    batchBusy.value = true
    await progressRuntime.start({
      title: isBatch ? 'Delete images' : 'Delete image',
      subtitle: file?.filename || `${paths.length} selected`,
      total: paths.length,
      message: isBatch ? 'Submitting bulk delete request...' : 'Submitting delete request...',
    })
    try {
      const result = await galleryApi.deleteFiles(paths)
      const removed = Number(result.removed || 0)
      progressRuntime.record({ label: 'Refresh list', message: 'Delete complete. Refreshing list...' })
      if (file) {
        options.selectedPaths.value.delete(file.path)
        options.selectedPaths.value = new Set(options.selectedPaths.value)
      } else {
        options.clearSelection()
      }
      paths.forEach((path) => {
        options.closePreviewIfPath(path)
        options.closeTagEditorIfPath(path)
      })
      if (paths.length === 1 && options.files.value.length === 1 && options.currentPage.value > 1) {
        options.currentPage.value -= 1
      } else {
        await options.loadGallery()
      }
      progressRuntime.succeed(isBatch ? `Deleted ${removed} images` : 'Image deleted', removed)
    } catch (error: any) {
      const message = error?.message || (isBatch ? 'Bulk image delete failed' : 'Failed to delete image')
      progressRuntime.fail(message)
    } finally {
      batchBusy.value = false
    }
  }

  function handleDelete(file: GalleryFile) {
    return deleteImages([file.path], file)
  }

  async function handleDeleteSelected() {
    const paths = Array.from(options.selectedPaths.value)
    return deleteImages(paths)
  }

  async function handleBatchDownload() {
    const paths = Array.from(options.selectedPaths.value)
    if (!paths.length) return

    batchBusy.value = true
    await progressRuntime.start({
      title: 'Download images',
      subtitle: `${paths.length} selected`,
      total: paths.length,
      message: 'Creating ZIP archive...',
    })
    try {
      const blob = await galleryApi.downloadZip(paths)
      progressRuntime.record({ label: 'Start download', message: 'ZIP created. Starting download...' })
      saveBlob(blob, `images_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.zip`)
      progressRuntime.succeed(`Packed ${paths.length} images`, paths.length)
    } catch (error: any) {
      const message = error?.message || 'Bulk image download failed'
      progressRuntime.fail(message)
    } finally {
      batchBusy.value = false
    }
  }

  async function handleGenBoxPush(file: GalleryFile) {
    if (genboxPushBusyPath.value) return
    genboxPushBusyPath.value = file.path
    try {
      const result = await galleryApi.pushToGenBox(file.path)
      options.toast.success(result.label, 'Push successful')
      await options.loadGallery()
    } catch (error) {
      options.toast.error(errorMessage(error, 'Failed to push to GenBox'), 'Push failed')
    } finally {
      genboxPushBusyPath.value = null
    }
  }

  function deactivate() {
    storageStatsQuery.invalidate()
    isStorageBusy.value = false
  }

  return {
    batchBusy,
    genboxPushBusyPath,
    isStorageModalOpen,
    isStorageBusy,
    storageActionMessage,
    storageActionError,
    targetFreeMb,
    operationProgress,
    closeOperationProgress: progressRuntime.close,
    refreshStorageStats,
    openStorageModal,
    closeStorageModal,
    handleCompressStorage,
    handleCleanupExpired,
    handleCleanupToTarget,
    handleDelete,
    handleDeleteSelected,
    handleBatchDownload,
    handleGenBoxPush,
    deactivate,
  }
}
