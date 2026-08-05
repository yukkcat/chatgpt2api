import assert from 'node:assert/strict'
import { createServer } from 'vite'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
}

async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { useLogDetailRuntime } = await server.ssrLoadModule(
    '/src/views/logs/logDetailRuntime.ts',
  )
  const requests = new Map()
  const runtime = useLogDetailRuntime({
    loadDetail: (id) => {
      const pending = deferred()
      requests.set(id, pending)
      return pending.promise
    },
  })

  runtime.openDetail({ id: 'first' })

  assert.equal(runtime.detailOpen.value, true)
  assert.equal(runtime.detailLoading.value, true)
  assert.equal(runtime.selectedLog.value, null)

  requests.get('first').resolve({ id: 'first', detailPresentation: { timeline: [] } })
  await flush()

  assert.equal(runtime.detailLoading.value, false)
  assert.equal(runtime.selectedLog.value.id, 'first')

  runtime.openDetail({ id: 'slow' })
  runtime.openDetail({ id: 'latest' })
  requests.get('slow').resolve({ id: 'slow', detailPresentation: { timeline: [] } })
  await flush()

  assert.equal(runtime.selectedLog.value, null)
  assert.equal(runtime.detailLoading.value, true)

  requests.get('latest').resolve({ id: 'latest', detailPresentation: { timeline: [] } })
  await flush()

  assert.equal(runtime.selectedLog.value.id, 'latest')
  assert.equal(runtime.detailLoading.value, false)

  runtime.openDetail({ id: 'closed' })
  runtime.closeDetail()
  requests.get('closed').resolve({ id: 'closed', detailPresentation: { timeline: [] } })
  await flush()

  assert.equal(runtime.detailOpen.value, false)
  assert.equal(runtime.selectedLog.value, null)
  assert.equal(runtime.detailLoading.value, false)
} finally {
  await server.close()
}
