import { computed, ref, type Ref } from 'vue'

import { galleryApi, type GalleryFile } from '@/api/gallery'
import {
  canPreviewFile as canPreviewGalleryFile,
  parseTags,
} from '@/views/gallery/galleryView'
import { errorMessage } from '@/lib/errorMessage'

type Toast = {
  success: (message: string, title?: string) => void
  error: (message: string, title?: string) => void
}

type GalleryInteractionRuntimeOptions = {
  toast: Toast
  files: Ref<GalleryFile[]>
  tagFilter: Ref<string>
  loadGallery: () => Promise<void>
  resetAndLoad: () => void
}

export function useGalleryInteractionRuntime(options: GalleryInteractionRuntimeOptions) {
  const isTagSaving = ref(false)
  const previewFile = ref<GalleryFile | null>(null)
  const tagEditorFile = ref<GalleryFile | null>(null)
  const tagDraft = ref('')
  const selectedPaths = ref<Set<string>>(new Set())
  const brokenImagePaths = ref<Set<string>>(new Set())

  const selectedCount = computed(() => selectedPaths.value.size)
  const allVisibleSelected = computed(() => (
    options.files.value.length > 0 && options.files.value.every((file) => selectedPaths.value.has(file.path))
  ))
  const someVisibleSelected = computed(() => (
    !allVisibleSelected.value
    && options.files.value.some((file) => selectedPaths.value.has(file.path))
  ))
  const draftTags = computed(() => parseTags(tagDraft.value))

  function openPreview(file: GalleryFile) {
    previewFile.value = file
  }

  function closePreview() {
    previewFile.value = null
  }

  function closePreviewIfPath(path: string) {
    if (previewFile.value?.path === path) closePreview()
  }

  function openTagEditor(file: GalleryFile) {
    tagEditorFile.value = file
    tagDraft.value = file.tags.join(', ')
  }

  function closeTagEditor() {
    if (isTagSaving.value) return
    tagEditorFile.value = null
    tagDraft.value = ''
  }

  function closeTagEditorIfPath(path: string) {
    if (tagEditorFile.value?.path === path) closeTagEditor()
  }

  function applyFileTags(path: string, tags: string[]) {
    options.files.value = options.files.value.map((file) => (file.path === path ? { ...file, tags } : file))
    if (previewFile.value?.path === path) previewFile.value = { ...previewFile.value, tags }
    if (tagEditorFile.value?.path === path) tagEditorFile.value = { ...tagEditorFile.value, tags }
  }

  async function saveTagEditor() {
    const file = tagEditorFile.value
    if (!file) return
    const tags = draftTags.value
    isTagSaving.value = true
    try {
      const result = await galleryApi.updateTags(file.path, tags)
      const nextTags = result.tags || tags
      applyFileTags(file.path, nextTags)
    } catch (error) {
      options.toast.error(errorMessage(error, '保存标签失败'), '保存失败')
      return
    } finally {
      isTagSaving.value = false
    }
    closeTagEditor()
    options.toast.success('标签已保存。', '保存成功')
    await options.loadGallery()
  }

  function toggleDraftTag(tag: string) {
    const next = new Set(draftTags.value)
    if (next.has(tag)) {
      next.delete(tag)
    } else {
      next.add(tag)
    }
    tagDraft.value = Array.from(next).join(', ')
  }

  function setTagFilter(tag: string) {
    const shouldReload = options.tagFilter.value === tag
    options.tagFilter.value = tag
    if (shouldReload) options.resetAndLoad()
  }

  function toggleSelect(path: string, checked?: boolean) {
    const next = new Set(selectedPaths.value)
    const shouldSelect = typeof checked === 'boolean' ? checked : !next.has(path)
    if (shouldSelect) {
      next.add(path)
    } else {
      next.delete(path)
    }
    selectedPaths.value = next
  }

  function toggleSelectAllVisible(checked?: boolean) {
    const next = new Set(selectedPaths.value)
    const shouldSelect = typeof checked === 'boolean' ? checked : !allVisibleSelected.value
    for (const file of options.files.value) {
      if (shouldSelect) next.add(file.path)
      else next.delete(file.path)
    }
    selectedPaths.value = next
  }

  function isSelected(path: string) {
    return selectedPaths.value.has(path)
  }

  function clearSelection() {
    selectedPaths.value = new Set()
  }

  function pruneSelection() {
    if (selectedPaths.value.size === 0) return
    const loadedPaths = new Set(options.files.value.map((file) => file.path))
    selectedPaths.value = new Set(Array.from(selectedPaths.value).filter((path) => loadedPaths.has(path)))
  }

  function canPreviewFile(file: GalleryFile) {
    return canPreviewGalleryFile(file, brokenImagePaths.value)
  }

  function handleImageError(event: Event, path: string) {
    const img = event.target as HTMLImageElement
    img.style.opacity = '0'
    brokenImagePaths.value = new Set([...brokenImagePaths.value, path])
  }

  function clearBrokenImages() {
    brokenImagePaths.value = new Set()
  }

  return {
    isTagSaving,
    previewFile,
    tagEditorFile,
    tagDraft,
    selectedPaths,
    selectedCount,
    allVisibleSelected,
    someVisibleSelected,
    draftTags,
    openPreview,
    closePreview,
    closePreviewIfPath,
    openTagEditor,
    closeTagEditor,
    closeTagEditorIfPath,
    saveTagEditor,
    toggleDraftTag,
    setTagFilter,
    toggleSelect,
    toggleSelectAllVisible,
    isSelected,
    clearSelection,
    pruneSelection,
    canPreviewFile,
    handleImageError,
    clearBrokenImages,
  }
}
