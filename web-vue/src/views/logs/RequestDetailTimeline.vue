<template>
  <section class="request-detail-timeline">
    <div class="request-detail-timeline__header">
      <div>
        <span>步骤耗时</span>
        <p>按执行顺序展示，条形长度表示相对耗时</p>
      </div>
      <RequestTimelineSummary
        :step-count="stepCount"
        :duration-ms="durationMs"
        :status="status"
      />
    </div>

    <RequestTimelineBreakdown
      :segments="segments"
      :legend-items="legendItems"
      :groups="groups"
      :details-visible="detailsVisible"
      :empty-message="emptyMessage"
      @toggle-details="emit('toggle-details')"
    />
  </section>
</template>

<script setup lang="ts">
import type { CallPresentationStatus } from '@/api/requestDetail'
import type {
  DetailTimelineGroup,
  DetailTimelineLegendItem,
  DetailTimelineSegment,
} from '@/views/logs/requestDetailView'
import RequestTimelineBreakdown from '@/views/logs/RequestTimelineBreakdown.vue'
import RequestTimelineSummary from '@/views/logs/RequestTimelineSummary.vue'

withDefaults(defineProps<{
  segments: DetailTimelineSegment[]
  legendItems: DetailTimelineLegendItem[]
  groups: DetailTimelineGroup[]
  stepCount: number
  durationMs: number
  status: CallPresentationStatus
  detailsVisible: boolean
  emptyMessage?: string
}>(), {
  emptyMessage: '该请求没有可展示的步骤耗时。',
})

const emit = defineEmits<{
  (e: 'toggle-details'): void
}>()
</script>

<style scoped>
.request-detail-timeline {
  display: flex;
  flex-direction: column;
  gap: 14px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
  padding: 14px;
}

.request-detail-timeline__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.request-detail-timeline__header span {
  color: hsl(var(--foreground));
  font-size: 13px;
  font-weight: 650;
}

.request-detail-timeline__header p {
  margin-top: 3px;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

@media (max-width: 640px) {
  .request-detail-timeline__header {
    flex-direction: column;
  }
}
</style>
