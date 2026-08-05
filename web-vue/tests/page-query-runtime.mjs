import assert from 'node:assert/strict'
import { computed, nextTick, ref } from 'vue'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

function deferred() {
  let resolve
  const promise = new Promise(resolvePromise => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function createVisibilityRuntime(initialVisible) {
  const isActive = ref(true)
  const isVisible = ref(initialVisible)
  const canRun = computed(() => isActive.value && isVisible.value)
  const requestSeq = new Map()
  const showCallbacks = new Set()
  const hideCallbacks = new Set()

  return {
    isActive,
    isVisible,
    canRun,
    nextRequest(key) {
      const next = (requestSeq.get(key) || 0) + 1
      requestSeq.set(key, next)
      return next
    },
    isLatestRequest(key, seq, options = {}) {
      if (!isActive.value) return false
      if (options.requireVisible !== false && !isVisible.value) return false
      return requestSeq.get(key) === seq
    },
    invalidateRequest(key) {
      requestSeq.set(key, (requestSeq.get(key) || 0) + 1)
    },
    onShow(callback) {
      showCallbacks.add(callback)
    },
    onHide(callback) {
      hideCallbacks.add(callback)
    },
    show() {
      if (isVisible.value) return
      isVisible.value = true
      showCallbacks.forEach(callback => callback({ initial: false, visible: true }))
    },
    hide() {
      if (!isVisible.value) return
      isVisible.value = false
      hideCallbacks.forEach(callback => callback({ initial: false, visible: false }))
    },
  }
}

try {
  const {
    usePageQuery,
    usePageVisibilityReload,
    useSerialVisibilityPolling,
  } = await server.ssrLoadModule(
    '/src/composables/usePageQuery.ts',
  )
  const timers = new Map()
  const runtime = {
    canRun: ref(true),
    clearTimer: key => timers.delete(key),
    setTimer: (key, _delay, callback) => timers.set(key, callback),
  }
  const firstRequest = deferred()
  let calls = 0
  const polling = useSerialVisibilityPolling({
    runtime,
    key: 'monitor:poll',
    intervalMs: 5000,
    immediate: true,
    action: () => {
      calls += 1
      return calls === 1 ? firstRequest.promise : Promise.resolve()
    },
  })

  polling.start()
  assert.equal(calls, 1)

  polling.stop()
  polling.start()
  assert.equal(calls, 2, 'reactivation must not be blocked by an obsolete request')

  firstRequest.resolve()
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(timers.size, 1)

  {
    const hiddenRuntime = createVisibilityRuntime(false)
    const appliedValues = []
    let requestCalls = 0
    const query = usePageQuery({
      runtime: hiddenRuntime,
      key: 'accounts:list',
    })
    const load = () => query.run(
      async () => {
        requestCalls += 1
        return requestCalls
      },
      { apply: value => appliedValues.push(value) },
    )
    usePageVisibilityReload({
      runtime: hiddenRuntime,
      invalidate: query.invalidate,
      reload: load,
    })

    await load()
    assert.equal(requestCalls, 1)
    assert.deepEqual(appliedValues, [], 'a hidden initial response must not update the page')

    hiddenRuntime.show()
    await Promise.resolve()
    await Promise.resolve()

    assert.equal(requestCalls, 2, 'the first visible transition must reload a hidden mount')
    assert.deepEqual(appliedValues, [2])
  }

  {
    const visibleRuntime = createVisibilityRuntime(true)
    const appliedValues = []
    let requestCalls = 0
    const query = usePageQuery({
      runtime: visibleRuntime,
      key: 'logs:list',
    })
    const load = () => query.run(
      async () => {
        requestCalls += 1
        return requestCalls
      },
      { apply: value => appliedValues.push(value) },
    )
    const visibilityReload = usePageVisibilityReload({
      runtime: visibleRuntime,
      invalidate: query.invalidate,
      reload: load,
    })

    await load()
    assert.equal(visibilityReload.reloadIfPending(), false)
    await Promise.resolve()

    assert.equal(requestCalls, 1, 'a visible mount must keep its single initial request')
    assert.deepEqual(appliedValues, [1])
  }

  {
    const visibleRuntime = createVisibilityRuntime(true)
    const blocked = ref(false)
    let requestCalls = 0
    const visibilityReload = usePageVisibilityReload({
      runtime: visibleRuntime,
      invalidate: () => {},
      reload: () => {
        requestCalls += 1
      },
      shouldReload: () => !blocked.value,
    })

    visibleRuntime.hide()
    blocked.value = true
    visibleRuntime.show()
    assert.equal(requestCalls, 0, 'a blocked visible transition must retain the pending reload')
    assert.equal(visibilityReload.reloadIfPending(), false)

    blocked.value = false
    await nextTick()
    assert.equal(requestCalls, 1, 'unblocking must consume the pending reload without another visibility event')
    assert.equal(visibilityReload.reloadIfPending(), false, 'the pending reload must be consumed only once')
  }

} finally {
  await server.close()
}
