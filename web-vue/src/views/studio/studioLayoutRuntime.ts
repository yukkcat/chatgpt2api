import { computed, nextTick, ref, watch } from 'vue'
import {
  getBooleanPreference,
  getNumberPreference,
  preferenceKeys,
  setBooleanPreference,
  setNumberPreference,
} from '@/lib/preferences'
import type { useStudioScrollRuntime } from './studioScrollRuntime'

const DEFAULT_SIDEBAR_WIDTH = 244

export type StudioLayoutRuntimeInput = {
  scrollRuntime: Pick<ReturnType<typeof useStudioScrollRuntime>, 'scrollToBottom'>
}

export function useStudioLayoutRuntime(input: StudioLayoutRuntimeInput) {
  const isFullscreen = ref(getBooleanPreference(preferenceKeys.studioFullscreen, false))
  const isMobileHistoryOpen = ref(false)
  const sidebarWidth = ref(getNumberPreference(preferenceKeys.studioSidebarWidth, DEFAULT_SIDEBAR_WIDTH, {
    min: 220,
    max: 380,
  }))
  const workspaceStyle = computed(() => ({
    '--studio-history-width': `${sidebarWidth.value}px`,
  }))

  let sidebarResizeStartX = 0
  let sidebarResizeStartWidth = DEFAULT_SIDEBAR_WIDTH

  watch(isFullscreen, (value) => setBooleanPreference(preferenceKeys.studioFullscreen, value))
  watch(sidebarWidth, (value) => setNumberPreference(preferenceKeys.studioSidebarWidth, value))

  function openMobileHistory() {
    isMobileHistoryOpen.value = true
  }

  function closeMobileHistory() {
    isMobileHistoryOpen.value = false
  }

  function toggleFullscreen() {
    isFullscreen.value = !isFullscreen.value
    void nextTick(input.scrollRuntime.scrollToBottom)
  }

  function startSidebarResize(event: PointerEvent) {
    event.preventDefault()
    ;(event.currentTarget as HTMLElement | null)?.setPointerCapture?.(event.pointerId)
    sidebarResizeStartX = event.clientX
    sidebarResizeStartWidth = sidebarWidth.value
    document.body.classList.add('studio-resizing')
    window.addEventListener('pointermove', handleSidebarResize)
    window.addEventListener('pointerup', stopSidebarResize, { once: true })
    window.addEventListener('pointercancel', stopSidebarResize, { once: true })
  }

  function handleSidebarResize(event: PointerEvent) {
    const nextWidth = sidebarResizeStartWidth + event.clientX - sidebarResizeStartX
    sidebarWidth.value = Math.min(380, Math.max(220, Math.round(nextWidth)))
  }

  function stopSidebarResize() {
    document.body.classList.remove('studio-resizing')
    window.removeEventListener('pointermove', handleSidebarResize)
    window.removeEventListener('pointerup', stopSidebarResize)
    window.removeEventListener('pointercancel', stopSidebarResize)
  }

  function dispose() {
    stopSidebarResize()
  }

  return {
    closeMobileHistory,
    dispose,
    isFullscreen,
    isMobileHistoryOpen,
    openMobileHistory,
    startSidebarResize,
    stopSidebarResize,
    toggleFullscreen,
    workspaceStyle,
  }
}
