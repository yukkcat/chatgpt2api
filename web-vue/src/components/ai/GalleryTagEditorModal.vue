<template>
  <ModalShell
    :open="Boolean(file)"
    aria-label="Edit tags"
    :z-index="150"
    close-on-backdrop
    @close="$emit('close')"
  >
    <template v-if="file">
      <ModalHeader
        title="Edit tags"
        :subtitle="file.path"
        :close-disabled="isSaving"
        @close="$emit('close')"
      />

      <div class="gallery-tag-editor">
        <div class="gallery-tag-editor__grid">
          <img
            :src="imageUrl"
            :alt="file.filename"
            class="gallery-tag-editor__thumb"
          />
          <div class="gallery-tag-editor__body">
            <Input
              :model-value="draft"
              type="text"
              placeholder="Separate tags with commas or spaces"
              block
              @update:model-value="$emit('update:draft', $event)"
              @keyup.enter="$emit('save')"
            />
            <div class="gallery-tag-editor__tags">
              <button
                v-for="tag in allTags"
                :key="tag"
                type="button"
                class="tag-picker"
                :class="{ active: draftTags.includes(tag) }"
                @click="$emit('toggle-tag', tag)"
              >
                {{ tag }}
              </button>
              <span v-if="allTags.length === 0" class="gallery-tag-editor__empty">No existing tags</span>
            </div>
          </div>
        </div>
      </div>

      <ModalFooter>
        <Button size="sm" variant="outline" :disabled="isSaving" @click="$emit('clear')">
          Clear
        </Button>
        <Button size="sm" variant="primary" :disabled="isSaving" @click="$emit('save')">
          {{ isSaving ? 'Saving...' : 'Save tags' }}
        </Button>
      </ModalFooter>
    </template>
  </ModalShell>
</template>

<script setup lang="ts">
import { Button, Input } from 'nanocat-ui'
import type { GalleryFile } from '@/api/gallery'
import ModalFooter from './ModalFooter.vue'
import ModalHeader from './ModalHeader.vue'
import ModalShell from './ModalShell.vue'

defineProps<{
  file: GalleryFile | null
  imageUrl: string
  draft: string
  draftTags: string[]
  allTags: string[]
  isSaving: boolean
}>()

defineEmits<{
  (e: 'close'): void
  (e: 'clear'): void
  (e: 'save'): void
  (e: 'toggle-tag', tag: string): void
  (e: 'update:draft', value: string): void
}>()
</script>

<style scoped>
.gallery-tag-editor {
  padding: 16px 20px;
}

.gallery-tag-editor__grid {
  display: grid;
  gap: 16px;
}

@media (min-width: 768px) {
  .gallery-tag-editor__grid {
    grid-template-columns: 10rem minmax(0, 1fr);
  }
}

.gallery-tag-editor__thumb {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 8px;
  background: hsl(var(--muted));
  object-fit: cover;
}

.gallery-tag-editor__body {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
}

.gallery-tag-editor__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.gallery-tag-editor__empty {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.tag-picker {
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

.tag-picker:hover,
.tag-picker.active {
  border-color: hsl(var(--primary) / 0.45);
  background: hsl(var(--primary) / 0.08);
  color: hsl(var(--foreground));
}
</style>
