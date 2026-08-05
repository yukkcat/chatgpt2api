import { ref } from 'vue'
import type { EditableFileTask } from '@/api/editableFileTasks'
import { downloadFilenameFromUrl, downloadPublicUrlAsFile } from '@/lib/downloads'

export type EditableFileTaskDownloadType = 'file' | 'zip'

type EditableFileTaskDownloadTarget = Pick<EditableFileTask, 'id' | 'kind'>

export function editableFileTaskDownloadFilename(
  task: EditableFileTaskDownloadTarget,
  url: string,
  type: EditableFileTaskDownloadType,
) {
  const fallback = type === 'zip'
    ? `${task.kind}-${task.id}.zip`
    : `${task.kind}-${task.id}.${task.kind === 'ppt' ? 'pptx' : 'psd'}`
  const filename = downloadFilenameFromUrl(url, fallback)
  return /\.[a-z0-9]{2,5}$/i.test(filename) ? filename : fallback
}

export function editableFileTaskDownloadError(error: unknown) {
  if (error instanceof Error && error.message.trim()) return error.message
  return '文件下载失败'
}

export type EditableFileTaskDownloadRuntimeInput = {
  onError: (message: string) => void
  downloadFile?: (url: string, filename: string) => Promise<void>
}

export function useEditableFileTaskDownload(input: EditableFileTaskDownloadRuntimeInput) {
  const isDownloading = ref(false)
  const downloadFile = input.downloadFile || downloadPublicUrlAsFile

  async function download(
    task: EditableFileTaskDownloadTarget,
    url: string,
    type: EditableFileTaskDownloadType,
  ) {
    if (isDownloading.value) return false
    isDownloading.value = true
    try {
      await downloadFile(url, editableFileTaskDownloadFilename(task, url, type))
      return true
    } catch (error) {
      input.onError(editableFileTaskDownloadError(error))
      return false
    } finally {
      isDownloading.value = false
    }
  }

  return {
    isDownloading,
    download,
  }
}
