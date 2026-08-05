import assert from 'node:assert/strict'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
const originalFetch = Object.getOwnPropertyDescriptor(globalThis, 'fetch')

function replaceGlobal(key, value) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value,
  })
}

function restoreGlobal(key, descriptor) {
  if (descriptor) Object.defineProperty(globalThis, key, descriptor)
  else delete globalThis[key]
}

try {
  const storage = new Map()
  replaceGlobal('window', {
    location: { hash: '#/studio' },
    localStorage: {
      getItem: key => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: key => storage.delete(key),
    },
    setTimeout: callback => {
      callback()
      return 1
    },
  })
  replaceGlobal('fetch', async () => new Response(
    JSON.stringify({ error: { message: 'Session expired' } }),
    {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    },
  ))

  const client = await server.ssrLoadModule('/src/api/client.ts')
  const { streamChatCompletion } = await server.ssrLoadModule('/src/api/chatStream.ts')

  let unauthorizedCalls = 0
  client.setAuthToken('expired-key')
  client.setUnauthorizedHandler(() => {
    unauthorizedCalls += 1
  })

  await assert.rejects(
    () => streamChatCompletion({ model: 'gpt-4o', messages: [] }),
    /Session expired/,
  )
  assert.equal(unauthorizedCalls, 1)
  assert.equal(client.getAuthToken(), '')
  client.setUnauthorizedHandler(null)
} finally {
  restoreGlobal('fetch', originalFetch)
  restoreGlobal('window', originalWindow)
  await server.close()
}
