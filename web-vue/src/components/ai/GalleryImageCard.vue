<template>
  <article
    v-memo="[signature]"
    class="gallery-image-card gallery-item"
    :class="{ 'is-selected': selected, 'is-expired': file.expired }"
  >
    <div class="media-wrapper" @click="handlePreview">
      <img
        v-if="previewable"
        :src="imageUrl"
        :alt="file.filename"
        loading="lazy"
        class="media-content"
        @error="handleImageError"
      />
      <div v-else class="media-fallback">
        <Icon icon="lucide:image-off" class="h-8 w-8" />
        <span>无法预览</span>
      </div>

      <div class="media-topline">
        <Checkbox
          :model-value="selected"
          :aria-label="`选择图片 ${file.filename}`"
          @click.stop
          @update:model-value="handleSelect"
        />
        <span v-if="file.expired" class="media-badge danger">已过期</span>
        <span v-else class="media-badge">{{ storageLabel }}</span>
      </div>

      <div class="media-overlay">
        <button class="overlay-btn" title="复制链接" @click.stop="handleCopy">
          <Icon :icon="copied ? 'lucide:check' : 'lucide:copy'" />
        </button>
        <button class="overlay-btn" title="编辑标签" @click.stop="handleEditTags">
          <Icon icon="lucide:tag" />
        </button>
        <button class="overlay-btn" title="下载" @click.stop="handleDownload">
          <Icon icon="lucide:download" />
        </button>
        <button class="overlay-btn danger" title="删除" @click.stop="handleDelete">
          <Icon icon="lucide:trash-2" />
        </button>
      </div>
    </div>

    <div class="file-info">
      <p class="file-name" :title="file.path">{{ file.filename }}</p>
      <div class="file-meta">
        <span>{{ sizeLabel }}</span>
        <span v-if="dimensions">{{ dimensions }}</span>
        <Tooltip
          v-if="file.expires_in_seconds !== null && !file.expired && timeRemaining"
          :text="'将在 ' + timeRemaining + ' 后自动删除'"
        >
          <span class="file-countdown">{{ timeRemaining }}</span>
        </Tooltip>
      </div>
      <div v-if="file.tags.length" class="tag-row">
        <button
          v-for="tag in file.tags"
          :key="`${file.path}-${tag}`"
          type="button"
          class="tag-chip"
          @click="handleTagClick(tag)"
        >
          {{ tag }}
        </button>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { Checkbox, Tooltip } from 'nanocat-ui'
import type { GalleryFile } from '@/api/gallery'

const props = defineProps<{
  file: GalleryFile
  signature: string
  selected: boolean
  previewable: boolean
  copied: boolean
  imageUrl: string
  storageLabel: string
  sizeLabel: string
  dimensions: string
  timeRemaining: string
}>()

const emit = defineEmits<{
  (e: 'preview', file: GalleryFile): void
  (e: 'select', file: GalleryFile, checked: boolean): void
  (e: 'image-error', event: Event, file: GalleryFile): void
  (e: 'copy', file: GalleryFile): void
  (e: 'edit-tags', file: GalleryFile): void
  (e: 'download', file: GalleryFile): void
  (e: 'delete', file: GalleryFile): void
  (e: 'tag-click', tag: string): void
}>()

function handlePreview() {
  emit('preview', props.file)
}

function handleSelect(checked: boolean | string | number) {
  emit('select', props.file, Boolean(checked))
}

function handleImageError(event: Event) {
  emit('image-error', event, props.file)
}

function handleCopy() {
  emit('copy', props.file)
}

function handleEditTags() {
  emit('edit-tags', props.file)
}

function handleDownload() {
  emit('download', props.file)
}

function handleDelete() {
  emit('delete', props.file)
}

function handleTagClick(tag: string) {
  emit('tag-click', tag)
}
</script>

