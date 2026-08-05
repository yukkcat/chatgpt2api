import assert from 'node:assert/strict'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

const originalDocument = Object.getOwnPropertyDescriptor(globalThis, 'document')
const originalFetch = Object.getOwnPropertyDescriptor(globalThis, 'fetch')
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')

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
  const anchor = {
    href: '',
    download: '',
    clickCount: 0,
    click() {
      this.clickCount += 1
    },
  }
  replaceGlobal('document', {
    body: {
      appendChild() {},
      removeChild() {},
    },
    createElement: tag => {
      assert.equal(tag, 'a')
      return anchor
    },
  })
  replaceGlobal('window', {
    location: {
      origin: 'http://console.local',
      hash: '#/studio',
    },
    setTimeout: callback => {
      callback()
      return 1
    },
  })

  let capturedUrl = ''
  let capturedOptions
  replaceGlobal('fetch', async (url, options) => {
    capturedUrl = url
    capturedOptions = options
    return {
      ok: true,
      status: 200,
      async blob() {
        return new Blob(['presentation'])
      },
    }
  })

  const { downloadPublicUrlAsFile } = await server.ssrLoadModule('/src/lib/downloads.ts')
  await downloadPublicUrlAsFile('/files/ppt/storage-id/result.pptx', 'result.pptx')

  assert.equal(capturedUrl, 'http://console.local/files/ppt/storage-id/result.pptx')
  assert.deepEqual(capturedOptions.headers, {})
  assert.equal(anchor.download, 'result.pptx')
  assert.equal(anchor.clickCount, 1)
} finally {
  restoreGlobal('document', originalDocument)
  restoreGlobal('fetch', originalFetch)
  restoreGlobal('window', originalWindow)
  await server.close()
}
