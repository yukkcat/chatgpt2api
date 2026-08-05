import { reactive } from 'vue'
import type { ToastItem } from 'nanocat-ui'

export type Toast = ToastItem

export const toastState = reactive<{ toasts: Toast[] }>({
  toasts: [],
})

let toastId = 0

export const showToast = (options: Omit<Toast, 'id'>) => {
  const id = `toast-${++toastId}`
  const duration = options.duration ?? 3000

  const toast: Toast = {
    id,
    type: options.type,
    title: options.title,
    message: options.message,
    duration,
  }

  toastState.toasts.push(toast)

  if (duration > 0) {
    setTimeout(() => {
      removeToast(id)
    }, duration)
  }

  return id
}

export const removeToast = (id: string) => {
  const index = toastState.toasts.findIndex((t) => t.id === id)
  if (index > -1) {
    toastState.toasts.splice(index, 1)
  }
}

export const useToast = () => {
  return {
    success: (message: string, title?: string, duration?: number) =>
      showToast({ type: 'success', message, title, duration }),
    error: (message: string, title?: string, duration?: number) =>
      showToast({ type: 'error', message, title, duration }),
    warning: (message: string, title?: string, duration?: number) =>
      showToast({ type: 'warning', message, title, duration }),
    info: (message: string, title?: string, duration?: number) =>
      showToast({ type: 'info', message, title, duration }),
  }
}
