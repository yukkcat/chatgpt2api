export async function writeClipboardText(value: string) {
  const text = String(value ?? '')
  if (!text) throw new Error('Nothing to copy')

  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Clipboard API can be unavailable on non-secure self-hosted origins.
    }
  }

  if (typeof document === 'undefined' || !document.body) {
    throw new Error('Clipboard is unavailable')
  }

  const previousActiveElement = document.activeElement
  const scrollX = typeof window !== 'undefined' ? window.scrollX : 0
  const scrollY = typeof window !== 'undefined' ? window.scrollY : 0
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', 'readonly')
  textarea.setAttribute('aria-hidden', 'true')
  textarea.style.position = 'fixed'
  textarea.style.top = '0'
  textarea.style.left = '0'
  textarea.style.width = '1px'
  textarea.style.height = '1px'
  textarea.style.opacity = '0'
  textarea.style.pointerEvents = 'none'
  document.body.appendChild(textarea)

  let copied = false
  try {
    textarea.focus({ preventScroll: true })
    textarea.select()
    textarea.setSelectionRange(0, textarea.value.length)
    copied = document.execCommand('copy')
  } finally {
    document.body.removeChild(textarea)
    if (
      previousActiveElement
      && previousActiveElement !== document.body
      && previousActiveElement.isConnected
      && 'focus' in previousActiveElement
      && typeof previousActiveElement.focus === 'function'
    ) {
      try {
        previousActiveElement.focus({ preventScroll: true })
      } catch {
        // Focus restoration is best-effort and must not turn a successful copy into a failure.
      }
    }
    if (typeof window !== 'undefined') window.scrollTo(scrollX, scrollY)
  }

  if (!copied) throw new Error('Clipboard copy failed')
}
