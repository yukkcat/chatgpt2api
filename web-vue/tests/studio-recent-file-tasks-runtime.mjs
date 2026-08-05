import assert from 'node:assert/strict'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { useStudioRecentFileTasksRuntime } = await server.ssrLoadModule(
    '/src/views/studio/studioRecentFileTasksRuntime.ts',
  )
  const successTask = {
    id: 'task-newest',
    kind: 'ppt',
    status: 'success',
    created_at: '2026-07-29 11:00:00',
    updated_at: '2026-07-29 11:02:00',
    elapsed_seconds: 120,
    can_download: true,
    can_delete: true,
    result: {
      conversation_id: 'conversation-newest',
      primary_url: '/files/ppt/task-newest/result.pptx',
      zip_url: '/files/ppt/task-newest/result.zip',
    },
  }
  const deletedTaskIds = []
  const runtime = useStudioRecentFileTasksRuntime({
    loadRecentTasks: async () => ({
      items: [successTask],
      missing_ids: [],
    }),
    deleteRecentTask: async taskId => {
      deletedTaskIds.push(taskId)
      return { task_id: taskId, deleted: true }
    },
  })

  await runtime.refresh()

  assert.equal(runtime.isLoading.value, false)
  assert.equal(runtime.error.value, '')
  assert.deepEqual(runtime.tasks.value.map((task) => task.id), ['task-newest'])
  assert.equal(runtime.tasks.value[0].result.primary_url, '/files/ppt/task-newest/result.pptx')

  assert.equal(await runtime.removeTask(successTask), true)
  assert.deepEqual(deletedTaskIds, ['task-newest'])
  assert.deepEqual(runtime.tasks.value, [])
  assert.equal(runtime.isTaskBusy('task-newest'), false)

  const copiedErrors = []
  const failedTask = {
    id: 'task-failed',
    kind: 'psd',
    status: 'error',
    created_at: '2026-07-29 12:00:00',
    updated_at: '2026-07-29 12:00:10',
    elapsed_seconds: 10,
    can_download: false,
    can_delete: true,
    error: 'upstream export failed',
  }
  const copyRuntime = useStudioRecentFileTasksRuntime({
    copyText: async value => copiedErrors.push(value),
  })
  assert.equal(await copyRuntime.copyTaskError(failedTask), true)
  assert.deepEqual(copiedErrors, ['upstream export failed'])
  assert.equal(copyRuntime.actionError.value, '')

  const runningTask = {
    id: 'task-running',
    kind: 'ppt',
    status: 'running',
    created_at: '2026-07-29 12:00:00',
    updated_at: '2026-07-29 12:00:01',
    elapsed_seconds: 1,
    can_download: false,
    can_delete: false,
  }
  assert.equal(await runtime.removeTask(runningTask), false)
  assert.deepEqual(deletedTaskIds, ['task-newest'])

  const failingRuntime = useStudioRecentFileTasksRuntime({
    deleteRecentTask: async () => {
      throw new Error('task is still running')
    },
  })
  assert.equal(await failingRuntime.removeTask(failedTask), false)
  assert.equal(failingRuntime.actionError.value, 'task is still running')
  assert.equal(failingRuntime.isTaskBusy(failedTask.id), false)

  let resolveStaleRefresh
  const staleRefresh = new Promise(resolve => {
    resolveStaleRefresh = resolve
  })
  const raceRuntime = useStudioRecentFileTasksRuntime({
    loadRecentTasks: () => staleRefresh,
    deleteRecentTask: async taskId => ({ task_id: taskId, deleted: true }),
  })
  const refreshPromise = raceRuntime.refresh()
  assert.equal(await raceRuntime.removeTask(successTask), true)
  resolveStaleRefresh({ items: [successTask], missing_ids: [] })
  await refreshPromise
  assert.deepEqual(raceRuntime.tasks.value, [])

  await raceRuntime.refresh()
  assert.deepEqual(raceRuntime.tasks.value.map(task => task.id), ['task-newest'])
} finally {
  await server.close()
}
