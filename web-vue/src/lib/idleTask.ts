type IdleCallbackHandle = number
type IdleDeadlineLike = { didTimeout: boolean; timeRemaining: () => number }
type IdleCallback = (deadline: IdleDeadlineLike) => void

type WindowWithIdleCallback = Window & {
  requestIdleCallback?: (callback: IdleCallback, options?: { timeout?: number }) => IdleCallbackHandle
  cancelIdleCallback?: (handle: IdleCallbackHandle) => void
}

export interface IdleTaskHandle {
  cancel: () => void
  flush: () => void
}

export function scheduleIdleTask(callback: () => void, timeout = 1500): IdleTaskHandle {
  const win = window as WindowWithIdleCallback
  let handle: IdleCallbackHandle | null = null
  let cancelled = false

  function run() {
    if (cancelled) return
    cancelled = true
    handle = null
    callback()
  }

  if (typeof win.requestIdleCallback === 'function') {
    handle = win.requestIdleCallback(run, { timeout })
  } else {
    handle = window.setTimeout(run, Math.max(0, timeout))
  }

  return {
    cancel: () => {
      if (cancelled) return
      cancelled = true
      if (handle === null) return
      if (typeof win.cancelIdleCallback === 'function' && typeof win.requestIdleCallback === 'function') {
        win.cancelIdleCallback(handle)
      } else {
        window.clearTimeout(handle)
      }
      handle = null
    },
    flush: run,
  }
}