<style scoped>
.gallery-item {
  --gallery-card-bg: hsl(var(--card));
  --gallery-card-border: hsl(var(--border));
  --gallery-card-hover-border: hsl(var(--primary) / 0.35);
  --gallery-card-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  --gallery-media-bg: hsl(var(--muted));
  --gallery-badge-bg: rgba(255, 255, 255, 0.92);
  --gallery-badge-fg: hsl(var(--foreground));
  --gallery-float-bg: rgba(255, 255, 255, 0.92);
  --gallery-float-border: rgba(255, 255, 255, 0.6);
  --gallery-float-fg: hsl(var(--foreground));
  --gallery-float-hover-bg: hsl(var(--foreground));
  --gallery-float-hover-fg: hsl(var(--card));

  display: flex;
  height: 100%;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--gallery-card-border);
  border-radius: var(--gallery-radius, 16px);
  background: var(--gallery-card-bg);
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}

.gallery-item:hover {
  border-color: var(--gallery-card-hover-border);
  box-shadow: var(--gallery-card-shadow);
}

.gallery-item.is-selected {
  border-color: hsl(var(--primary) / 0.7);
  box-shadow: 0 0 0 2px hsl(var(--primary) / 0.16);
}

.gallery-item.is-expired {
  opacity: 0.65;
}

.media-wrapper {
  position: relative;
  aspect-ratio: 1 / 1;
  overflow: hidden;
  cursor: pointer;
  background: var(--gallery-media-bg);
}

.media-content {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s, opacity 0.2s;
}

.media-fallback {
  display: flex;
  width: 100%;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

.gallery-item:hover .media-content {
  transform: scale(1.025);
}

.media-topline {
  position: absolute;
  top: 8px;
  left: 8px;
  right: 8px;
  z-index: 2;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  pointer-events: none;
}

.media-topline :deep(*) {
  pointer-events: auto;
}

.media-badge {
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--gallery-badge-bg);
  color: var(--gallery-badge-fg);
  font-size: 10px;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(8px);
}

.media-badge.danger {
  background: hsl(0 84.2% 60.2%);
  color: white;
}

.media-overlay {
  position: absolute;
  inset: auto 8px 8px 8px;
  z-index: 2;
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.15s;
}

.media-wrapper:hover .media-overlay,
.gallery-item.is-selected .media-overlay {
  opacity: 1;
}

.overlay-btn {
  display: inline-flex;
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--gallery-float-border);
  border-radius: 999px;
  background: var(--gallery-float-bg);
  color: var(--gallery-float-fg);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, transform 0.15s;
  backdrop-filter: blur(8px);
}

.overlay-btn:hover {
  transform: translateY(-1px);
  background: var(--gallery-float-hover-bg);
  color: var(--gallery-float-hover-fg);
}

.overlay-btn.danger:hover {
  background: hsl(0 84.2% 60.2%);
  color: white;
}

.overlay-btn svg {
  width: 15px;
  height: 15px;
}

.file-info {
  display: flex;
  height: 88px;
  flex: 1 1 auto;
  flex-direction: column;
  padding: 10px;
}

.file-name {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.file-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  min-height: 16px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.file-countdown {
  color: hsl(25 95% 53%);
  font-weight: 500;
  cursor: help;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
  max-height: 23px;
  overflow: hidden;
}

.tag-chip {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  padding: 3px 8px;
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
  background: hsl(var(--background));
  color: hsl(var(--muted-foreground));
  font-size: 11px;
  line-height: 1.2;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}

.tag-chip:hover {
  border-color: hsl(var(--primary) / 0.45);
  background: hsl(var(--primary) / 0.08);
  color: hsl(var(--foreground));
}

@media (max-width: 420px) {
  .file-info {
    padding: 8px;
  }
}
</style>

<style>
html[data-theme="dark"] .gallery-image-card.gallery-item {
  --gallery-card-bg: hsl(0 0% 12%);
  --gallery-card-border: hsl(0 0% 31%);
  --gallery-card-hover-border: hsl(0 0% 48%);
  --gallery-card-shadow: 0 12px 28px rgba(0, 0, 0, 0.36);
  --gallery-media-bg: hsl(0 0% 14%);
  --gallery-badge-bg: rgba(22, 22, 22, 0.72);
  --gallery-badge-fg: rgba(255, 255, 255, 0.88);
  --gallery-float-bg: rgba(22, 22, 22, 0.78);
  --gallery-float-border: rgba(255, 255, 255, 0.18);
  --gallery-float-fg: rgba(255, 255, 255, 0.9);
  --gallery-float-hover-bg: rgba(255, 255, 255, 0.9);
  --gallery-float-hover-fg: hsl(0 0% 8%);
}
</style>
