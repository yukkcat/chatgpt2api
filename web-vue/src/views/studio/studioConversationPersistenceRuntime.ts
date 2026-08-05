import { type Ref, watch } from 'vue'
import { getStringPreference, preferenceKeys, setStringPreference } from '@/lib/preferences'
import { scheduleIdleTask, type IdleTaskHandle } from '@/lib/idleTask'
import type { StudioConversation, StudioConversationBadgeState } from '@/components/studio/types'
import {
  loadStudioConversationNotices,
  loadStudioConversations,
  persistStudioConversationNotices,
  persistStudioConversations,
} from './studioConversationState'

type StudioConversationIdSetRef = {
  value: Set<string>
}

export type StudioConversationPersistenceRuntimeInput = {
  conversations: Ref<StudioConversation[]>
  conversationNotices: Ref<Record<string, StudioConversationBadgeState>>
  activeConversationId: Ref<string>
  validConversationIds: StudioConversationIdSetRef
}

export function loadStudioConversationPersistenceState() {
  return {
    activeConversationId: getStringPreference(preferenceKeys.studioActiveConversationId, ''),
    conversationNotices: loadStudioConversationNotices(),
    conversations: loadStudioConversations(),
  }
}

export type StudioConversationPersistenceRuntime = ReturnType<typeof useStudioConversationPersistenceRuntime>

export function useStudioConversationPersistenceRuntime(input: StudioConversationPersistenceRuntimeInput) {
  let conversationsTimer: number | null = null
  let conversationNoticesTimer: number | null = null
  let activeConversationTimer: number | null = null
  let conversationsIdleTask: IdleTaskHandle | null = null
  let conversationNoticesIdleTask: IdleTaskHandle | null = null

  const stopConversationWatch = watch(input.conversations, scheduleConversations)
  const stopConversationNoticeWatch = watch(input.conversationNotices, scheduleConversationNotices)
  const stopActiveConversationWatch = watch(input.activeConversationId, scheduleActiveConversationId)

  function scheduleConversations() {
    if (conversationsTimer !== null) return
    conversationsTimer = window.setTimeout(() => {
      conversationsTimer = null
      conversationsIdleTask?.cancel()
      conversationsIdleTask = scheduleIdleTask(() => {
        conversationsIdleTask = null
        persistStudioConversations(input.conversations.value)
      }, 1200)
    }, 300)
  }

  function scheduleConversationNotices() {
    if (conversationNoticesTimer !== null) return
    conversationNoticesTimer = window.setTimeout(() => {
      conversationNoticesTimer = null
      conversationNoticesIdleTask?.cancel()
      conversationNoticesIdleTask = scheduleIdleTask(() => {
        conversationNoticesIdleTask = null
        persistStudioConversationNotices(input.conversationNotices.value, input.validConversationIds.value)
      }, 1200)
    }, 300)
  }

  function scheduleActiveConversationId() {
    if (activeConversationTimer !== null) {
      window.clearTimeout(activeConversationTimer)
    }
    activeConversationTimer = window.setTimeout(() => {
      activeConversationTimer = null
      setStringPreference(preferenceKeys.studioActiveConversationId, input.activeConversationId.value)
    }, 200)
  }

  function flushConversations() {
    if (conversationsTimer !== null) {
      window.clearTimeout(conversationsTimer)
      conversationsTimer = null
    }
    if (conversationsIdleTask) {
      conversationsIdleTask.flush()
      conversationsIdleTask = null
      return
    }
    persistStudioConversations(input.conversations.value)
  }

  function flushConversationNotices() {
    if (conversationNoticesTimer !== null) {
      window.clearTimeout(conversationNoticesTimer)
      conversationNoticesTimer = null
    }
    if (conversationNoticesIdleTask) {
      conversationNoticesIdleTask.flush()
      conversationNoticesIdleTask = null
      return
    }
    persistStudioConversationNotices(input.conversationNotices.value, input.validConversationIds.value)
  }

  function flushActiveConversationId() {
    if (activeConversationTimer !== null) {
      window.clearTimeout(activeConversationTimer)
      activeConversationTimer = null
    }
    setStringPreference(preferenceKeys.studioActiveConversationId, input.activeConversationId.value)
  }

  function flush() {
    if (conversationsTimer !== null || conversationsIdleTask) flushConversations()
    if (conversationNoticesTimer !== null || conversationNoticesIdleTask) flushConversationNotices()
    if (activeConversationTimer !== null) flushActiveConversationId()
  }

  function dispose() {
    stopConversationWatch()
    stopConversationNoticeWatch()
    stopActiveConversationWatch()
    flush()
  }

  return {
    flush,
    scheduleConversationNotices,
    scheduleConversations,
    dispose,
  }
}
