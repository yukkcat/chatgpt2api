<template>
  <OperationProgressDrawer
    :open="open"
    :title="title || '账号任务记录'"
    :subtitle="`${processed} / ${total} · ${percent}%`"
    :total="total"
    :current="processed"
    :percent="percent"
    :status-label="statusText"
    :error="progress?.error || ''"
    :busy="!canClose"
    :tone="progress?.tone || (progress?.error ? 'danger' : 'info')"
    :events="timelineEvents"
    :summary-items="progress?.summary_items || []"
    :can-cancel="canStop"
    :cancel-disabled="stopRequested"
    :cancel-label="stopRequested ? '停止中...' : '停止'"
    :close-disabled="!canClose"
    @cancel="emit('stop')"
    @close="emit('close')"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AccountOperationProgress } from '@/api/accounts'
import OperationProgressDrawer from '@/components/ai/OperationProgressDrawer.vue'
import type { OperationTimelineEvent } from '@/composables/useOperationProgressRuntime'
import type { AccountOperationTimelineEvent } from './accountBulkProgressRuntime'

const props = defineProps<{
  open: boolean
  title: string
  statusText: string
  progress: AccountOperationProgress | null
  percent: number
  events: AccountOperationTimelineEvent[]
  canStop: boolean
  stopRequested: boolean
  canClose: boolean
}>()

const emit = defineEmits<{
  close: []
  stop: []
}>()

const processed = computed(() => Math.max(0, Number(props.progress?.processed || 0)))
const total = computed(() => Math.max(0, Number(props.progress?.total || 0)))

const timelineEvents = computed<OperationTimelineEvent[]>(() => props.events.map((event) => ({
  key: event.key,
  timestamp: event.timestamp,
  label: event.account_label || event.account_id || '任务',
  message: event.message,
  tone: event.tone,
})))
</script>
