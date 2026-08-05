<template>
  <div v-if="images.length" class="detail-image-preview">
    <div class="detail-image-preview__header">
      <span class="detail-image-preview__title">图片预览</span>
      <span class="detail-image-preview__count">{{ images.length }} 张</span>
    </div>
    <div class="detail-image-preview__grid">
      <button
        v-for="(image, index) in images"
        :key="`${image.url}-${index}`"
        type="button"
        class="detail-image-preview__item"
        :title="image.title || image.url"
        @click="$emit('preview-click', image)"
      >
        <div class="detail-image-preview__media">
          <img
            v-if="!image.broken"
            :src="image.url"
            :alt="image.alt || `日志结果图片 ${index + 1}`"
            loading="lazy"
            class="detail-image-preview__image"
            @error="$emit('image-error', $event, image.url)"
          />
          <span v-else>无法预览</span>
        </div>
        <p class="detail-image-preview__filename">
          {{ image.filename || '-' }}
        </p>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
export type DetailImagePreviewItem = {
  url: string
  title?: string
  filename?: string
  alt?: string
  broken?: boolean
}

defineProps<{
  images: DetailImagePreviewItem[]
}>()

defineEmits<{
  (e: 'image-error', event: Event, url: string): void
  (e: 'preview-click', image: DetailImagePreviewItem): void
}>()
</script>

<style scoped>
.detail-image-preview {
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
}

.detail-image-preview__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-bottom: 1px solid hsl(var(--border) / 0.7);
  padding: 8px 12px;
}

.detail-image-preview__title {
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.detail-image-preview__count {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.detail-image-preview__grid {
  display: grid;
  gap: 12px;
  padding: 12px;
}

.detail-image-preview__item {
  display: block;
  width: 100%;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--muted) / 0.3);
  color: inherit;
  text-align: left;
  transition: border-color 0.18s ease;
}

.detail-image-preview__item:hover {
  border-color: hsl(var(--primary) / 0.4);
}

.detail-image-preview__media {
  display: flex;
  aspect-ratio: 4 / 3;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: hsl(var(--muted) / 0.35);
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.detail-image-preview__image {
  height: 100%;
  width: 100%;
  object-fit: contain;
  transition: transform 0.18s ease;
}

.detail-image-preview__item:hover .detail-image-preview__image {
  transform: scale(1.02);
}

.detail-image-preview__filename {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 6px 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

@media (min-width: 640px) {
  .detail-image-preview__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
