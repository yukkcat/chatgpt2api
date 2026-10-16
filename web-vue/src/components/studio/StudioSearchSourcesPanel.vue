<template>
  <section class="studio-search-sources-panel" aria-label="Sources">
    <ModalHeader
      title="Sources"
      :subtitle="`${sourceViews.length} web results`"
      compact
      @close="$emit('close')"
    />

    <div ref="sourceListRef" class="studio-search-sources-list custom-scrollbar">
      <component
        :is="view.source.url ? 'a' : 'div'"
        v-for="view in sourceViews"
        :key="`${message.id}-source-${view.index}`"
        :data-source-index="view.index"
        class="studio-search-source-card"
        :class="{
          'is-static': !view.source.url,
          'is-highlighted': highlightedSourceIndex === view.index,
        }"
        :href="view.source.url || undefined"
        :target="view.source.url ? '_blank' : undefined"
        :rel="view.source.url ? 'noreferrer' : undefined"
      >
        <span class="studio-search-source-index">{{ view.index + 1 }}</span>
        <span class="studio-search-source-body">
          <strong>{{ view.title }}</strong>
          <small v-if="view.host">{{ view.host }}</small>
          <em v-if="view.source.snippet">{{ view.source.snippet }}</em>
        </span>
        <Icon
          v-if="view.source.url"
          icon="lucide:external-link"
          class="studio-search-source-open h-3.5 w-3.5"
        />
      </component>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, nextTick, ref, watch } from 'vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import type { StudioMessage, StudioSearchSource } from './types'

const props = defineProps<{
  message: StudioMessage
  highlightedSourceIndex: number | null
  highlightRevision: number
}>()

defineEmits<{
  close: []
}>()

const sourceListRef = ref<HTMLElement | null>(null)
const sourceViews = computed(() => (props.message.searchSources || []).map((source, index) => ({
  source,
  index,
  title: sourceTitle(source, index),
  host: sourceHost(source.url),
})))

function sourceTitle(source: StudioSearchSource, index: number) {
  return source.title?.trim() || source.url?.trim() || `Source ${index + 1}`
}

function sourceHost(url: string | undefined) {
  const value = String(url || '').trim()
  if (!value) return ''
  try {
    return new URL(value).host.replace(/^www\./, '')
  } catch {
    return ''
  }
}

watch(
  () => [props.message.id, props.highlightedSourceIndex, props.highlightRevision] as const,
  async ([, sourceIndex]) => {
    if (sourceIndex === null) return
    await nextTick()
    const target = sourceListRef.value?.querySelector<HTMLElement>(`[data-source-index="${sourceIndex}"]`)
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  },
  { immediate: true },
)
</script>

<style scoped>
.studio-search-sources-panel {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
  background: hsl(var(--card));
}

.studio-search-sources-list {
  display: grid;
  min-height: 0;
  flex: 1 1 auto;
  align-content: start;
  gap: 0.625rem;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0.75rem;
}

.studio-search-source-card {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 0.5rem;
  border: 1px solid hsl(var(--border) / 0.72);
  border-radius: 0.5rem;
  background: hsl(var(--background) / 0.72);
  padding: 0.625rem;
  color: hsl(var(--foreground));
  text-decoration: none;
  transition: border-color 150ms ease, background 150ms ease, box-shadow 150ms ease;
}

.studio-search-source-card:hover,
.studio-search-source-card:focus-visible {
  border-color: hsl(var(--foreground) / 0.22);
  background: hsl(var(--background));
}

.studio-search-source-card:focus-visible {
  outline: 2px solid hsl(var(--ring));
  outline-offset: 2px;
}

.studio-search-source-card.is-static {
  cursor: default;
}

.studio-search-source-card.is-highlighted {
  border-color: hsl(var(--primary) / 0.42);
  background: hsl(var(--primary) / 0.08);
  box-shadow: 0 0 0 3px hsl(var(--primary) / 0.08);
}

.studio-search-source-index {
  display: inline-flex;
  width: 1.35rem;
  height: 1.35rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: hsl(var(--secondary));
  color: hsl(var(--muted-foreground));
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1;
}

.studio-search-source-body {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.15rem;
}

.studio-search-source-body strong,
.studio-search-source-body em {
  display: -webkit-box;
  min-width: 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
}

.studio-search-source-body strong {
  -webkit-line-clamp: 2;
  font-size: 0.8rem;
  font-weight: 750;
  line-height: 1.3;
}

.studio-search-source-body small {
  min-width: 0;
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-size: 0.7rem;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.studio-search-source-body em {
  -webkit-line-clamp: 3;
  color: hsl(var(--muted-foreground));
  font-size: 0.72rem;
  font-style: normal;
  line-height: 1.35;
}

.studio-search-source-open {
  margin-top: 0.1rem;
  color: hsl(var(--muted-foreground));
}
</style>
