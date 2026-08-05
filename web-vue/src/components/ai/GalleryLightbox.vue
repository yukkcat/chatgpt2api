<template>
  <ModalShell
    :open="Boolean(file)"
    aria-label="图片预览"
    close-on-overlay
    close-on-escape
    overlay-class="lightbox"
    root-class="lightbox-content"
    size-class=""
    max-width="92vw"
    :z-index="420"
    bare
    @close="emit('close')"
  >
    <template v-if="file">
      <CloseButton class="lightbox-close" label="关闭预览" tone="dark" @click="emit('close')" />
        <img
          :src="imageUrl"
          :alt="file.filename"
          class="lightbox-media"
        />
        <div class="lightbox-info">
          <span class="max-w-[24rem] truncate" :title="file.path">{{ file.filename }}</span>
          <span v-if="sizeLabel">{{ sizeLabel }}</span>
          <span v-if="file.created_at">{{ file.created_at }}</span>
          <button v-if="canShowDownload" class="lightbox-btn" @click="emitFile('download')">
            <Icon icon="lucide:download" />
            下载
          </button>
          <button v-if="canShowCopy" class="lightbox-btn" @click="emitFile('copy')">
            <Icon :icon="copied ? 'lucide:check' : 'lucide:copy'" />
            {{ copied ? '已复制' : '复制链接' }}
          </button>
          <button v-if="canShowTag" class="lightbox-btn" @click="emitFile('edit-tags')">
            <Icon icon="lucide:tag" />
            标签
          </button>
        </div>
    </template>
  </ModalShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { CloseButton, ModalShell } from 'nanocat-ui'
import type { GalleryFile } from '@/api/gallery'

const props = withDefaults(defineProps<{
  file: GalleryFile | null
  imageUrl: string
  sizeLabel: string
  copied: boolean
  showActions?: boolean
  showDownloadAction?: boolean
  showCopyAction?: boolean
  showTagAction?: boolean
}>(), {
  showActions: true,
  showDownloadAction: true,
  showCopyAction: true,
  showTagAction: true,
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'download', file: GalleryFile): void
  (e: 'copy', file: GalleryFile): void
  (e: 'edit-tags', file: GalleryFile): void
}>()

const canShowDownload = computed(() => props.showActions && props.showDownloadAction)
const canShowCopy = computed(() => props.showActions && props.showCopyAction)
const canShowTag = computed(() => props.showActions && props.showTagAction)

function emitFile(event: 'download' | 'copy' | 'edit-tags') {
  if (!props.file) return
  emit(event, props.file)
}
</script>

<style scoped>
:global(.lightbox) {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.62);
  backdrop-filter: blur(10px);
}

:global(.lightbox-content) {
  position: relative;
  display: flex;
  max-height: 92vh;
  width: fit-content;
  flex-direction: column;
  align-items: center;
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.lightbox-close {
  position: absolute;
  top: -40px;
  right: -4px;
}

.lightbox-media {
  max-width: 100%;
  max-height: 80vh;
  border-radius: var(--gallery-radius, 16px);
  object-fit: contain;
}

.lightbox-info {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 12px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.78);
}

.lightbox-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 999px;
  background: transparent;
  color: white;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.lightbox-btn:hover {
  border-color: rgba(255, 255, 255, 0.65);
  background: rgba(255, 255, 255, 0.1);
}
</style>
