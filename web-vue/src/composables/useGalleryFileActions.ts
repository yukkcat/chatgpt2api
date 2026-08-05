import { onBeforeUnmount, ref } from 'vue'
import { resolveGalleryFileUrl, type GalleryFile } from '@/api/gallery'
import { downloadUrlAsFile } from '@/lib/downloads'
import { errorMessage } from '@/lib/errorMessage'
import { useToast } from '@/composables/useToast'

type GalleryFileActionsOptions = {
  resolveUrl?: (url: string) => string
  copyResetMs?: number
  copySuccessMessage?: string
  copyErrorMessage?: string
  copySuccessTitle?: string
  copyErrorTitle?: string
  showDownloadSuccess?: boolean
  downloadSuccessMessage?: (file: GalleryFile) => string
  downloadErrorMessage?: (error: unknown, file: GalleryFile) => string
  downloadSuccessTitle?: string
  downloadErrorTitle?: string
}

function fallbackCopyText(value: string) {
  const input = document.createElement('input')
  input.value = value
  document.body.appendChild(input)
  input.select()
  document.execCommand('copy')
  document.body.removeChild(input)
}

async function copyTextToClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value)
    return
  }
  fallbackCopyText(value)
}

export function useGalleryFileActions(options: GalleryFileActionsOptions = {}) {
  const toast = useToast()
  const copiedFileKey = ref('')
  let copyResetTimer: number | null = null

  const resolveUrl = options.resolveUrl || resolveGalleryFileUrl
  const copyResetMs = options.copyResetMs ?? 1800

  function clearCopyState() {
    copiedFileKey.value = ''
    if (copyResetTimer !== null) {
      window.clearTimeout(copyResetTimer)
      copyResetTimer = null
    }
  }

  function markCopied(file: GalleryFile) {
    clearCopyState()
    copiedFileKey.value = file.path
    copyResetTimer = window.setTimeout(() => {
      copiedFileKey.value = ''
      copyResetTimer = null
    }, copyResetMs)
  }

  async function copyFileLink(file: GalleryFile | null) {
    if (!file) return
    try {
      await copyTextToClipboard(resolveUrl(file.url))
      markCopied(file)
      toast.success(options.copySuccessMessage || '图片链接已复制。', options.copySuccessTitle || '复制成功')
    } catch {
      clearCopyState()
      toast.error(options.copyErrorMessage || '复制链接失败。', options.copyErrorTitle || '复制失败')
    }
  }

  async function downloadFile(file: GalleryFile | null) {
    if (!file) return
    try {
      await downloadUrlAsFile(resolveUrl(file.url), file.filename, { localPath: file.path })
      if (options.showDownloadSuccess !== false) {
        toast.success(
          options.downloadSuccessMessage?.(file) || `已开始下载 ${file.filename}`,
          options.downloadSuccessTitle,
        )
      }
    } catch (error) {
      toast.error(
        options.downloadErrorMessage?.(error, file) || errorMessage(error, '') || '无法读取图片文件',
        options.downloadErrorTitle || '下载失败',
      )
    }
  }

  onBeforeUnmount(() => {
    clearCopyState()
  })

  return {
    copiedFileKey,
    clearCopyState,
    copyFileLink,
    downloadFile,
  }
}
