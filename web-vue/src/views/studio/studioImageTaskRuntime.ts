import { computed, ref, type ComputedRef } from 'vue'
import {
  imageTasksApi,
  type ImageTask,
} from '@/api/imageTasks'
import type { PageRuntime } from '@/composables/usePageRuntime'
import type {
  StudioConversation,
  StudioConversationBadge,
  StudioConversationBadgeState,
} from '@/components/studio/types'
import { getJsonPreference, preferenceKeys, setJsonPreference } from '@/lib/preferences'
import { isStudioImageMessageRunning, type StudioConversationLookup, type StudioConversationRuntimeIndex } from './studioConversationState'
import { cleanStudioText } from './studioSearchView'
import { useStudioTaskPollingCoordinator } from './studioTaskPollingCoordinator'

const IMAGE_POLL_TIMER_KEY = 'studio:image-poll'
const IMAGE_REFRESH_TIMER_KEY = 'studio:image-refresh'
const IMAGE_TASKS_REQUEST_KEY = 'studio:image-tasks'

export type StudioImageTaskRuntimeHooks = {
  markConversationNotice: (conversationId: string, state: StudioConversationBadgeState) => void
  touchConversation: (conversation: StudioConversation) => void
  onRefreshError: (message: string) => void
  onRefreshSuccess?: () => void
  formatError: (error: unknown, fallback: string) => string
}

export type StudioImageTaskRuntimeInput = {
  pageRuntime: PageRuntime
  activeConversation: ComputedRef<StudioConversation | null>
  conversationNotices: ComputedRef<Record<string, StudioConversationBadgeState>>
  conversationLookup: ComputedRef<StudioConversationLookup>
  conversationRuntimeIndex: ComputedRef<StudioConversationRuntimeIndex>
  hooks: StudioImageTaskRuntimeHooks
}

