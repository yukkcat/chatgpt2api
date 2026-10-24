import { ref } from 'vue'

import type {
  ProxyNodeImportInvalidItem,
  ProxyNodeImportResult,
} from '@/api/proxy'
import { useOperationProgressRuntime } from '@/composables/useOperationProgressRuntime'

interface ProxyNodeImportPayload {
  text: string
  existing_urls?: string[]
}

interface ProxyNodeImportRuntimeOptions {
  importNodes: (payload: ProxyNodeImportPayload) => Promise<ProxyNodeImportResult>
  onApply: (result: ProxyNodeImportResult) => void
  formatError: (error: unknown) => string
}

export function useProxyNodeImportRuntime(options: ProxyNodeImportRuntimeOptions) {
  const sourceText = ref('')
  const formOpen = ref(false)
  const submitting = ref(false)
  const invalidItems = ref<ProxyNodeImportInvalidItem[]>([])
  const submitError = ref('')
  const progressRuntime = useOperationProgressRuntime()
  const operationProgress = progressRuntime.state
  let requestGeneration = 0

  function sourceLineCount() {
    return sourceText.value
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#'))
      .length
  }

  function resultSummary(result: ProxyNodeImportResult) {
    return [
      result.added_count ? `Added ${result.added_count}` : '',
      result.duplicate_count ? `Skipped ${result.duplicate_count} duplicates` : '',
      result.invalid_count ? `${result.invalid_count} invalid lines` : '',
    ].filter(Boolean).join(', ') || 'No proxy nodes to add'
  }

  function activate() {
    requestGeneration += 1
    sourceText.value = ''
    formOpen.value = true
    submitting.value = false
    invalidItems.value = []
    submitError.value = ''
    progressRuntime.reset()
  }

  function deactivate() {
    requestGeneration += 1
    formOpen.value = false
    submitting.value = false
    progressRuntime.reset()
  }

  async function submit(existingUrls: readonly string[]) {
    if (submitting.value || !sourceText.value.trim()) return

    const generation = ++requestGeneration
    submitting.value = true
    formOpen.value = false
    invalidItems.value = []
    submitError.value = ''
    const total = sourceLineCount()

    await progressRuntime.start({
      title: 'Add proxy nodes in bulk',
      subtitle: total ? `${total} lines` : '',
      total,
      message: 'Parsing and removing duplicates...',
    })
    if (generation !== requestGeneration) return

    try {
      const result = await options.importNodes({
        text: sourceText.value,
        existing_urls: [...existingUrls],
      })
      if (generation !== requestGeneration) return

      options.onApply(result)
      invalidItems.value = result.invalid_items
      sourceText.value = result.invalid_items.map((item) => item.raw).join('\n')
      const summary = resultSummary(result)
      if (result.invalid_count || !result.added_count) {
        progressRuntime.warn(summary, total)
      } else {
        progressRuntime.succeed(`${summary}. Save the proxy group to apply changes.`, total)
      }
    } catch (error) {
      if (generation !== requestGeneration) return
      submitError.value = options.formatError(error)
      progressRuntime.fail(submitError.value)
    } finally {
      if (generation === requestGeneration) submitting.value = false
    }
  }

  function closeProgress() {
    if (!progressRuntime.close()) return false
    if (invalidItems.value.length || submitError.value) {
      formOpen.value = true
      return 'resume' as const
    }
    return 'done' as const
  }

  return {
    sourceText,
    formOpen,
    submitting,
    invalidItems,
    submitError,
    operationProgress,
    activate,
    deactivate,
    submit,
    closeProgress,
  }
}
