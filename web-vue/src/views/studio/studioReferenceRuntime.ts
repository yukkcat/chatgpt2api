import { ref } from 'vue'
import type { StudioPreviewImage, StudioReference, StudioReferenceImage } from '@/components/studio/types'
import { createStudioId } from './studioConversationState'

const DEFAULT_MAX_REFERENCE_FILES = 8
const MESSAGE_PREVIEW_MAX_EDGE = 640
const MESSAGE_PREVIEW_MAX_FALLBACK_LENGTH = 450_000
const MESSAGE_PREVIEW_QUALITY = 0.82

export type StudioReferenceRuntimeOptions = {
  maxFiles?: number
}

function isImageFile(file: File) {
  return file.type.startsWith('image/') || /\.(avif|bmp|gif|heic|heif|ico|jpe?g|png|svg|tiff?|webp)$/i.test(file.name)
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('读取参考图失败'))
    reader.readAsDataURL(file)
  })
}

function fallbackMessagePreviewDataUrl(source: string) {
  return source.length <= MESSAGE_PREVIEW_MAX_FALLBACK_LENGTH ? source : ''
}

function createMessagePreviewDataUrl(source: string, mimeType: string) {
  if (!source || typeof document === 'undefined' || typeof Image === 'undefined') {
    return Promise.resolve(fallbackMessagePreviewDataUrl(source))
  }

  return new Promise<string>((resolve) => {
    const image = new Image()
    image.onload = () => {
      const width = image.naturalWidth || image.width
      const height = image.naturalHeight || image.height
      if (!width || !height) {
        resolve(fallbackMessagePreviewDataUrl(source))
        return
      }

      try {
        const scale = Math.min(1, MESSAGE_PREVIEW_MAX_EDGE / Math.max(width, height))
        const canvas = document.createElement('canvas')
        canvas.width = Math.max(1, Math.round(width * scale))
        canvas.height = Math.max(1, Math.round(height * scale))
        const context = canvas.getContext('2d')
        if (!context) {
          resolve(fallbackMessagePreviewDataUrl(source))
          return
        }
        context.drawImage(image, 0, 0, canvas.width, canvas.height)
        const outputType = mimeType === 'image/png' || mimeType === 'image/webp' ? 'image/webp' : 'image/jpeg'
        const preview = canvas.toDataURL(outputType, MESSAGE_PREVIEW_QUALITY)
        resolve(preview || fallbackMessagePreviewDataUrl(source))
      } catch {
        resolve(fallbackMessagePreviewDataUrl(source))
      }
    }
    image.onerror = () => resolve(fallbackMessagePreviewDataUrl(source))
    image.src = source
  })
}

export async function createStudioReferenceFromFile(file: File): Promise<StudioReference> {
  const dataUrl = await readFileAsDataUrl(file)
  const previewDataUrl = await createMessagePreviewDataUrl(dataUrl, file.type)
  return {
    id: createStudioId('source'),
    name: file.name || '参考图',
    type: file.type || 'image/png',
    size: file.size,
    dataUrl,
    previewDataUrl,
  }
}

export function toStudioMessageReferenceImage(reference: StudioReference): StudioReferenceImage {
  return {
    id: reference.id,
    name: reference.name,
    type: reference.type,
    size: reference.size,
    dataUrl: reference.previewDataUrl ?? reference.dataUrl,
  }
}

export function useStudioReferenceRuntime(options: StudioReferenceRuntimeOptions = {}) {
  const maxFiles = options.maxFiles || DEFAULT_MAX_REFERENCE_FILES
  const files = ref<File[]>([])
  const references = ref<StudioReference[]>([])
  const preview = ref<StudioPreviewImage | null>(null)

  function attachmentNames() {
    return references.value.map((reference) => reference.name)
  }

  function messageReferenceImages(): StudioReferenceImage[] {
    return references.value
      .map(toStudioMessageReferenceImage)
      .filter((reference) => reference.dataUrl)
      .slice(0, maxFiles)
  }

  function selectedFiles() {
    return files.value.slice(0, maxFiles)
  }

  async function append(nextFiles: File[]) {
    const remaining = Math.max(0, maxFiles - files.value.length)
    const imageFiles = nextFiles.filter(isImageFile).slice(0, remaining)
    if (!imageFiles.length) return false

    for (const file of imageFiles) {
      const reference = await createStudioReferenceFromFile(file)
      files.value.push(file)
      references.value.push(reference)
    }
    return true
  }

  function remove(index: number) {
    files.value.splice(index, 1)
    references.value.splice(index, 1)
  }

  function clear() {
    files.value = []
    references.value = []
  }

  function open(reference: StudioReference) {
    if (!reference.dataUrl) return
    preview.value = {
      src: reference.dataUrl,
      name: reference.name,
    }
  }

  function openPreview(src: string, name: string, localPath = '') {
    if (!src) return
    preview.value = { src, name, localPath }
  }

  function closePreview() {
    preview.value = null
  }

  return {
    files,
    references,
    preview,
    selectedFiles,
    attachmentNames,
    messageReferenceImages,
    append,
    remove,
    clear,
    open,
    openPreview,
    closePreview,
  }
}
