<template>
  <div class="timeline-breakdown">
    <RequestTimelineBar
      v-if="segments.length"
      :segments="segments"
      :legend-items="legendItems"
    />

    <div v-else-if="emptyMessage" class="timeline-breakdown__empty">
      {{ emptyMessage }}
    </div>

    <div v-if="groups.length" class="timeline-breakdown__details">
      <button
        type="button"
        class="timeline-breakdown__toggle"
        :aria-expanded="detailsVisible"
        @click.stop="emit('toggle-details')"
      >
        <span>步骤明细</span>
        <strong>
          {{ detailsVisible ? '收起' : '展开' }}
          <Icon
            icon="lucide:chevron-down"
            :class="{ 'timeline-breakdown__chevron--open': detailsVisible }"
          />
        </strong>
      </button>

      <div v-show="detailsVisible" class="timeline-breakdown__groups">
        <div v-for="group in groups" :key="group.key" class="timeline-breakdown__group">
          <div class="timeline-breakdown__group-title">{{ group.name }}</div>
          <div class="timeline-breakdown__steps">
            <div
              v-for="step in group.steps"
              :key="step.key"
              class="timeline-breakdown__step"
              :class="[
                `timeline-breakdown__step--${step.category}`,
                `timeline-breakdown__step--${step.tone}`,
              ]"
            >
              <div class="timeline-breakdown__step-main">
                <div class="timeline-breakdown__step-head">
                  <div class="timeline-breakdown__step-label">
                    <span>{{ step.label }}</span>
                    <StateBadge :tone="step.tone" size="xs" shape="rounded">
                      {{ step.statusLabel }}
                    </StateBadge>
                  </div>
                  <span v-if="step.time" class="timeline-breakdown__step-time">{{ step.time }}</span>
                </div>
                <div class="timeline-breakdown__bar">
                  <span :style="step.barStyle" />
                </div>
                <p v-if="step.note" class="timeline-breakdown__step-note">{{ step.note }}</p>
              </div>
              <strong class="timeline-breakdown__step-value">{{ step.value }}</strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import RequestTimelineBar from '@/views/logs/RequestTimelineBar.vue'
import type {
  DetailTimelineGroup,
  DetailTimelineLegendItem,
  DetailTimelineSegment,
} from '@/views/logs/requestDetailView'

withDefaults(defineProps<{
  segments: DetailTimelineSegment[]
  legendItems: DetailTimelineLegendItem[]
  groups: DetailTimelineGroup[]
  detailsVisible: boolean
  emptyMessage?: string
}>(), {
  emptyMessage: '',
})

const emit = defineEmits<{
  (e: 'toggle-details'): void
}>()
</script>

<style scoped>
.timeline-breakdown,
.timeline-breakdown__details,
.timeline-breakdown__groups {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.timeline-breakdown {
  gap: 14px;
}

.timeline-breakdown__details,
.timeline-breakdown__groups {
  gap: 12px;
}

.timeline-breakdown__empty {
  border: 1px dashed hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--muted) / 0.25);
  padding: 14px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.timeline-breakdown__toggle {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--muted) / 0.22);
  padding: 8px 10px;
  text-align: left;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.timeline-breakdown__toggle:hover {
  background: hsl(var(--muted) / 0.34);
  color: hsl(var(--foreground));
}

.timeline-breakdown__toggle > span {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.timeline-breakdown__toggle strong {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
}

.timeline-breakdown__toggle svg {
  width: 14px;
  height: 14px;
  transition: transform 160ms ease;
}

.timeline-breakdown__chevron--open {
  transform: rotate(180deg);
}

.timeline-breakdown__group {
  display: grid;
  grid-template-columns: 5.5rem minmax(0, 1fr);
  gap: 12px;
}

.timeline-breakdown__group-title {
  padding-top: 5px;
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
}

.timeline-breakdown__steps {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 9px;
}

.timeline-breakdown__step {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 4.5rem;
  align-items: start;
  gap: 12px;
}

.timeline-breakdown__step-main {
  min-width: 0;
}

.timeline-breakdown__step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.timeline-breakdown__step-label {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.timeline-breakdown__step-time {
  flex: 0 0 auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.timeline-breakdown__bar {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: hsl(var(--muted) / 0.48);
  margin-top: 7px;
}

.timeline-breakdown__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: hsl(var(--muted-foreground) / 0.5);
}

.timeline-breakdown__step--entry .timeline-breakdown__bar span {
  background: rgb(96 165 250 / 0.78);
}

.timeline-breakdown__step--prepare .timeline-breakdown__bar span {
  background: rgb(20 184 166 / 0.76);
}

.timeline-breakdown__step--upstream .timeline-breakdown__bar span {
  background: rgb(99 102 241 / 0.76);
}

.timeline-breakdown__step--resolve .timeline-breakdown__bar span {
  background: rgb(249 115 22 / 0.72);
}

.timeline-breakdown__step--download .timeline-breakdown__bar span {
  background: rgb(34 197 94 / 0.68);
}

.timeline-breakdown__step--warning .timeline-breakdown__bar span {
  background: rgb(245 158 11 / 0.84);
}

.timeline-breakdown__step--danger .timeline-breakdown__bar span {
  background: rgb(244 63 94 / 0.82);
}

.timeline-breakdown__step-note {
  margin-top: 6px;
  overflow-wrap: anywhere;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.timeline-breakdown__step-value {
  padding-top: 1.6rem;
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 13px;
  font-weight: 650;
  color: hsl(var(--foreground));
}

@media (max-width: 640px) {
  .timeline-breakdown__group,
  .timeline-breakdown__step {
    grid-template-columns: 1fr;
  }

  .timeline-breakdown__group {
    gap: 8px;
  }

  .timeline-breakdown__step-value {
    padding-top: 0;
    text-align: left;
  }
}
</style>
