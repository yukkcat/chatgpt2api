import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'

export interface PageRuntimeContext {
  initial: boolean
  visible: boolean
}

type PageRuntimeCallback = (context: PageRuntimeContext) => void

function removeCallback(callbacks: Set<PageRuntimeCallback>, callback: PageRuntimeCallback) {
  callbacks.delete(callback)
}

export function usePageRuntime(_name: string) {
  const isActive = ref(false)
  const isVisible = ref(typeof document === 'undefined' ? true : !document.hidden)
  const canRun = computed(() => isActive.value && isVisible.value)

  const activateCallbacks = new Set<PageRuntimeCallback>()
  const deactivateCallbacks = new Set<PageRuntimeCallback>()
  const showCallbacks = new Set<PageRuntimeCallback>()
  const hideCallbacks = new Set<PageRuntimeCallback>()
  const requestSeq = new Map<string, number>()
  const timers = new Map<string, number>()
  const intervals = new Map<string, number>()

  let skipFirstActivatedHook = true

  function context(initial = false): PageRuntimeContext {
    return {
      initial,
      visible: isVisible.value,
    }
  }

  function emit(callbacks: Set<PageRuntimeCallback>, initial = false) {
    const payload = context(initial)
    callbacks.forEach((callback) => callback(payload))
  }

  function invalidateRequest(key: string) {
    requestSeq.set(key, (requestSeq.get(key) || 0) + 1)
  }

  function invalidateAllRequests() {
    requestSeq.forEach((value, key) => {
      requestSeq.set(key, value + 1)
    })
  }

  function nextRequest(key: string) {
    const next = (requestSeq.get(key) || 0) + 1
    requestSeq.set(key, next)
    return next
  }

  function isLatestRequest(key: string, seq: number, options: { requireVisible?: boolean } = {}) {
    if (!isActive.value) return false
    if (options.requireVisible !== false && !isVisible.value) return false
    return requestSeq.get(key) === seq
  }

  function clearTimer(key: string) {
    const timer = timers.get(key)
    if (timer === undefined) return
    window.clearTimeout(timer)
    timers.delete(key)
  }

  function clearIntervalTimer(key: string) {
    const interval = intervals.get(key)
    if (interval === undefined) return
    window.clearInterval(interval)
    intervals.delete(key)
  }

  function setTimer(key: string, delayMs: number, callback: () => void, options: { requireVisible?: boolean } = {}) {
    clearTimer(key)
    if (!isActive.value) return
    if (options.requireVisible !== false && !isVisible.value) return
    const timer = window.setTimeout(() => {
      timers.delete(key)
      if (!isActive.value) return
      if (options.requireVisible !== false && !isVisible.value) return
      callback()
    }, Math.max(0, delayMs))
    timers.set(key, timer)
  }

  function setIntervalTimer(key: string, delayMs: number, callback: () => void, options: { requireVisible?: boolean } = {}) {
    clearIntervalTimer(key)
    if (!isActive.value) return
    if (options.requireVisible !== false && !isVisible.value) return
    const interval = window.setInterval(() => {
      if (!isActive.value) {
        clearIntervalTimer(key)
        return
      }
      if (options.requireVisible !== false && !isVisible.value) return
      callback()
    }, Math.max(1, delayMs))
    intervals.set(key, interval)
  }

  function clearTimers() {
    Array.from(timers.keys()).forEach(clearTimer)
  }

  function clearIntervals() {
    Array.from(intervals.keys()).forEach(clearIntervalTimer)
  }

  function clearScope() {
    clearTimers()
    clearIntervals()
    invalidateAllRequests()
  }

  function activate(initial = false) {
    isActive.value = true
    isVisible.value = typeof document === 'undefined' ? true : !document.hidden
    emit(activateCallbacks, initial)
  }

  function deactivate() {
    if (!isActive.value) return
    isActive.value = false
    clearScope()
    emit(deactivateCallbacks)
  }

  function handleVisibilityChange() {
    const nextVisible = typeof document === 'undefined' ? true : !document.hidden
    if (isVisible.value === nextVisible) return
    isVisible.value = nextVisible
    if (!nextVisible) {
      clearScope()
      emit(hideCallbacks)
      return
    }
    if (!isActive.value) return
    emit(showCallbacks)
  }

  function onActivate(callback: PageRuntimeCallback) {
    activateCallbacks.add(callback)
    return () => removeCallback(activateCallbacks, callback)
  }

  function onDeactivate(callback: PageRuntimeCallback) {
    deactivateCallbacks.add(callback)
    return () => removeCallback(deactivateCallbacks, callback)
  }

  function onShow(callback: PageRuntimeCallback) {
    showCallbacks.add(callback)
    return () => removeCallback(showCallbacks, callback)
  }

  function onHide(callback: PageRuntimeCallback) {
    hideCallbacks.add(callback)
    return () => removeCallback(hideCallbacks, callback)
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', handleVisibilityChange)
    activate(true)
  })

  onActivated(() => {
    if (skipFirstActivatedHook) {
      skipFirstActivatedHook = false
      return
    }
    activate(false)
  })

  onDeactivated(() => {
    deactivate()
  })

  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    deactivate()
    clearScope()
  })

  return {
    isActive,
    isVisible,
    canRun,
    nextRequest,
    isLatestRequest,
    invalidateRequest,
    invalidateAllRequests,
    setTimer,
    clearTimer,
    setInterval: setIntervalTimer,
    clearInterval: clearIntervalTimer,
    clearScope,
    onActivate,
    onDeactivate,
    onShow,
    onHide,
  }
}

export type PageRuntime = ReturnType<typeof usePageRuntime>
