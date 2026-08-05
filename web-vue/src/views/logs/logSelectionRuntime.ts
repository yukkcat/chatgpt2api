import { computed, ref, type Ref } from 'vue'
import type { SystemLogRow } from '@/api/logs'
import { useOperationProgressRuntime } from '@/composables/useOperationProgressRuntime'
import { errorMessage } from '@/lib/errorMessage'

export type LogSelectionRuntimeInput = {
  visibleLogs: Ref<SystemLogRow[]>
  selectedLog: Ref<SystemLogRow | null>
  closeDetail: () => void
  deleteLogs: (ids: string[]) => Promise<{ removed: number }>
  refreshLogs: () => Promise<void>
}

export function useLogSelectionRuntime(input: LogSelectionRuntimeInput) {
  const selectedLogIds = ref<string[]>([])
  const deleteTarget = ref<SystemLogRow | null>(null)
  const deleteSelectedOpen = ref(false)
  const isDeleting = ref(false)
  const progressRuntime = useOperationProgressRuntime()
  const operationProgress = progressRuntime.state

  const currentLogIdSet = computed(() => new Set(input.visibleLogs.value.map((item) => item.id).filter(Boolean)))
  const selectedDeletableLogIds = computed(() => (
    Array.from(new Set(selectedLogIds.value)).filter((id) => currentLogIdSet.value.has(id))
  ))
  const selectedLogIdSet = computed(() => new Set(selectedDeletableLogIds.value))
  const selectedLogCount = computed(() => selectedDeletableLogIds.value.length)
  const allVisibleLogsSelected = computed(() => {
    if (input.visibleLogs.value.length === 0) return false
    return input.visibleLogs.value.every((item) => selectedLogIdSet.value.has(item.id))
  })
  const someVisibleLogsSelected = computed(() => (
    !allVisibleLogsSelected.value
    && input.visibleLogs.value.some((item) => selectedLogIdSet.value.has(item.id))
  ))

  function pruneSelectionToVisible() {
    selectedLogIds.value = selectedLogIds.value.filter((id) => currentLogIdSet.value.has(id))
  }

  function isLogSelected(id: string): boolean {
    return selectedLogIdSet.value.has(id)
  }

  function toggleLogSelection(id: string, checked?: boolean) {
    const next = new Set(selectedLogIds.value)
    const shouldSelect = typeof checked === 'boolean' ? checked : !next.has(id)
    if (shouldSelect) next.add(id)
    else next.delete(id)
    selectedLogIds.value = Array.from(next)
  }

  function toggleSelectAllVisibleLogs(checked?: boolean) {
    const next = new Set(selectedLogIds.value)
    const shouldSelect = typeof checked === 'boolean' ? checked : !allVisibleLogsSelected.value
    input.visibleLogs.value.forEach((item) => {
      if (shouldSelect) next.add(item.id)
      else next.delete(item.id)
    })
    selectedLogIds.value = Array.from(next)
  }

  function clearLogSelection() {
    selectedLogIds.value = []
  }

  function removeSelectedLogIds(ids: readonly string[]) {
    const deleted = new Set(ids)
    selectedLogIds.value = selectedLogIds.value.filter((id) => !deleted.has(id))
  }

  function requestDeleteLog(item: SystemLogRow) {
    deleteTarget.value = item
  }

  function requestDeleteSelectedLogs() {
    if (selectedLogCount.value === 0) return
    deleteSelectedOpen.value = true
  }

  async function executeLogDelete(ids: string[], item: SystemLogRow | null) {
    if (ids.length === 0) return
    deleteTarget.value = null
    deleteSelectedOpen.value = false
    isDeleting.value = true
    const isBatch = ids.length > 1
    await progressRuntime.start({
      title: isBatch ? '批量删除日志' : '删除日志',
      subtitle: item ? item.time || item.id : `已选择 ${ids.length} 条`,
      total: ids.length,
      message: isBatch ? '正在提交批量删除请求...' : '正在提交删除请求...',
    })
    try {
      const result = await input.deleteLogs(ids)
      const removed = Number(result.removed ?? ids.length)
      progressRuntime.record({ label: '刷新列表', message: '删除完成，正在刷新列表...' })
      if (input.selectedLog.value && ids.includes(input.selectedLog.value.id)) input.closeDetail()
      removeSelectedLogIds(ids)
      await input.refreshLogs()
      progressRuntime.succeed(isBatch ? `已删除 ${removed} 条日志` : '日志已删除', removed)
    } catch (error) {
      const message = errorMessage(error, '删除失败')
      progressRuntime.fail(message)
    } finally {
      isDeleting.value = false
    }
  }

  async function confirmDeleteRequest() {
    const item = deleteTarget.value
    const ids = item
      ? [item.id]
      : deleteSelectedOpen.value
        ? selectedDeletableLogIds.value
        : []
    await executeLogDelete(ids, item)
  }

  return {
    selectedLogIds,
    deleteTarget,
    deleteSelectedOpen,
    isDeleting,
    operationProgress,
    closeOperationProgress: progressRuntime.close,
    selectedDeletableLogIds,
    selectedLogIdSet,
    selectedLogCount,
    allVisibleLogsSelected,
    someVisibleLogsSelected,
    pruneSelectionToVisible,
    isLogSelected,
    toggleLogSelection,
    toggleSelectAllVisibleLogs,
    clearLogSelection,
    requestDeleteLog,
    requestDeleteSelectedLogs,
    confirmDeleteRequest,
  }
}
