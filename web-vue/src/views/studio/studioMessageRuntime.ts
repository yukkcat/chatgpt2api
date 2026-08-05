import type { Ref } from 'vue'
import type { StudioConversation, StudioMessage } from '@/components/studio/types'
import { buildStudioConversationTitle, createStudioId } from './studioConversationState'

export type StudioMessageTarget = {
  conversation: StudioConversation
  index: number
  message: StudioMessage
}

export type StudioMessageRuntimeHooks = {
  touchConversation: (conversation: StudioConversation) => void
  scheduleScrollToBottom: () => void
}

export type StudioMessageRuntimeInput = {
  conversations: Ref<StudioConversation[]>
  activeConversation: Ref<StudioConversation | null>
  hooks: StudioMessageRuntimeHooks
}

export function useStudioMessageRuntime(input: StudioMessageRuntimeInput) {
  function findMessage(messageId: string): StudioMessageTarget | null {
    if (!messageId) return null
    for (const conversation of input.conversations.value) {
      const index = conversation.messages.findIndex((item) => item.id === messageId)
      if (index >= 0) return { conversation, index, message: conversation.messages[index] }
    }
    return null
  }

  function addMessage(conversation: StudioConversation, message: Omit<StudioMessage, 'id' | 'createdAt'>) {
    const next: StudioMessage = {
      id: createStudioId('message'),
      createdAt: new Date().toISOString(),
      ...message,
    }
    conversation.messages.push(next)
    const inserted = conversation.messages[conversation.messages.length - 1] || next
    input.hooks.touchConversation(conversation)
    if (conversation.title === '新对话' && message.role === 'user') {
      conversation.title = buildStudioConversationTitle(message.content)
    }
    input.hooks.scheduleScrollToBottom()
    return inserted
  }

  function deleteActiveMessage(messageId: string) {
    const conversation = input.activeConversation.value
    if (!conversation) return null
    conversation.messages = conversation.messages.filter((message) => message.id !== messageId)
    input.hooks.touchConversation(conversation)
    return conversation
  }

  function replaceFromTarget(target: StudioMessageTarget, message: StudioMessage) {
    const { conversation, index } = target
    conversation.messages = [
      ...conversation.messages.slice(0, index),
      message,
    ]
    if (!conversation.messages.slice(0, index).some((item) => item.role === 'user')) {
      conversation.title = buildStudioConversationTitle(message.content)
    }
    input.hooks.touchConversation(conversation)
  }

  function pruneAfterTarget(target: StudioMessageTarget) {
    target.conversation.messages = target.conversation.messages.slice(0, target.index)
    input.hooks.touchConversation(target.conversation)
  }

  function findPreviousUserMessage(target: StudioMessageTarget) {
    return target.conversation.messages
      .slice(0, target.index)
      .reverse()
      .find((item) => item.role === 'user' && item.content.trim()) || null
  }

  return {
    addMessage,
    deleteActiveMessage,
    findMessage,
    findPreviousUserMessage,
    pruneAfterTarget,
    replaceFromTarget,
  }
}
