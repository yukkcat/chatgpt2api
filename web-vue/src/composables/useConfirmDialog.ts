import { ref } from 'vue'

type ConfirmOptions = {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
}

// Global singleton state: all callers share the same dialog instance.
const open = ref(false)
const title = ref('Confirm action')
const message = ref('')
const confirmText = ref('Confirm')
const cancelText = ref('Cancel')
let resolver: ((value: boolean) => void) | null = null

export function useConfirmDialog() {
  const ask = (options: ConfirmOptions) =>
    new Promise<boolean>((resolve) => {
      title.value = options.title || 'Confirm action'
      message.value = options.message
      confirmText.value = options.confirmText || 'Confirm'
      cancelText.value = options.cancelText || 'Cancel'
      open.value = true
      resolver = resolve
    })

  const confirm = () => {
    open.value = false
    resolver?.(true)
    resolver = null
  }

  const cancel = () => {
    open.value = false
    resolver?.(false)
    resolver = null
  }

  return {
    open,
    title,
    message,
    confirmText,
    cancelText,
    ask,
    confirm,
    cancel,
  }
}
