<template>
  <RequestDetailDrawer
    :open="open"
    title="日志详情"
    :loading="loading"
    :error="error"
    loading-title="正在加载日志详情"
    loading-description="正在读取完整日志数据..."
    error-title="日志详情加载失败"
    @close="emit('close')"
  >
    <template v-if="log">
      <RequestDetailSummary
        :status-label="statusLabel(log)"
        :status-tone="statusTone(log)"
        :title="summaryText(log) || '调用日志'"
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
        empty-message="这条日志没有步骤耗时埋点；新的图片请求会显示分段耗时。"
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
        :title="log.requestTextTruncated ? '请求文本（已截断）' : '请求文本'"
        :content="log.requestTextFull || log.requestText"
        @copy="emit('copy', $event)"
      />
      <DetailTextBlock title="对外错误" :content="log.error" tone="danger" @copy="emit('copy', $event)" />
      <DetailTextBlock title="上游错误" :content="log.rawUpstreamError" tone="danger" @copy="emit('copy', $event)" />
      <DetailTextBlock title="上游文本" :content="log.rawUpstreamMessage" tone="warning" @copy="emit('copy', $event)" />
      <DetailImagePreview
        :images="images"
        @image-error="(event, url) => emit('image-error', event, url)"
        @preview-click="emit('preview-image', $event)"
      />
      <DetailTextBlock title="结果 URL" :content="log.urls.join('\n')" @copy="emit('copy', $event)" />
      <DetailTextBlock
        title="原始 detail JSON"
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
