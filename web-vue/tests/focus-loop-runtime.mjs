import assert from 'node:assert/strict'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

function createFocusable(name) {
  return {
    name,
    isConnected: true,
    getAttribute: () => null,
    hasAttribute: () => false,
    getClientRects: () => [{ width: 1, height: 1 }],
    focus() {
      globalThis.document.activeElement = this
    },
  }
}

function createTabEvent(shiftKey = false) {
  return {
    key: 'Tab',
    shiftKey,
    defaultPrevented: false,
    preventDefault() {
      this.defaultPrevented = true
    },
  }
}

try {
  const { focusFirstWithin, focusRefTarget, trapFocusWithin } = await server.ssrLoadModule('/src/lib/focusLoop.ts')
  const first = createFocusable('first')
  const last = createFocusable('last')
  const container = {
    querySelector: () => first,
    querySelectorAll: () => [first, last],
    focus() {
      globalThis.document.activeElement = this
    },
  }
  globalThis.document = { activeElement: last }

  const forward = createTabEvent()
  assert.equal(trapFocusWithin(container, forward), true)
  assert.equal(forward.defaultPrevented, true)
  assert.equal(globalThis.document.activeElement, first)

  globalThis.document.activeElement = first
  const backward = createTabEvent(true)
  assert.equal(trapFocusWithin(container, backward), true)
  assert.equal(backward.defaultPrevented, true)
  assert.equal(globalThis.document.activeElement, last)

  const toggle = createFocusable('toggle')
  globalThis.document.activeElement = null
  assert.equal(focusRefTarget({ $el: toggle }), true)
  assert.equal(globalThis.document.activeElement, toggle)

  globalThis.document.activeElement = null
  assert.equal(focusFirstWithin(container, '#app-sidebar-navigation a[href]'), true)
  assert.equal(globalThis.document.activeElement, first)

  const emptyContainer = {
    ...createFocusable('empty container'),
    querySelectorAll: () => [],
  }
  const emptyTab = createTabEvent()
  assert.equal(trapFocusWithin(emptyContainer, emptyTab), true)
  assert.equal(emptyTab.defaultPrevented, true)
  assert.equal(globalThis.document.activeElement, emptyContainer)
} finally {
  await server.close()
}
