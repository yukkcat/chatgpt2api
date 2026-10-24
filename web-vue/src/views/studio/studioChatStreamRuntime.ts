import { ref } from 'vue'
import type { StudioConversation, StudioConversationBadgeState, StudioMessage } from '@/components/studio/types'
import { streamStudioChatReply, studioErrorMessage } from './studioRequestView'

export type StudioChatStreamRuntimeHooks = {
  touchConversation: (conversation: StudioConversation) => void
  scheduleScrollToBottom: () => void
  markConversationNotice: (conversationId: string, state: StudioConversationBadgeState) => void
}

export type StudioChatStreamInput = {
  conversation: StudioConversation
  assistantMessage: StudioMessage
  model: string
  reasoningEffort: string
}

export function useStudioChatStreamRuntime(hooks: StudioChatStreamRuntimeHooks) {
  const isStreaming = ref(false)
  let streamController: AbortController | null = null

  async function stream(input: StudioChatStreamInput) {
    const controller = new AbortController()
    streamController = controller
    isStreaming.value = true

    let pendingDelta = ''
    let deltaFrameId: number | null = null

    const flushPendingDelta = () => {
      if (deltaFrameId !== null) {
        window.cancelAnimationFrame(deltaFrameId)
        deltaFrameId = null
      }
      if (!pendingDelta) return
      input.assistantMessage.content += pendingDelta
      pendingDelta = ''
      hooks.touchConversation(input.conversation)
      hooks.scheduleScrollToBottom()
    }

    const scheduleDeltaFlush = (delta: string) => {
      pendingDelta += delta
      if (deltaFrameId !== null) return
      deltaFrameId = window.requestAnimationFrame(() => {
        deltaFrameId = null
        flushPendingDelta()
      })
    }

    try {
      await streamStudioChatReply({
        conversation: input.conversation,
        currentAssistantId: input.assistantMessage.id,
        model: input.model,
        reasoningEffort: input.reasoningEffort,
        signal: controller.signal,
        handlers: {
          onDelta: scheduleDeltaFlush,
        },
      })
      flushPendingDelta()
      input.assistantMessage.status = 'done'
      if (!input.assistantMessage.content.trim()) input.assistantMessage.content = 'The upstream service returned no content.'
      hooks.markConversationNotice(input.conversation.id, 'done')
    } catch (error) {
      flushPendingDelta()
      if (controller.signal.aborted) {
        input.assistantMessage.status = 'done'
        if (!input.assistantMessage.content.trim()) input.assistantMessage.content = 'Stopped.'
        hooks.markConversationNotice(input.conversation.id, 'done')
        return
      }
      const message = studioErrorMessage(error, 'Chat request failed')
      input.assistantMessage.status = 'error'
      input.assistantMessage.error = message
      input.assistantMessage.content = input.assistantMessage.content.trim()
        ? `${input.assistantMessage.content}\n\n${message}`
        : message
      hooks.markConversationNotice(input.conversation.id, 'error')
    } finally {
      flushPendingDelta()
      isStreaming.value = false
      streamController = null
      hooks.touchConversation(input.conversation)
    }
  }

  function stop() {
    streamController?.abort()
  }

  function dispose() {
    stop()
  }

  return {
    isStreaming,
    stream,
    stop,
    dispose,
  }
}
