import type { Ref } from 'vue'
import type { StudioConversation, StudioConversationBadgeState } from '@/components/studio/types'
import {
  buildStudioConversationTitle,
  createStudioId,
  type StudioConversationLookup,
} from './studioConversationState'
import type { StudioConversationPersistenceRuntime } from './studioConversationPersistenceRuntime'
import type { StudioConversationSelectionRuntime } from './studioConversationSelectionRuntime'

type StudioConversationLookupRef = {
  value: StudioConversationLookup
}

export type StudioConversationActionsRuntimeHooks = {
  cancelMessageEdit: (clearComposer?: boolean) => void
  resetTasks: () => void
  scheduleScrollToBottom: () => void
}

export type StudioConversationActionsRuntimeInput = {
  conversations: Ref<StudioConversation[]>
  activeConversationId: Ref<string>
  activeConversation: Ref<StudioConversation | null>
  conversationNotices: Ref<Record<string, StudioConversationBadgeState>>
  conversationLookup: StudioConversationLookupRef
  persistenceRuntime: Pick<StudioConversationPersistenceRuntime, 'scheduleConversationNotices' | 'scheduleConversations'>
  selectionRuntime: Pick<StudioConversationSelectionRuntime, 'cancel' | 'select'>
  hooks: StudioConversationActionsRuntimeHooks
}

export function useStudioConversationActionsRuntime(input: StudioConversationActionsRuntimeInput) {
  function ensureConversation(content = '') {
    if (input.activeConversation.value) return input.activeConversation.value
    return createConversation(content)
  }

  function createConversation(seed = '') {
    input.selectionRuntime.cancel()
    input.hooks.cancelMessageEdit(false)
    const seedText = typeof seed === 'string' ? seed : ''
    const now = new Date().toISOString()
    const conversation: StudioConversation = {
      id: createStudioId('studio'),
      title: seedText ? buildStudioConversationTitle(seedText) : '新对话',
      createdAt: now,
      updatedAt: now,
      messages: [],
    }
    input.conversations.value = [conversation, ...input.conversations.value]
    input.activeConversationId.value = conversation.id
    input.hooks.scheduleScrollToBottom()
    return conversation
  }

  function selectConversation(conversationId: string) {
    input.selectionRuntime.select(conversationId)
  }

  function renameConversation(conversationId: string, title: string) {
    const conversation = input.conversationLookup.value.byId.get(conversationId)
    if (!conversation) return
    const nextTitle = title.trim()
    conversation.title = nextTitle || '新对话'
    touchConversation(conversation)
  }

  function reorderConversation(sourceId: string, targetId: string) {
    if (!sourceId || !targetId || sourceId === targetId) return
    const sourceIndex = input.conversations.value.findIndex((item) => item.id === sourceId)
    const targetIndex = input.conversations.value.findIndex((item) => item.id === targetId)
    if (sourceIndex < 0 || targetIndex < 0) return
    const next = input.conversations.value.slice()
    const [moved] = next.splice(sourceIndex, 1)
    next.splice(targetIndex, 0, moved)
    input.conversations.value = next
    input.persistenceRuntime.scheduleConversations()
  }

  function prepareDeleteConversation(conversationId: string) {
    input.selectionRuntime.cancel()
    return input.conversationLookup.value.byId.get(conversationId) || null
  }

  function deleteConversation(conversationId: string) {
    input.conversations.value = input.conversations.value.filter((item) => item.id !== conversationId)
    clearConversationNotice(conversationId)
    if (input.activeConversationId.value === conversationId) {
      input.activeConversationId.value = input.conversations.value[0]?.id || ''
    }
    if (!input.conversations.value.length) createConversation()
    input.persistenceRuntime.scheduleConversations()
  }

  function prepareClearHistory() {
    input.selectionRuntime.cancel()
    return input.conversations.value.length > 0
  }

  function clearHistory() {
    input.hooks.cancelMessageEdit()
    input.conversations.value = []
    input.hooks.resetTasks()
    input.conversationNotices.value = {}
    input.activeConversationId.value = ''
    createConversation()
  }

  function clearCurrentConversation(conversationId?: string) {
    const conversation = conversationId
      ? input.conversationLookup.value.byId.get(conversationId)
      : input.activeConversation.value
    if (!conversation?.messages.length) return null
    input.hooks.cancelMessageEdit()
    conversation.messages = []
    conversation.title = '新对话'
    clearConversationNotice(conversation.id)
    touchConversation(conversation)
    input.hooks.resetTasks()
    input.hooks.scheduleScrollToBottom()
    return conversation
  }

  function touchConversation(conversation: StudioConversation) {
    conversation.updatedAt = new Date().toISOString()
    input.persistenceRuntime.scheduleConversations()
  }

  function markConversationNotice(conversationId: string, state: StudioConversationBadgeState) {
    if (!conversationId) return
    const current = input.conversationNotices.value[conversationId]
    const nextState = current === 'error' && state === 'done' ? current : state
    input.conversationNotices.value = {
      ...input.conversationNotices.value,
      [conversationId]: nextState,
    }
    input.persistenceRuntime.scheduleConversationNotices()
  }

  function clearConversationNotice(conversationId: string) {
    if (!conversationId || !input.conversationNotices.value[conversationId]) return
    const next = { ...input.conversationNotices.value }
    delete next[conversationId]
    input.conversationNotices.value = next
    input.persistenceRuntime.scheduleConversationNotices()
  }

  return {
    clearConversationNotice,
    clearCurrentConversation,
    clearHistory,
    createConversation,
    deleteConversation,
    ensureConversation,
    markConversationNotice,
    prepareClearHistory,
    prepareDeleteConversation,
    renameConversation,
    reorderConversation,
    selectConversation,
    touchConversation,
  }
}
