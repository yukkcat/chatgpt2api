import { computed, nextTick, ref } from 'vue'

import type {
  AccountOperationEvent,
  AccountOperationProgress,
} from '@/api/accounts'

export type AccountBulkProgressKind = 'sync' | 'credentials' | 'mutation' | 'import'

export interface AccountOperationTimelineEvent extends AccountOperationEvent {
  key: string
}

type AccountBulkProgressPatch = Partial<AccountOperationProgress> & {
  total: number
  processed?: number
}

const ACCOUNT_OPERATION_EVENT_LIMIT = 500

function cleanText(value: unknown) {
  return String(value || '').trim()
}

export function useAccountBulkProgressRuntime() {
  const batchBusy = ref(false)
  const showRefreshProgress = ref(false)
  const refreshProgressTitle = ref('')
  const refreshProgress = ref<AccountOperationProgress | null>(null)
  const refreshProgressKind = ref<AccountBulkProgressKind>('sync')
  const bulkStopRequested = ref(false)
  const bulkStopEnabled = ref(false)
  const operationEvents = ref<AccountOperationTimelineEvent[]>([])
  const backendEventKeys = new Set<string>()

  function trimEvents() {
    if (operationEvents.value.length <= ACCOUNT_OPERATION_EVENT_LIMIT) return
    operationEvents.value = operationEvents.value.slice(-ACCOUNT_OPERATION_EVENT_LIMIT)
  }

  function mergeBackendEvents(events: AccountOperationEvent[] | undefined) {
    if (!Array.isArray(events) || events.length === 0) return
    const additions: AccountOperationTimelineEvent[] = []
    for (const [index, raw] of events.entries()) {
      if (!raw || typeof raw !== 'object') continue
      const message = cleanText(raw.message)
      if (!message) continue
      const sequence = Number.isFinite(Number(raw.sequence))
        ? Math.max(0, Number(raw.sequence))
        : index + 1
      const timestamp = cleanText(raw.timestamp)
      const key = [
        'backend',
        sequence,
        timestamp,
        cleanText(raw.action),
        cleanText(raw.account_id),
        message,
      ].join(':')
      if (backendEventKeys.has(key)) continue
      backendEventKeys.add(key)
      additions.push({
        key,
        sequence,
        timestamp,
        account_id: cleanText(raw.account_id),
        account_label: cleanText(raw.account_label),
        action: cleanText(raw.action),
        status: raw.status,
        tone: raw.tone,
        message,
      })
    }
    if (!additions.length) return
    operationEvents.value = [...operationEvents.value, ...additions]
    trimEvents()
  }

  const refreshProgressPercent = computed(() => {
    const progress = refreshProgress.value
    const total = Math.max(0, Number(progress?.total || 0))
    if (total <= 0) return 0
    return Math.min(100, Math.round((Math.max(0, Number(progress?.processed || 0)) / total) * 100))
  })

  const refreshProgressStatusText = computed(() => {
    const progress = refreshProgress.value
    if (bulkStopRequested.value) return '停止中'
    if (progress?.status_label) return progress.status_label
    if (progress?.error) return '失败'
    if (progress?.done) return '已完成'
    return progress?.stage_label || '处理中'
  })

  const canStopRefreshProgress = computed(() => (
    bulkStopEnabled.value
    && showRefreshProgress.value
    && batchBusy.value
    && !refreshProgress.value?.done
  ))

  const canCloseRefreshProgress = computed(() => (
    Boolean(refreshProgress.value?.done) || !batchBusy.value
  ))

  async function start(
    title: string,
    total: number,
    kind: AccountBulkProgressKind,
    options: { stoppable?: boolean } = {},
  ) {
    backendEventKeys.clear()
    operationEvents.value = []
    bulkStopRequested.value = false
    bulkStopEnabled.value = Boolean(options.stoppable)
    batchBusy.value = true
    showRefreshProgress.value = true
    refreshProgressTitle.value = title
    refreshProgressKind.value = kind
    refreshProgress.value = {
      total,
      processed: 0,
      done: false,
      error: null,
      total_quota: kind === 'sync' ? 0 : undefined,
      result: null,
    }
    await nextTick()
    if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') return
    await new Promise<void>((resolve) => {
      let settled = false
      const finish = () => {
        if (settled) return
        settled = true
        window.clearTimeout(fallbackTimer)
        resolve()
      }
      const fallbackTimer = window.setTimeout(finish, 80)
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(finish)
      })
    })
  }

  function end() {
    batchBusy.value = false
  }

  function update(patch: AccountBulkProgressPatch) {
    mergeBackendEvents(patch.events)
    const current = refreshProgress.value || { total: patch.total, processed: 0, done: false }
    refreshProgress.value = {
      ...current,
      ...patch,
      done: patch.done === undefined ? current.done : Boolean(patch.done),
    }
  }

  function finish(patch: AccountBulkProgressPatch) {
    mergeBackendEvents(patch.events)
    const progress: AccountOperationProgress = {
      ...(refreshProgress.value || { total: patch.total, processed: patch.processed || 0, done: false }),
      ...patch,
      done: true,
    }
    refreshProgress.value = progress
  }

  function fail(total: number, processed: number, error: string) {
    const progress: AccountOperationProgress = {
      ...(refreshProgress.value || { total, processed, done: false }),
      total,
      processed,
      done: true,
      error,
    }
    refreshProgress.value = progress
  }

  function requestStop() {
    if (!canStopRefreshProgress.value) return false
    bulkStopRequested.value = true
    return true
  }

  function close() {
    if (!refreshProgress.value?.done && batchBusy.value) return false
    showRefreshProgress.value = false
    return true
  }

  return {
    batchBusy,
    showRefreshProgress,
    refreshProgressTitle,
    refreshProgress,
    refreshProgressKind,
    refreshProgressPercent,
    refreshProgressStatusText,
    canStopRefreshProgress,
    canCloseRefreshProgress,
    bulkStopRequested,
    bulkStopEnabled,
    operationEvents,
    appendEvents: mergeBackendEvents,
    start,
    end,
    update,
    finish,
    fail,
    requestStop,
    close,
  }
}