export function useStudioImageTaskRuntime(input: StudioImageTaskRuntimeInput) {
  const imageTasks = ref<ImageTask[]>([])
  const taskById = computed(() => new Map(imageTasks.value.map((task) => [task.id, task])))
  const activeImageTaskIds = computed(() => {
    const ids = input.activeConversation.value?.messages
      .map((message) => message.taskId)
      .filter((id): id is string => Boolean(id)) || []
    return Array.from(new Set(ids)).slice(0, 80)
  })
  const pendingImageTaskIds = computed(() => input.conversationRuntimeIndex.value.pendingImageTaskIds)
  const requestedImageTaskIds = computed(() => Array.from(new Set([
    ...activeImageTaskIds.value,
    ...pendingImageTaskIds.value,
  ])).slice(0, 180))
  const activeRunningTaskCount = computed(() => {
    const conversation = input.activeConversation.value
    if (!conversation) return 0
    return conversation.messages.reduce((total, message) => {
      if (isStudioImageMessageRunning(message)) return total + 1
      if (message.status === 'sending' || message.status === 'streaming') return total + 1
      return total
    }, 0)
  })
  const conversationBadges = computed<Record<string, StudioConversationBadge>>(() => {
    const badges: Record<string, StudioConversationBadge> = {}
    const runtime = input.conversationRuntimeIndex.value
    const validIds = input.conversationLookup.value.validIds
    Object.entries(runtime.runningCounts).forEach(([conversationId, running]) => {
      if (running > 0) {
        badges[conversationId] = {
          state: 'running',
          label: `处理中 ${running}`,
          count: running,
        }
      }
    })
    Object.entries(input.conversationNotices.value).forEach(([conversationId, notice]) => {
      if (!validIds.has(conversationId) || badges[conversationId]) return
      if (notice === 'done') {
        badges[conversationId] = { state: 'done', label: '已完成' }
      } else if (notice === 'error') {
        badges[conversationId] = { state: 'error', label: '失败' }
      }
    })
    return badges
  })

  function storedImageTaskIds() {
    const ids = getJsonPreference<unknown[]>(preferenceKeys.imageTaskLocalIds, [])
    return Array.isArray(ids) ? ids.map((id) => cleanStudioText(id)).filter(Boolean) : []
  }

  function rememberTask(taskId: string) {
    if (!taskId) return
    const ids = Array.from(new Set([taskId, ...storedImageTaskIds()])).slice(0, 160)
    setJsonPreference(preferenceKeys.imageTaskLocalIds, ids)
  }

  function mergeTaskItems(items: ImageTask[]) {
    const map = new Map(imageTasks.value.map((task) => [task.id, task]))
    items.filter((task) => task.id).forEach((task) => map.set(task.id, task))
    imageTasks.value = Array.from(map.values())
  }

  function markMissing(taskIds: string[]) {
    const missing = new Set(taskIds.filter(Boolean))
    if (!missing.size) return
    imageTasks.value = imageTasks.value.filter((task) => !missing.has(task.id) || task.terminal)
    const changedConversations = new Set<StudioConversation>()
    input.conversationRuntimeIndex.value.imageTaskMessageEntries.forEach(({ conversation, message }) => {
      if (!message.taskId || !missing.has(message.taskId)) return
      if (message.status === 'done' || message.status === 'error') return
      message.status = 'error'
      message.error = '图片任务已过期或不存在'
      changedConversations.add(conversation)
      input.hooks.markConversationNotice(conversation.id, 'error')
    })
    changedConversations.forEach(input.hooks.touchConversation)
  }

  function syncMessageStatuses() {
    const changedConversations = new Set<StudioConversation>()
    input.conversationRuntimeIndex.value.imageTaskMessageEntries.forEach(({ conversation, message }) => {
      if (!message.taskId) return
      const task = taskById.value.get(message.taskId)
      if (!task) return
      const previousStatus = message.status
      if (!task.terminal) {
        message.status = 'running'
        message.error = undefined
      } else if (task.status === 'success' || task.status === 'partial_success' || task.status === 'text_review') {
        message.status = 'done'
        message.error = undefined
        if (previousStatus !== 'done') input.hooks.markConversationNotice(conversation.id, 'done')
      } else {
        message.status = 'error'
        message.error = task.public_error
        if (previousStatus !== 'error') input.hooks.markConversationNotice(conversation.id, 'error')
      }
      if (message.status !== previousStatus) changedConversations.add(conversation)
    })
    changedConversations.forEach(input.hooks.touchConversation)
  }

  const taskPollingCoordinator = useStudioTaskPollingCoordinator({
    pageRuntime: input.pageRuntime,
    requestedTaskIds: requestedImageTaskIds,
    pendingTaskIds: pendingImageTaskIds,
    requestKey: IMAGE_TASKS_REQUEST_KEY,
    pollTimerKey: IMAGE_POLL_TIMER_KEY,
    refreshTimerKey: IMAGE_REFRESH_TIMER_KEY,
    loadTasks: imageTasksApi.list,
    applyResponse: (response) => {
      mergeTaskItems(response.items)
      markMissing(response.missing_ids)
      syncMessageStatuses()
    },
    clearTasks: () => {
      imageTasks.value = []
    },
    onRefreshSuccess: input.hooks.onRefreshSuccess,
    onRefreshError: (error) => {
      input.hooks.onRefreshError(input.hooks.formatError(error, '刷新图片任务失败'))
    },
  })

  function merge(items: ImageTask[]) {
    mergeTaskItems(items)
    taskPollingCoordinator.invalidateRefreshSignature()
  }

  async function resumePoll(taskId: string) {
    const normalizedTaskId = cleanStudioText(taskId)
    if (!normalizedTaskId) return null
    try {
      const task = await imageTasksApi.resumePoll(normalizedTaskId)
      merge([task])
      syncMessageStatuses()
      taskPollingCoordinator.schedulePoll()
      return task
    } catch (error) {
      input.hooks.onRefreshError(input.hooks.formatError(error, '继续图片任务失败'))
      return null
    }
  }

  function reset() {
    imageTasks.value = []
    taskPollingCoordinator.invalidateRefreshSignature()
  }

  return {
    imageTasks,
    isFetchingTasks: taskPollingCoordinator.isFetchingTasks,
    taskById,
    activeImageTaskIds,
    pendingImageTaskIds,
    requestedImageTaskIds,
    activeRunningTaskCount,
    conversationBadges,
    rememberTask,
    resumePoll,
    refresh: taskPollingCoordinator.refresh,
    merge,
    reset,
    schedulePoll: taskPollingCoordinator.schedulePoll,
    scheduleRefresh: taskPollingCoordinator.scheduleRefresh,
    deactivate: taskPollingCoordinator.deactivate,
    dispose: taskPollingCoordinator.dispose,
  }
}
