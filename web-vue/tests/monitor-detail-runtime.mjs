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
  const { useMonitorDetailRuntime } = await server.ssrLoadModule(
    '/src/views/monitor/monitorDetailRuntime.ts',
  )
  const requests = []
  const runtime = useMonitorDetailRuntime({
    loadDetail: (callId) => {
      const pending = deferred()
      requests.push({ callId, pending })
      return pending.promise
    },
  })

  runtime.openDetail({ call_id: 'active-call' })
  assert.equal(runtime.detailOpen.value, true)
  assert.equal(runtime.detailLoading.value, true)
  assert.equal(requests.length, 1)

  requests[0].pending.resolve({ call_id: 'active-call', status: 'running', events: ['first'] })
  await flush()

  assert.equal(runtime.detailLoading.value, false)
  assert.deepEqual(runtime.detailRecord.value.events, ['first'])

  const refresh = runtime.refreshIfRunning()
  assert.equal(requests.length, 2)
  assert.equal(runtime.detailLoading.value, false, 'background refresh must keep the drawer stable')
  assert.deepEqual(runtime.detailRecord.value.events, ['first'])

  requests[1].pending.resolve({ call_id: 'active-call', status: 'success', events: ['first', 'done'] })
  await refresh

  assert.deepEqual(runtime.detailRecord.value.events, ['first', 'done'])
  await runtime.refreshIfRunning()
  assert.equal(requests.length, 2, 'terminal details must stop refreshing')

  runtime.openDetail({ call_id: 'closing-call' })
  assert.equal(requests.length, 3)
  runtime.closeDetail()
  requests[2].pending.resolve({ call_id: 'closing-call', status: 'running', events: [] })
  await flush()

  assert.equal(runtime.detailOpen.value, false)
  assert.equal(runtime.detailRecord.value, null)
} finally {
  await server.close()
}
