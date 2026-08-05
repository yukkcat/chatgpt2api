import { ref, watch, type ComputedRef } from 'vue'
import type { PageRuntime } from '@/composables/usePageRuntime'

export type StudioTaskListResponse<Task> = {
  items: Task[]
  missing_ids: string[]
}

export type StudioTaskPollingCoordinatorInput<Task> = {
  pageRuntime: PageRuntime
  requestedTaskIds: ComputedRef<string[]>
  pendingTaskIds: ComputedRef<string[]>
  requestKey: string
  pollTimerKey: string
  refreshTimerKey: string
  loadTasks: (ids: string[]) => Promise<StudioTaskListResponse<Task>>
  applyResponse: (response: StudioTaskListResponse<Task>) => void
  clearTasks: () => void
  onRefreshError: (error: unknown) => void
  onRefreshSuccess?: () => void
  pollIntervalMs?: number
  refreshDelayMs?: number
}

export function useStudioTaskPollingCoordinator<Task>(
  input: StudioTaskPollingCoordinatorInput<Task>,
) {
  const isFetchingTasks = ref(false)
  const pollIntervalMs = input.pollIntervalMs ?? 4000
  const refreshDelayMs = input.refreshDelayMs ?? 120

  let refreshQueued = false
  let refreshQueuedForce = false
  let lastSuccessfulRefreshSignature = ''

  function invalidateRefreshSignature() {
    lastSuccessfulRefreshSignature = ''
  }

  async function refresh(force = false) {
    if (!input.pageRuntime.canRun.value) return
    if (isFetchingTasks.value) {
      refreshQueued = true
      refreshQueuedForce = refreshQueuedForce || force
      return
    }

    const ids = input.requestedTaskIds.value
    const signature = ids.join('\u0000')
    if (!force && signature && signature === lastSuccessfulRefreshSignature) return
    if (!ids.length) {
      input.clearTasks()
      invalidateRefreshSignature()
      return
    }

    const requestSeq = input.pageRuntime.nextRequest(input.requestKey)
    isFetchingTasks.value = true
    try {
      const response = await input.loadTasks(ids)
      if (!input.pageRuntime.isLatestRequest(input.requestKey, requestSeq)) return
      input.applyResponse(response)
      input.onRefreshSuccess?.()
      lastSuccessfulRefreshSignature = signature
    } catch (error) {
      if (!input.pageRuntime.isLatestRequest(input.requestKey, requestSeq)) return
      input.onRefreshError(error)
      invalidateRefreshSignature()
    } finally {
      if (!input.pageRuntime.isLatestRequest(input.requestKey, requestSeq)) return
      isFetchingTasks.value = false
      if (refreshQueued) {
        const queuedForce = refreshQueuedForce
        refreshQueued = false
        refreshQueuedForce = false
        scheduleRefresh(0, queuedForce)
      }
    }
  }

  function schedulePoll() {
    input.pageRuntime.clearInterval(input.pollTimerKey)
    if (!input.pageRuntime.canRun.value || !input.pendingTaskIds.value.length) return
    input.pageRuntime.setInterval(input.pollTimerKey, pollIntervalMs, () => {
      void refresh(true)
    })
  }

  function scheduleRefresh(delay = refreshDelayMs, force = false) {
    if (!input.pageRuntime.canRun.value) return
    input.pageRuntime.setTimer(input.refreshTimerKey, delay, () => {
      void refresh(force)
    })
  }

  function deactivate() {
    input.pageRuntime.invalidateRequest(input.requestKey)
    isFetchingTasks.value = false
    refreshQueued = false
    refreshQueuedForce = false
    invalidateRefreshSignature()
    input.pageRuntime.clearInterval(input.pollTimerKey)
    input.pageRuntime.clearTimer(input.refreshTimerKey)
  }

  const stopRequestedTaskWatch = watch(input.requestedTaskIds, () => scheduleRefresh())
  const stopPendingTaskWatch = watch(input.pendingTaskIds, schedulePoll)

  function dispose() {
    deactivate()
    stopRequestedTaskWatch()
    stopPendingTaskWatch()
  }

  return {
    isFetchingTasks,
    refresh,
    invalidateRefreshSignature,
    schedulePoll,
    scheduleRefresh,
    deactivate,
    dispose,
  }
}
