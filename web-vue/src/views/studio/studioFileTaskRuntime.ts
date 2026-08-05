import { computed, ref, type ComputedRef } from 'vue'
import {
  editableFileTasksApi,
  type EditableFileTask,
} from '@/api/editableFileTasks'
import type { PageRuntime } from '@/composables/usePageRuntime'
import type {
  StudioConversation,
  StudioConversationBadgeState,
} from '@/components/studio/types'
import type {
  StudioConversationRuntimeIndex,
} from './studioConversationState'
import { useStudioTaskPollingCoordinator } from './studioTaskPollingCoordinator'

const FILE_POLL_TIMER_KEY = 'studio:file-poll'
const FILE_REFRESH_TIMER_KEY = 'studio:file-refresh'
const FILE_TASKS_REQUEST_KEY = 'studio:file-tasks'

export type StudioFileTaskRuntimeHooks = {
  markConversationNotice: (conversationId: string, state: StudioConversationBadgeState) => void
  touchConversation: (conversation: StudioConversation) => void
  onRefreshError: (message: string) => void
  onRefreshSuccess?: () => void
  formatError: (error: unknown, fallback: string) => string
}

export type StudioFileTaskRuntimeInput = {
  pageRuntime: PageRuntime
  activeConversation: ComputedRef<StudioConversation | null>
  conversationRuntimeIndex: ComputedRef<StudioConversationRuntimeIndex>
  hooks: StudioFileTaskRuntimeHooks
}

export function useStudioFileTaskRuntime(input: StudioFileTaskRuntimeInput) {
  const fileTasks = ref<EditableFileTask[]>([])
  const taskById = computed(() => new Map(fileTasks.value.map((task) => [task.id, task])))
  const activeFileTaskIds = computed(() => {
    const ids = input.activeConversation.value?.messages
      .filter((message) => !message.fileTaskDeleted)
      .map((message) => message.fileTaskId)
      .filter((id): id is string => Boolean(id)) || []
    return Array.from(new Set(ids)).slice(0, 80)
  })
  const pendingFileTaskIds = computed(() => input.conversationRuntimeIndex.value.pendingFileTaskIds)
  const requestedFileTaskIds = computed(() => Array.from(new Set([
    ...activeFileTaskIds.value,
    ...pendingFileTaskIds.value,
  ])).slice(0, 180))

  function mergeTaskItems(items: EditableFileTask[]) {
    const tasks = new Map(fileTasks.value.map((task) => [task.id, task]))
    items.filter((task) => task.id).forEach((task) => tasks.set(task.id, task))
    fileTasks.value = Array.from(tasks.values())
  }

  function markMissing(taskIds: string[]) {
    const missing = new Set(taskIds.filter(Boolean))
    if (!missing.size) return
    fileTasks.value = fileTasks.value.filter((task) => !missing.has(task.id))
    const changedConversations = new Set<StudioConversation>()
    input.conversationRuntimeIndex.value.fileTaskMessageEntries.forEach(({ conversation, message }) => {
      if (!message.fileTaskId || !missing.has(message.fileTaskId)) return
      if (message.status === 'error') return
      message.status = 'error'
      message.error = '文件任务已过期或不存在'
      changedConversations.add(conversation)
      input.hooks.markConversationNotice(conversation.id, 'error')
    })
    changedConversations.forEach(input.hooks.touchConversation)
  }

  function markDeleted(taskIds: string[]) {
    const deleted = new Set(taskIds.filter(Boolean))
    if (!deleted.size) return
    fileTasks.value = fileTasks.value.filter((task) => !deleted.has(task.id))
    taskPollingCoordinator.invalidateRefreshSignature()
    const changedConversations = new Set<StudioConversation>()
    input.conversationRuntimeIndex.value.fileTaskMessageEntries.forEach(({ conversation, message }) => {
      if (!message.fileTaskId || !deleted.has(message.fileTaskId)) return
      message.fileTaskDeleted = true
      message.status = 'done'
      message.error = undefined
      changedConversations.add(conversation)
    })
    changedConversations.forEach(input.hooks.touchConversation)
  }

  function syncMessageStatuses() {
    const changedConversations = new Set<StudioConversation>()
    input.conversationRuntimeIndex.value.fileTaskMessageEntries.forEach(({ conversation, message }) => {
      if (!message.fileTaskId) return
      const task = taskById.value.get(message.fileTaskId)
      if (!task) return
      const previousStatus = message.status
      const previousError = message.error
      if (task.status === 'queued' || task.status === 'running') {
        message.status = task.status
        message.error = undefined
      } else if (task.status === 'success') {
        message.status = 'done'
        message.error = undefined
        if (previousStatus !== 'done') input.hooks.markConversationNotice(conversation.id, 'done')
      } else {
        message.status = 'error'
        message.error = task.error
        if (previousStatus !== 'error') input.hooks.markConversationNotice(conversation.id, 'error')
      }
      if (message.status !== previousStatus || message.error !== previousError) {
        changedConversations.add(conversation)
      }
    })
    changedConversations.forEach(input.hooks.touchConversation)
  }

  const taskPollingCoordinator = useStudioTaskPollingCoordinator({
    pageRuntime: input.pageRuntime,
    requestedTaskIds: requestedFileTaskIds,
    pendingTaskIds: pendingFileTaskIds,
    requestKey: FILE_TASKS_REQUEST_KEY,
    pollTimerKey: FILE_POLL_TIMER_KEY,
    refreshTimerKey: FILE_REFRESH_TIMER_KEY,
    loadTasks: editableFileTasksApi.list,
    applyResponse: (response) => {
      mergeTaskItems(response.items)
      markMissing(response.missing_ids)
      syncMessageStatuses()
    },
    clearTasks: () => {
      fileTasks.value = []
    },
    onRefreshSuccess: input.hooks.onRefreshSuccess,
    onRefreshError: (error) => {
      input.hooks.onRefreshError(input.hooks.formatError(error, '刷新文件任务失败'))
    },
  })

  function merge(items: EditableFileTask[]) {
    mergeTaskItems(items)
    taskPollingCoordinator.invalidateRefreshSignature()
  }

  function reset() {
    fileTasks.value = []
    taskPollingCoordinator.invalidateRefreshSignature()
  }

  return {
    fileTasks,
    isFetchingTasks: taskPollingCoordinator.isFetchingTasks,
    taskById,
    activeFileTaskIds,
    pendingFileTaskIds,
    requestedFileTaskIds,
    refresh: taskPollingCoordinator.refresh,
    merge,
    markMissing,
    markDeleted,
    reset,
    schedulePoll: taskPollingCoordinator.schedulePoll,
    scheduleRefresh: taskPollingCoordinator.scheduleRefresh,
    deactivate: taskPollingCoordinator.deactivate,
    dispose: taskPollingCoordinator.dispose,
  }
}
