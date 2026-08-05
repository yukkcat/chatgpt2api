import type { Ref } from 'vue'

type StudioConversationIdSetRef = {
  value: Set<string>
}

export type StudioConversationSelectionRuntimeHooks = {
  cancelMessageEdit: () => void
  clearConversationNotice: (conversationId: string) => void
}

export type StudioConversationSelectionRuntimeInput = {
  activeConversationId: Ref<string>
  validConversationIds: StudioConversationIdSetRef
  hooks: StudioConversationSelectionRuntimeHooks
}

export type StudioConversationSelectionRuntime = ReturnType<typeof useStudioConversationSelectionRuntime>

export function useStudioConversationSelectionRuntime(input: StudioConversationSelectionRuntimeInput) {
  let pendingConversationSelectId = ''
  let frameId: number | null = null

  function select(conversationId: string) {
    if (!conversationId || (input.activeConversationId.value === conversationId && !pendingConversationSelectId)) return
    pendingConversationSelectId = conversationId
    if (frameId !== null) return
    frameId = window.requestAnimationFrame(() => {
      frameId = null
      const nextId = pendingConversationSelectId
      pendingConversationSelectId = ''
      apply(nextId)
    })
  }

  function apply(conversationId: string) {
    if (!conversationId || input.activeConversationId.value === conversationId) return
    if (!input.validConversationIds.value.has(conversationId)) return
    input.hooks.cancelMessageEdit()
    input.activeConversationId.value = conversationId
    input.hooks.clearConversationNotice(conversationId)
  }

  function cancel() {
    pendingConversationSelectId = ''
    if (frameId !== null) {
      window.cancelAnimationFrame(frameId)
      frameId = null
    }
  }

  function dispose() {
    cancel()
  }

  return {
    apply,
    cancel,
    dispose,
    select,
  }
}
