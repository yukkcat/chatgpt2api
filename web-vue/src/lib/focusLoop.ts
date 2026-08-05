const focusableSelector = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[contenteditable="true"]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

type FocusLoopEvent = Pick<KeyboardEvent, 'key' | 'shiftKey' | 'preventDefault'>

function isFocusTarget(value: unknown): value is HTMLElement {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<HTMLElement>
  return typeof candidate.focus === 'function'
    && typeof candidate.getClientRects === 'function'
    && typeof candidate.getAttribute === 'function'
    && typeof candidate.hasAttribute === 'function'
}

function isAvailableFocusTarget(element: HTMLElement) {
  return element.isConnected !== false
    && element.getClientRects().length > 0
    && element.getAttribute('aria-hidden') !== 'true'
    && element.getAttribute('aria-disabled') !== 'true'
    && !element.hasAttribute('inert')
}

export function getFocusableElements(container: HTMLElement | null) {
  if (!container) return []
  return Array.from(container.querySelectorAll<HTMLElement>(focusableSelector))
    .filter(isAvailableFocusTarget)
}

export function focusElement(target: HTMLElement | null) {
  if (!target || !isAvailableFocusTarget(target)) return false
  target.focus({ preventScroll: true })
  return true
}

export function focusRefTarget(target: unknown) {
  const candidate = target && typeof target === 'object' && '$el' in target
    ? (target as { $el?: unknown }).$el
    : target
  return focusElement(isFocusTarget(candidate) ? candidate : null)
}

export function focusFirstWithin(container: HTMLElement | null, preferredSelector = '') {
  if (!container) return false
  const preferred = preferredSelector
    ? container.querySelector<HTMLElement>(preferredSelector)
    : null
  if (preferred && focusElement(preferred)) return true
  return focusElement(getFocusableElements(container)[0] ?? container)
}

export function trapFocusWithin(container: HTMLElement | null, event: FocusLoopEvent) {
  if (event.key !== 'Tab' || !container) return false
  const focusableElements = getFocusableElements(container)
  if (!focusableElements.length) {
    event.preventDefault()
    focusElement(container)
    return true
  }

  const activeElement = typeof document !== 'undefined' ? document.activeElement : null
  const currentIndex = focusableElements.findIndex(element => element === activeElement)
  const shouldWrapBackward = event.shiftKey && currentIndex <= 0
  const shouldWrapForward = !event.shiftKey && (
    currentIndex < 0 || currentIndex === focusableElements.length - 1
  )
  if (!shouldWrapBackward && !shouldWrapForward) return false

  event.preventDefault()
  const target = shouldWrapBackward
    ? focusableElements[focusableElements.length - 1]
    : focusableElements[0]
  focusElement(target)
  return true
}
