import type { Ref } from 'vue'

import type { PromptLibraryView, PromptSource } from '@/api/prompts'
import { useOperationProgressRuntime } from '@/composables/useOperationProgressRuntime'
import { errorMessage } from '@/lib/errorMessage'

type SettingsPromptSourcesOperationRuntimeOptions = {
  sources: Readonly<Ref<PromptSource[]>>
  refreshSources: () => Promise<PromptLibraryView>
}

export function useSettingsPromptSourcesOperationRuntime(
  options: SettingsPromptSourcesOperationRuntimeOptions,
) {
  const progressRuntime = useOperationProgressRuntime()
  const operationProgress = progressRuntime.state

  async function refreshAllSources() {
    const sourceCount = options.sources.value.length
    await progressRuntime.start({
      title: '更新提示词快照',
      subtitle: sourceCount > 0 ? `${sourceCount} 个词源` : '',
      total: 1,
      message: '正在从 image-prompts 下载并更新本地快照...',
    })
    try {
      const result = await options.refreshSources()
      const summary = result.sync_summary
      if (summary.tone === 'danger') progressRuntime.fail(summary.message, 1)
      else if (summary.tone === 'warning') progressRuntime.warn(summary.message, 1)
      else progressRuntime.succeed(summary.message, 1)
      return result
    } catch (error) {
      progressRuntime.fail(errorMessage(error, '提示词源更新失败'))
      return null
    }
  }

  return {
    operationProgress,
    refreshAllSources,
    closeOperationProgress: progressRuntime.close,
  }
}
