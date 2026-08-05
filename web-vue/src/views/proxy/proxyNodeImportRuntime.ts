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
      result.added_count ? `已添加 ${result.added_count} 个` : '',
      result.duplicate_count ? `跳过重复 ${result.duplicate_count} 个` : '',
      result.invalid_count ? `${result.invalid_count} 行格式错误` : '',
    ].filter(Boolean).join('，') || '没有可添加的代理节点'
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
      title: '批量添加代理节点',
      subtitle: total ? `${total} 行` : '',
      total,
      message: '正在解析并去重...',
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
        progressRuntime.succeed(`${summary}；保存代理组后生效`, total)
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
