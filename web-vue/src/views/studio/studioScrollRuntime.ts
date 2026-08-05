import { nextTick, type Ref } from 'vue'
import type { PageRuntime } from '@/composables/usePageRuntime'

const SCROLL_REQUEST_KEY = 'studio:scroll'

export type StudioMessageListScroller = {
  scrollToBottom: () => Promise<void> | void
}

export type StudioScrollRuntimeInput = {
  pageRuntime: PageRuntime
  messageListRef: Ref<StudioMessageListScroller | null>
}

export function useStudioScrollRuntime(input: StudioScrollRuntimeInput) {
  let frameId: number | null = null
  let scheduled = false

  function scrollToBottom() {
    void input.messageListRef.value?.scrollToBottom()
  }

  function scheduleScrollToBottom() {
    if (!input.pageRuntime.canRun.value) return
    if (scheduled) return
    const requestSeq = input.pageRuntime.nextRequest(SCROLL_REQUEST_KEY)
    scheduled = true
    void nextTick(() => {
      if (frameId !== null) return
      frameId = window.requestAnimationFrame(() => {
        frameId = null
        scheduled = false
        if (!input.pageRuntime.isLatestRequest(SCROLL_REQUEST_KEY, requestSeq)) return
        scrollToBottom()
      })
    })
  }

  function cancel() {
    input.pageRuntime.invalidateRequest(SCROLL_REQUEST_KEY)
    if (frameId !== null) {
      window.cancelAnimationFrame(frameId)
      frameId = null
    }
    scheduled = false
  }

  function dispose() {
    cancel()
  }

  return {
    scrollToBottom,
    scheduleScrollToBottom,
    cancel,
    dispose,
  }
}
