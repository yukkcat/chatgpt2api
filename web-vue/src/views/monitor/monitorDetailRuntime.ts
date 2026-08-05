import { ref, shallowRef } from 'vue'

import type {
  RealtimeMonitorRecord,
  RealtimeMonitorRecordDetail,
} from '@/api/monitor'
import { errorMessage } from '@/lib/errorMessage'

type MonitorDetailRuntimeOptions = {
  loadDetail: (callId: string) => Promise<RealtimeMonitorRecordDetail>
}

export function useMonitorDetailRuntime(options: MonitorDetailRuntimeOptions) {
  const detailOpen = ref(false)
  const detailLoading = ref(false)
  const detailError = ref('')
  const detailRecord = shallowRef<RealtimeMonitorRecordDetail | null>(null)
  const detailTargetCallId = ref('')
  let detailRequestId = 0

  async function loadDetail(callId: string, initial: boolean) {
    const normalizedCallId = callId.trim()
    if (!normalizedCallId) return
    const requestId = ++detailRequestId
    if (initial) {
      detailLoading.value = true
      detailError.value = ''
      detailRecord.value = null
    }
    try {
      const detail = await options.loadDetail(normalizedCallId)
      if (
        requestId !== detailRequestId
        || !detailOpen.value
        || detailTargetCallId.value !== normalizedCallId
      ) return
      detailRecord.value = detail
      detailError.value = ''
    } catch (caught) {
      if (
        requestId !== detailRequestId
        || !detailOpen.value
        || detailTargetCallId.value !== normalizedCallId
      ) return
      if (initial || !detailRecord.value) {
        detailError.value = errorMessage(caught, '请求详情加载失败')
      }
    } finally {
      if (requestId === detailRequestId && initial) detailLoading.value = false
    }
  }

  function openDetail(row: Pick<RealtimeMonitorRecord, 'call_id'>) {
    const callId = String(row.call_id || '').trim()
    if (!callId) return
    detailOpen.value = true
    detailTargetCallId.value = callId
    void loadDetail(callId, true)
  }

  async function refreshIfRunning() {
    const callId = detailTargetCallId.value
    if (!detailOpen.value || !callId || detailLoading.value) return
    if (detailRecord.value && detailRecord.value.status !== 'running') return
    await loadDetail(callId, false)
  }

  function closeDetail() {
    detailRequestId += 1
    detailOpen.value = false
    detailLoading.value = false
    detailError.value = ''
    detailRecord.value = null
    detailTargetCallId.value = ''
  }

  return {
    detailOpen,
    detailLoading,
    detailError,
    detailRecord,
    openDetail,
    refreshIfRunning,
    closeDetail,
  }
}
