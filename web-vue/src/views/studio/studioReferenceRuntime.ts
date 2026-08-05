import { ref } from 'vue'
import type { StudioPreviewImage, StudioReference, StudioReferenceImage } from '@/components/studio/types'
import { createStudioId } from './studioConversationState'

const DEFAULT_MAX_REFERENCE_FILES = 8

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

export async function createStudioReferenceFromFile(file: File): Promise<StudioReference> {
  const dataUrl = await readFileAsDataUrl(file)
  return {
    id: createStudioId('source'),
    name: file.name || '参考图',
    type: file.type || 'image/png',
    size: file.size,
    dataUrl,
  }
}

export function toStudioMessageReferenceImage(reference: StudioReference): StudioReferenceImage {
  return {
    id: reference.id,
    name: reference.name,
    type: reference.type,
    size: reference.size,
    dataUrl: reference.dataUrl,
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
