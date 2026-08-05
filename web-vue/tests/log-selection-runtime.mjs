import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { ref } from 'vue'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
}

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { useLogSelectionRuntime } = await server.ssrLoadModule(
    '/src/views/logs/logSelectionRuntime.ts',
  )
  const item = { id: 'log-1', time: '2026-07-25 12:00:00' }
  const selectedLog = ref(item)
  let detailTargetId = item.id
  let closeCount = 0
  let notificationCount = 0
  const deleteRequests = []
  const runtime = useLogSelectionRuntime({
    visibleLogs: ref([item]),
    selectedLog,
    closeDetail: () => {
      closeCount += 1
      detailTargetId = ''
      selectedLog.value = null
    },
    deleteLogs: async (ids) => {
      const request = deferred()
      deleteRequests.push({ ids, request })
      return request.promise
    },
    refreshLogs: async () => {},
    notifySuccess: () => { notificationCount += 1 },
    notifyError: () => { notificationCount += 1 },
  })

  runtime.requestDeleteLog(item)
  const deleteSingle = runtime.confirmDeleteRequest()

  assert.equal(runtime.operationProgress.open, true)
  assert.equal(runtime.operationProgress.busy, true)
  assert.equal(runtime.operationProgress.title, '删除日志')
  assert.equal(deleteRequests.length, 0, '应先渲染抽屉再提交请求')
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(deleteRequests[0].ids, [item.id])

  deleteRequests[0].request.resolve({ removed: 1 })
  await deleteSingle

  assert.equal(closeCount, 1)
  assert.equal(detailTargetId, '')
  assert.equal(selectedLog.value, null)
  assert.equal(runtime.operationProgress.busy, false)
  assert.equal(runtime.operationProgress.current, 1)
  assert.deepEqual(
    runtime.operationProgress.events.map((event) => event.label),
    ['开始处理', '刷新列表', '已完成'],
  )
  assert.equal(notificationCount, 0, '执行结果已在抽屉显示时不应重复通知')

  selectedLog.value = item
  detailTargetId = item.id

  runtime.toggleLogSelection(item.id, true)
  assert.equal(runtime.isLogSelected(item.id), true)
  assert.equal(runtime.selectedLogCount.value, 1)

  runtime.toggleLogSelection(item.id, false)
  assert.equal(runtime.isLogSelected(item.id), false)
  assert.equal(runtime.selectedLogCount.value, 0)

  runtime.toggleLogSelection(item.id, true)
  runtime.requestDeleteSelectedLogs()
  const deleteBatch = runtime.confirmDeleteRequest()

  assert.equal(runtime.operationProgress.open, true)
  assert.equal(runtime.operationProgress.busy, true)
  assert.equal(runtime.operationProgress.title, '删除日志')
  assert.equal(deleteRequests.length, 1, '应先渲染抽屉再提交批量请求')
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(deleteRequests[1].ids, [item.id])

  deleteRequests[1].request.resolve({ removed: 1 })
  await deleteBatch

  assert.equal(closeCount, 2)
  assert.equal(detailTargetId, '')
  assert.equal(selectedLog.value, null)
  assert.equal(runtime.operationProgress.busy, false)
  assert.equal(runtime.operationProgress.current, 1)
  assert.deepEqual(
    runtime.operationProgress.events.map((event) => event.label),
    ['开始处理', '刷新列表', '已完成'],
  )
  assert.equal(notificationCount, 0, '批量执行结果已在抽屉显示时不应重复通知')
} finally {
  await server.close()
}
