<template>
  <div class="timeline-bar">
    <div class="timeline-bar__track">
      <div
        v-for="segment in segments"
        :key="segment.key"
        class="timeline-bar__segment"
        :class="[
          `timeline-bar__segment--${segment.category}`,
          `timeline-bar__segment--${segment.tone}`,
          { 'timeline-bar__segment--compact': segment.compact },
        ]"
        :style="segment.barStyle"
        :title="segment.title"
      >
        <span>{{ segment.label }}</span>
        <strong>{{ segment.value }}</strong>
      </div>
    </div>
    <div v-if="legendItems.length" class="timeline-bar__legend">
      <span
        v-for="item in legendItems"
        :key="`${item.key}-legend`"
        class="timeline-bar__legend-item"
        :class="[
          `timeline-bar__legend-item--${item.category}`,
          `timeline-bar__legend-item--${item.tone}`,
        ]"
      >
        <i />
        {{ item.label }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type {
  DetailTimelineLegendItem,
  DetailTimelineSegment,
} from '@/views/logs/requestDetailView'

withDefaults(defineProps<{
  segments: DetailTimelineSegment[]
  legendItems?: DetailTimelineLegendItem[]
}>(), {
  legendItems: () => [],
})
</script>

<style scoped>
.timeline-bar {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
}

.timeline-bar__track {
  display: flex;
  height: 28px;
  min-height: 28px;
  gap: 2px;
  overflow: hidden;
  border-radius: 8px;
  background: hsl(var(--muted) / 0.72);
  padding: 3px;
}

.timeline-bar__segment {
  position: relative;
  display: flex;
  min-width: 6px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  overflow: hidden;
  border-radius: 5px;
  background: hsl(var(--muted-foreground) / 0.45);
  color: rgb(255 255 255 / 0.96);
  padding: 0 8px;
  white-space: nowrap;
}

.timeline-bar__segment span,
.timeline-bar__segment strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.timeline-bar__segment span {
  font-size: 12px;
  font-weight: 600;
}

.timeline-bar__segment strong {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  font-weight: 750;
}

.timeline-bar__segment--muted,
.timeline-bar__segment--info {
  background: hsl(var(--muted-foreground) / 0.48);
}

.timeline-bar__segment--compact {
  padding: 0;
}

.timeline-bar__segment--compact span,
.timeline-bar__segment--compact strong {
  display: none;
}

.timeline-bar__segment--entry {
  background: rgb(96 165 250 / 0.74);
}

.timeline-bar__segment--prepare {
  background: rgb(20 184 166 / 0.72);
}

.timeline-bar__segment--upstream {
  background: rgb(99 102 241 / 0.72);
}

.timeline-bar__segment--resolve {
  background: rgb(249 115 22 / 0.68);
  color: rgb(68 33 0);
}

.timeline-bar__segment--download {
  background: rgb(34 197 94 / 0.62);
  color: rgb(4 52 24);
}

.timeline-bar__segment--warning {
  background: rgb(245 158 11 / 0.84);
  color: rgb(74 45 0);
}

.timeline-bar__segment--danger {
  background: rgb(244 63 94 / 0.86);
  color: rgb(255 255 255 / 0.96);
}

.timeline-bar__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.timeline-bar__legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.timeline-bar__legend-item i {
  height: 7px;
  width: 7px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: hsl(var(--muted-foreground) / 0.54);
}

.timeline-bar__legend-item--entry i {
  background: rgb(96 165 250);
}

.timeline-bar__legend-item--prepare i {
  background: rgb(20 184 166);
}

.timeline-bar__legend-item--upstream i {
  background: rgb(99 102 241);
}

.timeline-bar__legend-item--resolve i {
  background: rgb(249 115 22);
}

.timeline-bar__legend-item--download i {
  background: rgb(34 197 94);
}

.timeline-bar__legend-item--state i {
  background: hsl(var(--muted-foreground));
}

.timeline-bar__legend-item--warning i {
  background: rgb(245 158 11);
}

.timeline-bar__legend-item--danger i {
  background: rgb(244 63 94);
}

@media (max-width: 640px) {
  .timeline-bar__track {
    height: 22px;
    min-height: 22px;
  }
}
</style>
