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
  const { galleryApi } = await server.ssrLoadModule('/src/api/gallery.ts')
  const { useGalleryOperationsRuntime } = await server.ssrLoadModule(
    '/src/views/gallery/galleryOperationsRuntime.ts',
  )
  const { genboxStatusLabel } = await server.ssrLoadModule(
    '/src/views/gallery/galleryView.ts',
  )
  const originalDeleteFiles = galleryApi.deleteFiles
  const request = deferred()
  const notifications = []
  const selectedPaths = ref(new Set(['images/one.png', 'images/two.png']))
  let cleared = false
  galleryApi.deleteFiles = () => request.promise

  try {
    const runtime = useGalleryOperationsRuntime({
      runtime: {
        isActive: ref(true),
        nextRequest: () => 1,
        isLatestRequest: () => true,
        invalidateRequest: () => {},
      },
      confirmDialog: { ask: async () => true },
      toast: {
        success: (...args) => notifications.push(['success', ...args]),
        error: (...args) => notifications.push(['error', ...args]),
      },
      files: ref([]),
      currentPage: ref(1),
      storageStats: ref(null),
      selectedPaths,
      loadGallery: async () => {},
      closePreviewIfPath: () => {},
      closeTagEditorIfPath: () => {},
      clearSelection: () => {
        cleared = true
        selectedPaths.value = new Set()
      },
    })

    const deletion = runtime.handleDeleteSelected()
    await Promise.resolve()
    assert.equal(runtime.operationProgress.open, true)
    assert.equal(runtime.operationProgress.busy, true)

    request.resolve({ removed: 2 })
    await deletion

    assert.equal(cleared, true)
    assert.equal(runtime.operationProgress.busy, false)
    assert.equal(runtime.operationProgress.message, '已删除 2 张图片')
    assert.deepEqual(
      runtime.operationProgress.events.map((event) => event.label),
      ['开始处理', '刷新列表', '已完成'],
    )
    assert.deepEqual(notifications, [], '执行结果已在抽屉显示时不应重复通知')
  } finally {
    galleryApi.deleteFiles = originalDeleteFiles
  }

  {
    const originalPushToGenBox = galleryApi.pushToGenBox
    const pushRequest = deferred()
    const pushNotifications = []
    let pushCalls = 0
    let reloadCount = 0
    galleryApi.pushToGenBox = (path) => {
      pushCalls += 1
      assert.equal(path, 'images/one.png')
      return pushRequest.promise
    }

    try {
      const runtime = useGalleryOperationsRuntime({
        runtime: {
          isActive: ref(true),
          nextRequest: () => 1,
          isLatestRequest: () => true,
          invalidateRequest: () => {},
        },
        confirmDialog: { ask: async () => true },
        toast: {
          success: (...args) => pushNotifications.push(['success', ...args]),
          error: (...args) => pushNotifications.push(['error', ...args]),
        },
        files: ref([]),
        currentPage: ref(1),
        storageStats: ref(null),
        selectedPaths: ref(new Set()),
        loadGallery: async () => {
          reloadCount += 1
        },
        closePreviewIfPath: () => {},
        closeTagEditorIfPath: () => {},
        clearSelection: () => {},
      })

      const first = runtime.handleGenBoxPush({ path: 'images/one.png' })
      await Promise.resolve()
      assert.equal(runtime.genboxPushBusyPath.value, 'images/one.png')
      const second = runtime.handleGenBoxPush({ path: 'images/one.png' })
      await Promise.resolve()
      assert.equal(pushCalls, 1)

      pushRequest.resolve({
        path: 'images/one.png',
        status: 'imported',
        sha256: 'a'.repeat(64),
        updated_at: '2026-07-25T12:00:00Z',
        source_retained: true,
      })
      await Promise.all([first, second])

      assert.equal(runtime.genboxPushBusyPath.value, null)
      assert.equal(reloadCount, 1)
      assert.deepEqual(pushNotifications, [['success', '已推送到 GenBox', 'Push 成功']])
    } finally {
      galleryApi.pushToGenBox = originalPushToGenBox
    }

    assert.equal(genboxStatusLabel({ genbox_push: { status: 'imported' } }), '已推送 GenBox')
    assert.equal(genboxStatusLabel({ genbox_push: { status: 'already-imported' } }), 'GenBox 已存在')
    assert.equal(genboxStatusLabel({ genbox_push: { status: 'duplicate-local' } }), 'GenBox 本地重复')
    assert.equal(genboxStatusLabel({ genbox_push: null }), '')
    assert.equal(genboxStatusLabel({}), '')
  }
} finally {
  await server.close()
}
