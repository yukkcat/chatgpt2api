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
  const { settingsApi } = await server.ssrLoadModule('/src/api/settings.ts')
  const { useConfirmDialog } = await server.ssrLoadModule('/src/composables/useConfirmDialog.ts')
  const { toastState } = await server.ssrLoadModule('/src/composables/useToast.ts')
  const { useSettingsImageStorageRuntime } = await server.ssrLoadModule(
    '/src/views/settings/settingsImageStorageRuntime.ts',
  )
  const { useSettingsBackupRuntime } = await server.ssrLoadModule(
    '/src/views/settings/settingsBackupRuntime.ts',
  )
  const { useSettingsPromptSourcesOperationRuntime } = await server.ssrLoadModule(
    '/src/views/settings/settingsPromptSourcesOperationRuntime.ts',
  )
  const originalSync = settingsApi.syncImageStorage
  const response = deferred()
  let requestCount = 0
  settingsApi.syncImageStorage = () => {
    requestCount += 1
    return response.promise
  }

  try {
    toastState.toasts.splice(0)
    const runtime = useSettingsImageStorageRuntime({ requireSavedSettings: () => true })
    const syncing = runtime.syncImageStorageFiles()
    await Promise.resolve()
    useConfirmDialog().confirm()
    await Promise.resolve()

    assert.equal(runtime.operationProgress.open, true)
    assert.equal(runtime.operationProgress.busy, true)
    assert.equal(runtime.operationProgress.title, '全量同步图片')
    assert.equal(requestCount, 0, '应先渲染执行抽屉再提交全量同步请求')

    await new Promise((resolve) => setTimeout(resolve, 0))
    assert.equal(requestCount, 1)
    response.resolve({ result: { uploaded: 3, skipped: 2, failed: 1 } })
    await syncing

    assert.equal(runtime.operationProgress.busy, false)
    assert.equal(runtime.operationProgress.tone, 'warning')
    assert.match(runtime.operationProgress.message, /上传 3.*跳过 2.*失败 1/)
    assert.equal(toastState.toasts.length, 0, '已有执行抽屉时不应重复弹出 Toast')
  } finally {
    settingsApi.syncImageStorage = originalSync
  }

  {
    const originalRunBackup = settingsApi.runBackup
    const originalListBackups = settingsApi.listBackups
    const response = deferred()
    let requestCount = 0
    settingsApi.runBackup = () => {
      requestCount += 1
      return response.promise
    }
    settingsApi.listBackups = async () => ({ items: [], state: null })
    try {
      toastState.toasts.splice(0)
      const runtime = useSettingsBackupRuntime({
        runtime: {
          isActive: { value: true },
          nextRequest: () => 1,
          isLatestRequest: () => true,
          invalidateRequest: () => {},
        },
        requestKey: 'settings:test-backups',
        requireSavedSettings: () => true,
      })
      const backingUp = runtime.runBackupNow()
      await Promise.resolve()
      useConfirmDialog().confirm()
      await Promise.resolve()

      assert.equal(runtime.operationProgress.open, true)
      assert.equal(runtime.operationProgress.busy, true)
      assert.equal(runtime.operationProgress.title, '立即备份')
      assert.equal(requestCount, 0, '应先渲染执行抽屉再提交备份请求')

      await new Promise((resolve) => setTimeout(resolve, 0))
      response.resolve({ result: { key: 'backups/2026-08-02.json' } })
      await backingUp

      assert.equal(runtime.operationProgress.busy, false)
      assert.equal(runtime.operationProgress.tone, 'success')
      assert.match(runtime.operationProgress.message, /backups\/2026-08-02\.json/)
      assert.deepEqual(
        runtime.operationProgress.events.map((event) => event.label),
        ['开始处理', '刷新记录', '已完成'],
      )
      assert.equal(toastState.toasts.length, 0, '已有执行抽屉时不应重复弹出 Toast')
    } finally {
      settingsApi.runBackup = originalRunBackup
      settingsApi.listBackups = originalListBackups
    }
  }

  {
    const response = deferred()
    let requestCount = 0
    const runtime = useSettingsPromptSourcesOperationRuntime({
      sources: ref([
        { id: 'one', enabled: true },
        { id: 'two', enabled: true },
        { id: 'off', enabled: false },
      ]),
      refreshSources: () => {
        requestCount += 1
        return response.promise
      },
    })
    const refreshing = runtime.refreshAllSources()

    assert.equal(runtime.operationProgress.open, true)
    assert.equal(runtime.operationProgress.busy, true)
    assert.equal(runtime.operationProgress.title, '更新提示词快照')
    assert.equal(runtime.operationProgress.subtitle, '3 个词源')
    assert.equal(runtime.operationProgress.total, 1)
    assert.equal(requestCount, 0, '应先渲染执行抽屉再提交词源同步请求')

    await new Promise((resolve) => setTimeout(resolve, 0))
    response.resolve({
      enabled_source_count: 2,
      source_error_count: 1,
      prompt_count: 120,
      sync_summary: {
        status: 'partial',
        tone: 'warning',
        total: 2,
        succeeded: 1,
        failed: 1,
        message: '词源同步完成：成功 1，失败 1，共 120 条提示词',
      },
    })
    await refreshing

    assert.equal(runtime.operationProgress.busy, false)
    assert.equal(runtime.operationProgress.tone, 'warning')
    assert.match(runtime.operationProgress.message, /成功 1.*失败 1/)
  }
} finally {
  await server.close()
}
