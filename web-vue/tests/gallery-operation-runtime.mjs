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
} finally {
  await server.close()
}
