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
    checkboxLabel?: string
  }) => Promise<boolean | { confirmed: boolean; checked: boolean }>
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
    errorMessage: '刷新存储统计失败',
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
          options.toast.error(message, '刷新失败')
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
      title: '压缩图片',
      message: '将尝试压缩本地图片以释放空间。该操作可能需要一点时间，确定继续吗？',
      confirmText: '开始压缩',
      cancelText: '取消',
    })
    if (!confirmed) return

    isStorageBusy.value = true
    storageActionMessage.value = '正在压缩图片...'
    storageActionError.value = ''
    try {
      const result = await galleryApi.compressStorage()
      storageActionMessage.value = result.message
      options.toast.success(storageActionMessage.value, '压缩完成')
      await Promise.all([refreshStorageStats({ lock: false }), options.loadGallery()])
    } catch (error: any) {
      storageActionError.value = error?.message || '压缩图片失败'
      options.toast.error(storageActionError.value, '压缩失败')
    } finally {
      isStorageBusy.value = false
    }
  }

  async function handleCleanupExpired() {
    const confirmed = await options.confirmDialog.ask({
      title: '清理过期图片',
      message: '将清理已过期图片的本地副本；仍有 WebDAV 副本的图库记录会保留。此操作不可恢复，确定继续吗？',
      confirmText: '清理过期',
      cancelText: '取消',
    })
    if (!confirmed) return

    isStorageBusy.value = true
    storageActionMessage.value = '正在清理过期图片...'
    storageActionError.value = ''
    try {
      const result = await galleryApi.cleanupExpired()
      storageActionMessage.value = result.message
      options.toast.success(storageActionMessage.value, '清理完成')
      await Promise.all([refreshStorageStats({ lock: false }), options.loadGallery()])
    } catch (error: any) {
      storageActionError.value = error?.message || '清理过期图片失败'
      options.toast.error(storageActionError.value, '清理失败')
    } finally {
      isStorageBusy.value = false
    }
  }

  async function handleCleanupToTarget(dryRun: boolean) {
    const target = Number(targetFreeMb.value)
    if (!Number.isFinite(target) || target < 1) {
      storageActionError.value = '请输入有效的目标剩余空间。'
      options.toast.error(storageActionError.value, '参数错误')
      return
    }

    const normalizedTarget = Math.floor(target)
    if (!dryRun) {
      const confirmed = await options.confirmDialog.ask({
        title: '清理到目标空间',
        message: `将从旧图片开始清理，直到磁盘剩余空间尽量达到 ${formatMb(normalizedTarget)}。此操作不可恢复，确定继续吗？`,
        confirmText: '开始清理',
        cancelText: '取消',
      })
      if (!confirmed) return
    }

    isStorageBusy.value = true
    storageActionMessage.value = dryRun ? '正在预估可清理图片...' : '正在清理到目标剩余空间...'
    storageActionError.value = ''
    try {
      const result = await galleryApi.cleanupToTarget(normalizedTarget, dryRun)
      storageActionMessage.value = result.message
      if (dryRun) {
        options.toast.success(storageActionMessage.value, '预估完成')
        await refreshStorageStats({ lock: false })
      } else {
        options.toast.success(storageActionMessage.value, '清理完成')
        await Promise.all([refreshStorageStats({ lock: false }), options.loadGallery()])
      }
    } catch (error: any) {
      storageActionError.value = error?.message || '按目标剩余空间清理失败'
      options.toast.error(storageActionError.value, '清理失败')
    } finally {
      isStorageBusy.value = false
    }
  }

  async function deleteImages(paths: string[], file: GalleryFile | null = null) {
    if (paths.length === 0) return
    const isBatch = paths.length > 1
    const confirmed = await options.confirmDialog.ask({
      title: isBatch ? '批量删除图片' : '删除图片',
      message: file
        ? `确定要删除 ${file.filename} 吗？此操作不可恢复。`
        : `确定要删除已选择的 ${paths.length} 张图片吗？此操作不可恢复。`,
      confirmText: '删除',
      cancelText: '取消',
    })
    if (!confirmed) return

    batchBusy.value = true
    await progressRuntime.start({
      title: isBatch ? '批量删除图片' : '删除图片',
      subtitle: file?.filename || `已选择 ${paths.length} 张`,
      total: paths.length,
      message: isBatch ? '正在提交批量删除请求...' : '正在提交删除请求...',
    })
    try {
      const result = await galleryApi.deleteFiles(paths)
      const removed = Number(result.removed || 0)
      progressRuntime.record({ label: '刷新列表', message: '删除完成，正在刷新列表...' })
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
      progressRuntime.succeed(isBatch ? `已删除 ${removed} 张图片` : '图片已删除', removed)
    } catch (error: any) {
      const message = error?.message || (isBatch ? '批量删除失败' : '删除图片失败')
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
      title: '批量下载图片',
      subtitle: `已选择 ${paths.length} 张`,
      total: paths.length,
      message: '正在打包 ZIP...',
    })
    try {
      const blob = await galleryApi.downloadZip(paths)
      progressRuntime.record({ label: '启动下载', message: 'ZIP 已生成，正在启动下载...' })
      saveBlob(blob, `images_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.zip`)
      progressRuntime.succeed(`已打包 ${paths.length} 张图片`, paths.length)
    } catch (error: any) {
      const message = error?.message || '批量下载失败'
      progressRuntime.fail(message)
    } finally {
      batchBusy.value = false
    }
  }

  async function handleGenBoxPush(file: GalleryFile) {
    if (genboxPushBusyPath.value) return
    genboxPushBusyPath.value = file.path
    try {
      const confirmed = await options.confirmDialog.ask({
        title: '推送到 GenBox',
        message: '只有你勾选下方选项、且 GenBox 回执确认时，源图才会被删除。',
        confirmText: '开始推送',
        cancelText: '取消',
        checkboxLabel: '推送成功后删除源图（默认不删）',
      })
      const selected = typeof confirmed === 'object' && confirmed.confirmed && confirmed.checked
      if (confirmed === false || (typeof confirmed === 'object' && !confirmed.confirmed)) return
      const result = await galleryApi.pushToGenBox(file.path, Boolean(selected))
      options.toast.success(result.label, 'Push 成功')
      await options.loadGallery()
    } catch (error) {
      options.toast.error(errorMessage(error, '推送到 GenBox 失败'), 'Push 失败')
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
