import { ref } from 'vue'
import {
  editableFileTasksApi,
  type EditableFileTask,
  type EditableFileTaskDeleteResponse,
  type EditableFileTasksResponse,
} from '@/api/editableFileTasks'
import { writeClipboardText } from '@/lib/clipboard'

export type StudioRecentFileTasksRuntimeInput = {
  loadRecentTasks?: () => Promise<EditableFileTasksResponse>
  formatError?: (error: unknown) => string
  deleteRecentTask?: (taskId: string) => Promise<EditableFileTaskDeleteResponse>
  copyText?: (value: string) => Promise<void>
}

function defaultErrorMessage(error: unknown) {
  if (error instanceof Error && error.message.trim()) return error.message
  return '最近文件任务加载失败'
}

function taskActionError(error: unknown, fallback: string) {
  if (error instanceof Error && error.message.trim()) return error.message
  return fallback
}

export function useStudioRecentFileTasksRuntime(input: StudioRecentFileTasksRuntimeInput = {}) {
  const tasks = ref<EditableFileTask[]>([])
  const isLoading = ref(false)
  const error = ref('')
  const actionError = ref('')
  const busyTaskIds = ref<ReadonlySet<string>>(new Set())
  const loadRecentTasks = input.loadRecentTasks
    || (() => editableFileTasksApi.list(undefined, 30))
  const deleteRecentTask = input.deleteRecentTask || editableFileTasksApi.delete
  const copyText = input.copyText || writeClipboardText
  const deletedTaskVersions = new Map<string, number>()

  let activeRefresh: Promise<void> | null = null
  let mutationVersion = 0

  function setTaskBusy(taskId: string, busy: boolean) {
    const next = new Set(busyTaskIds.value)
    if (busy) next.add(taskId)
    else next.delete(taskId)
    busyTaskIds.value = next
  }

  function isTaskBusy(taskId: string) {
    return busyTaskIds.value.has(taskId)
  }

  function refresh() {
    if (activeRefresh) return activeRefresh
    const refreshStartedAtVersion = mutationVersion

    activeRefresh = (async () => {
      isLoading.value = true
      error.value = ''
      try {
        const response = await loadRecentTasks()
        tasks.value = response.items.filter((task) => (
          (deletedTaskVersions.get(task.id) || 0) <= refreshStartedAtVersion
        ))
        for (const [taskId, deletedAtVersion] of deletedTaskVersions) {
          if (deletedAtVersion <= refreshStartedAtVersion) deletedTaskVersions.delete(taskId)
        }
      } catch (loadError) {
        error.value = input.formatError?.(loadError) || defaultErrorMessage(loadError)
      } finally {
        isLoading.value = false
        activeRefresh = null
      }
    })()

    return activeRefresh
  }

  async function removeTask(task: EditableFileTask) {
    if (!task.can_delete || isTaskBusy(task.id)) return false
    actionError.value = ''
    setTaskBusy(task.id, true)
    try {
      const response = await deleteRecentTask(task.id)
      mutationVersion += 1
      deletedTaskVersions.set(response.task_id, mutationVersion)
      tasks.value = tasks.value.filter((item) => item.id !== response.task_id)
      return true
    } catch (deleteError) {
      actionError.value = taskActionError(deleteError, '删除文件任务失败')
      return false
    } finally {
      setTaskBusy(task.id, false)
    }
  }

  async function copyTaskError(task: EditableFileTask) {
    if (!task.error || isTaskBusy(task.id)) return false
    actionError.value = ''
    setTaskBusy(task.id, true)
    try {
      await copyText(task.error)
      return true
    } catch (copyError) {
      actionError.value = taskActionError(copyError, '复制错误信息失败')
      return false
    } finally {
      setTaskBusy(task.id, false)
    }
  }

  return {
    tasks,
    isLoading,
    error,
    actionError,
    isTaskBusy,
    refresh,
    removeTask,
    copyTaskError,
  }
}
