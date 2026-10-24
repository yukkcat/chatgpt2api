<template>
  <RequestDetailDrawer
    :open="open"
    title="Log details"
    :loading="loading"
    :error="error"
    loading-title="Loading log details"
    loading-description="Reading complete log data..."
    error-title="Failed to load log details"
    @close="emit('close')"
  >
    <template v-if="log">
      <RequestDetailSummary
        :status-label="statusLabel(log)"
        :status-tone="statusTone(log)"
        :title="summaryText(log) || 'Call log'"
        :duration="durationDisplay.total"
        :duration-breakdown="durationDisplay.breakdown"
      />

      <RequestDetailFields
        :primary-fields="primaryFields"
        :diagnostic-fields="diagnosticFields"
        @copy="emit('copy', $event)"
      />

      <RequestDetailTimeline
        v-if="timelineSegments.length || timelineGroups.length"
        :segments="timelineSegments"
        :legend-items="timelineLegendItems"
        :groups="timelineGroups"
        :step-count="timelineStepCount"
        :duration-ms="timelineSegmentTotal"
        :status="log.presentation.status"
        :details-visible="timelineDetailsVisible"
        empty-message="This log has no step-timing data. New image requests will show timing breakdowns."
        @toggle-details="emit('toggle-timeline-details')"
      />

      <LogsImageAttemptTimeline
        v-if="hasImageAttemptBreakdown(log)"
        :attempts="log.imageAttempts"
        :groups="log.detailPresentation.attempt_groups"
        :requested-count="log.imageRequestedCount"
        :succeeded-count="log.imageSucceededCount"
        :failed-count="log.imageFailedCount"
        :switch-count="log.accountSwitchCount"
      />

      <DetailTextBlock
        :title="log.requestTextTruncated ? 'Request text (truncated)' : 'Request text'"
        :content="log.requestTextFull || log.requestText"
        @copy="emit('copy', $event)"
      />
      <DetailTextBlock title="Client-facing error" :content="log.error" tone="danger" @copy="emit('copy', $event)" />
      <DetailTextBlock title="Upstream error" :content="log.rawUpstreamError" tone="danger" @copy="emit('copy', $event)" />
      <DetailTextBlock title="Upstream text" :content="log.rawUpstreamMessage" tone="warning" @copy="emit('copy', $event)" />
      <DetailImagePreview
        :images="images"
        @image-error="(event, url) => emit('image-error', event, url)"
        @preview-click="emit('preview-image', $event)"
      />
      <DetailTextBlock title="Result URLs" :content="log.urls.join('\n')" @copy="emit('copy', $event)" />
      <DetailTextBlock
        title="Raw detail JSON"
        :content="log.rawJson"
        tone="muted"
        max-height="24rem"
        @copy="emit('copy', $event)"
      />
    </template>
  </RequestDetailDrawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DetailImagePreview from '@/components/ai/DetailImagePreview.vue'
import DetailTextBlock from '@/components/ai/DetailTextBlock.vue'
import RequestDetailDrawer from '@/components/ai/RequestDetailDrawer.vue'
import RequestDetailFields from '@/views/logs/RequestDetailFields.vue'
import RequestDetailSummary from '@/views/logs/RequestDetailSummary.vue'
import RequestDetailTimeline from '@/views/logs/RequestDetailTimeline.vue'
import { type SystemLogRow } from '@/api/logs'
import {
  hasImageAttemptBreakdown,
  type DetailField,
  type DetailTimelineGroup,
  type DetailTimelineLegendItem,
  type DetailTimelineSegment,
} from '@/views/logs/logDetailView'
import type { DetailPreviewImage } from '@/views/logs/logDetailRuntime'
import {
  logDurationDisplay,
  statusLabel,
  statusTone,
  summaryText,
} from '@/views/logs/logsView'
import LogsImageAttemptTimeline from '@/views/logs/LogsImageAttemptTimeline.vue'

const props = defineProps<{
  open: boolean
  log: SystemLogRow | null
  loading: boolean
  error: string
  primaryFields: DetailField[]
  diagnosticFields: DetailField[]
  timelineSegments: DetailTimelineSegment[]
  timelineLegendItems: DetailTimelineLegendItem[]
  timelineGroups: DetailTimelineGroup[]
  timelineStepCount: number
  timelineSegmentTotal: number
  timelineDetailsVisible: boolean
  images: DetailPreviewImage[]
}>()

const durationDisplay = computed(() => (
  props.log ? logDurationDisplay(props.log) : { total: '', breakdown: '' }
))

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'copy', value: string): void
  (e: 'image-error', event: Event, url: string): void
  (e: 'preview-image', image: DetailPreviewImage): void
  (e: 'toggle-timeline-details'): void
}>()
</script>
