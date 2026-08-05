import { computed, type Ref } from 'vue'
import type { SystemLogRow, SystemLogsResponse } from '@/api/logs'
import { saveBlob } from '@/lib/downloads'

export type LogExportRuntimeInput = {
  logs: Ref<SystemLogRow[]>
  logMeta: SystemLogsResponse
  currentPage: Readonly<Ref<number>>
}

function exportTimestamp() {
  return new Date().toISOString().slice(0, 19).replace(/:/g, '-')
}

function saveJsonBlob(payload: unknown, filename: string) {
  const blob = new Blob(
    [JSON.stringify(payload, null, 2)],
    { type: 'application/json' },
  )
  saveBlob(blob, filename)
}

export function useLogExportRuntime(input: LogExportRuntimeInput) {
  const exportDisabled = computed(() => input.logs.value.length === 0)

  function exportSystemLogs() {
    saveJsonBlob(
      {
        exported_at: new Date().toISOString(),
        page: input.currentPage.value,
        total: input.logMeta.total,
        logs: input.logs.value.map((item) => item.raw),
      },
      `logs_summary_${exportTimestamp()}.json`,
    )
  }

  return {
    exportDisabled,
    exportSystemLogs,
  }
}
