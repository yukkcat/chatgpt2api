import assert from 'node:assert/strict'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

const originalGlobals = new Map(
  ['document', 'navigator', 'window'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
)

function replaceGlobal(key, value) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value,
  })
}

function restoreGlobals() {
  for (const [key, descriptor] of originalGlobals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor)
    else delete globalThis[key]
  }
}

try {
  const { writeClipboardText } = await server.ssrLoadModule('/src/lib/clipboard.ts')
  let restoredFocusCount = 0
  let restoredFocusOptions = null
  let restoredScroll = null
  let restoredScrollCount = 0
  const previousFocus = {
    isConnected: true,
    focus(options) {
      restoredFocusCount += 1
      restoredFocusOptions = options
    },
  }
  const textarea = {
    style: {},
    setAttribute() {},
    focus() {},
    select() {},
    setSelectionRange() {},
  }
  const body = {
    appendChild() {},
    removeChild() {},
  }

  replaceGlobal('navigator', {
    clipboard: {
      writeText: async () => {
        throw new Error('Clipboard permission denied')
      },
    },
  })
  replaceGlobal('document', {
    activeElement: previousFocus,
    body,
    createElement: () => textarea,
    execCommand: command => command === 'copy',
  })
  replaceGlobal('window', {
    scrollX: 17,
    scrollY: 29,
    scrollTo: (x, y) => {
      restoredScroll = [x, y]
      restoredScrollCount += 1
    },
  })

  await writeClipboardText('copy me')

  assert.equal(restoredFocusCount, 1)
  assert.deepEqual(restoredFocusOptions, { preventScroll: true })
  assert.deepEqual(restoredScroll, [17, 29])
  assert.equal(restoredScrollCount, 1)

  previousFocus.focus = () => {
    throw new Error('focus target disappeared')
  }
  await writeClipboardText('copy again')
  assert.deepEqual(restoredScroll, [17, 29])
  assert.equal(restoredScrollCount, 2)
} finally {
  restoreGlobals()
  await server.close()
}
