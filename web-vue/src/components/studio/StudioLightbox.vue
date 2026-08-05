<template>
  <GalleryLightbox
    :file="lightboxFile"
    :image-url="preview?.src || ''"
    size-label=""
    :copied="false"
    :show-actions="true"
    :show-tag-action="false"
    @close="$emit('close')"
    @copy="copyPreview"
    @download="$emit('download')"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import GalleryLightbox from '@/components/ai/GalleryLightbox.vue'
import type { GalleryFile } from '@/api/gallery'
import type { StudioPreviewImage } from './types'

const props = defineProps<{
  preview: StudioPreviewImage | null
}>()

const emit = defineEmits<{
  close: []
  copy: [value: string]
  download: []
}>()

const lightboxFile = computed<GalleryFile | null>(() => {
  const preview = props.preview
  if (!preview) return null
  return {
    id: preview.localPath || preview.src,
    filename: preview.name || 'studio-preview-image',
    path: preview.localPath || preview.src,
    url: preview.src,
    thumbnail_url: preview.src,
    size_bytes: 0,
    created_at: '',
    date: '',
    media_type: 'image',
    expired: false,
    expires_at: null,
    expires_in_seconds: null,
    tags: [],
    storage: 'studio',
    local: Boolean(preview.localPath),
    webdav: false,
    available: true,
    width: null,
    height: null,
  }
})

function copyPreview() {
  if (!props.preview?.src) return
  emit('copy', props.preview.src)
}
</script>
