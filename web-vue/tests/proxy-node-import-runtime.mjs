import assert from 'node:assert/strict'
import { ref } from 'vue'
import { createServer } from 'vite'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { useProxyNodeImportRuntime } = await server.ssrLoadModule(
    '/src/views/proxy/proxyNodeImportRuntime.ts',
  )
  const {
    mergeImportedProxyNodes,
    useProxyGroupRuntime,
  } = await server.ssrLoadModule('/src/views/proxy/proxyGroupRuntime.ts')
  const { useProxyDefaultRuntime } = await server.ssrLoadModule('/src/views/proxy/proxyDefaultRuntime.ts')
  const { useAccountProxyRuntime } = await server.ssrLoadModule('/src/views/accounts/accountProxyRuntime.ts')
  const {
    proxyGroupActionItems,
    proxyGroupRowSignature,
    proxyTestToastType,
  } = await server.ssrLoadModule('/src/views/proxy/proxyView.ts')
  const { proxyApi } = await server.ssrLoadModule('/src/api/proxy.ts')
  const { useConfirmDialog } = await server.ssrLoadModule('/src/composables/useConfirmDialog.ts')
  const { toastState } = await server.ssrLoadModule('/src/composables/useToast.ts')
  const confirmDialog = useConfirmDialog()
  const pageRuntime = {
    nextRequest: () => 1,
    isLatestRequest: () => true,
    invalidateRequest: () => {},
  }

  {
    const usedGroup = {
      id: 'used',
      name: '已引用代理组',
      strategy: 'request_random',
      rotation_interval_minutes: 0,
      enabled: true,
      notes: '',
      nodes: [],
      reference_text: 'group:used',
      health: {
        state: 'unknown',
        checked_at: null,
        latency_ms: null,
        error: null,
      },
      can_delete: false,
      references: ['默认出口', '账号组 writers'],
    }
    const actions = proxyGroupActionItems(usedGroup, '', '', '')
    const deleteAction = actions.find((item) => item.key === 'delete')

    assert.equal(deleteAction.disabled, true)
    assert.equal(deleteAction.label, '不可删除 · 默认出口、账号组 writers')
  }

  {
    const deletableGroup = {
      id: 'unused',
      name: '未引用代理组',
      strategy: 'request_random',
      rotation_interval_minutes: 0,
      enabled: true,
      notes: '',
      nodes: [],
      reference_text: 'group:unused',
      health: {
        state: 'unknown',
        checked_at: null,
        latency_ms: null,
        error: null,
      },
      can_delete: true,
      references: [],
    }
    const runtime = useProxyGroupRuntime()

    runtime.handleProxyGroupAction(deletableGroup, 'delete')
    await Promise.resolve()

    assert.equal(confirmDialog.open.value, true)
    assert.equal(
      confirmDialog.message.value,
      '确认删除代理组 未引用代理组？该代理组当前未被任何出口、账号组或账号引用，删除后无法恢复。',
    )
    confirmDialog.cancel()
    await Promise.resolve()
  }

  {
    const originalDeleteGroup = proxyApi.deleteGroup
    let deleteCalls = 0
    proxyApi.deleteGroup = async () => {
      deleteCalls += 1
      return { revision: 'unexpected', deleted_id: 'used' }
    }
    try {
      const runtime = useProxyGroupRuntime()
      const usedGroup = {
        id: 'used',
        name: '已引用代理组',
        strategy: 'request_random',
        rotation_interval_minutes: 0,
        enabled: true,
        notes: '',
        nodes: [],
        reference_text: 'group:used',
        health: {
          state: 'unknown',
          checked_at: null,
          latency_ms: null,
          error: null,
        },
        can_delete: false,
        references: ['默认出口'],
      }

      runtime.handleProxyGroupAction(usedGroup, 'delete')
      await Promise.resolve()

      assert.equal(confirmDialog.open.value, false)
      assert.equal(deleteCalls, 0)
    } finally {
      proxyApi.deleteGroup = originalDeleteGroup
    }
  }

  {
    const baseGroup = {
      id: 'signature-group',
      name: '签名代理组',
      strategy: 'request_random',
      rotation_interval_minutes: 0,
      enabled: true,
      notes: '',
      nodes: [],
      reference_text: 'group:signature-group',
      health: {
        state: 'unknown',
        checked_at: null,
        latency_ms: null,
        error: null,
      },
      can_delete: true,
      references: [],
    }
    const availableSignature = proxyGroupRowSignature(baseGroup, '', '', '')
    const referencedSignature = proxyGroupRowSignature({
      ...baseGroup,
      can_delete: false,
      references: ['默认出口'],
    }, '', '', '')

    assert.notEqual(availableSignature, referencedSignature)
  }

  {
    assert.equal(proxyTestToastType('success'), 'success')
    assert.equal(proxyTestToastType('warning'), 'warning')
    assert.equal(proxyTestToastType('danger'), 'error')
  }

  {
    const originalTestGroup = proxyApi.testGroup
    proxyApi.testGroup = async () => ({
      summary: {
        status: 'partial',
        tone: 'warning',
        total: 2,
        succeeded: 1,
        failed: 1,
        max_latency_ms: 80,
        label: '代理组部分可用',
        message: '2 个节点中 1 个可用，1 个失败',
      },
      results: [{
        node_id: 'node-1',
        result: {
          ok: true,
          status: 200,
          latency_ms: 80,
          error: null,
        },
      }],
      result: null,
    })
    try {
      toastState.toasts.splice(0)
      const runtime = useProxyDefaultRuntime({
        runtime: pageRuntime,
        requestKey: 'proxy-test',
        groups: ref([]),
        testingKey: ref(''),
        updateGroups: () => {},
      })
      runtime.selectDefaultProxyGroup('mixed')
      const request = runtime.testDefaultProxy()
      await Promise.resolve()
      confirmDialog.confirm()
      await request

      assert.deepEqual(
        { type: toastState.toasts.at(-1)?.type, message: toastState.toasts.at(-1)?.message },
        { type: 'warning', message: '2 个节点中 1 个可用，1 个失败' },
      )
    } finally {
      proxyApi.testGroup = originalTestGroup
    }
  }

  {
    const originalTestGroup = proxyApi.testGroup
    proxyApi.testGroup = async () => ({
      summary: {
        status: 'partial',
        tone: 'warning',
        total: 3,
        succeeded: 2,
        failed: 1,
        max_latency_ms: 120,
        label: '代理组部分可用',
        message: '3 个节点中 2 个可用，1 个失败',
      },
      results: [],
      result: null,
    })
    try {
      toastState.toasts.splice(0)
      const runtime = useAccountProxyRuntime({
        proxyGroups: ref([]),
        proxyValue: ref(''),
        setError: () => {},
      })
      runtime.syncProxyControlsFromProjection({
        proxy: 'group:mixed',
        proxy_mode: 'group',
        proxy_group_id: 'mixed',
        proxy_label: '代理组：混合出口',
      })
      const request = runtime.testAccountProxy()
      await Promise.resolve()
      confirmDialog.confirm()
      await request

      assert.deepEqual(
        { type: toastState.toasts.at(-1)?.type, message: toastState.toasts.at(-1)?.message },
        { type: 'warning', message: '3 个节点中 2 个可用，1 个失败' },
      )
    } finally {
      proxyApi.testGroup = originalTestGroup
    }
  }

  {
    const originalTestGroup = proxyApi.testGroup
    const response = deferred()
    proxyApi.testGroup = () => response.promise
    try {
      toastState.toasts.splice(0)
      const runtime = useProxyGroupRuntime()
      const group = {
        id: 'failed-group',
        name: '全部失败代理组',
        strategy: 'request_random',
        rotation_interval_minutes: 0,
        enabled: true,
        notes: '',
        nodes: [{
          id: 'node-1',
          name: '出口 1',
          url: 'http://proxy.example:8080/',
          enabled: true,
          image_concurrency_limit: 30,
          notes: '',
          health: {
            state: 'unknown',
            checked_at: null,
            latency_ms: null,
            error: null,
          },
        }],
        reference_text: 'group:failed-group',
        health: {
          state: 'unknown',
          checked_at: null,
          latency_ms: null,
          error: null,
        },
        can_delete: true,
        references: [],
      }

      runtime.handleProxyGroupAction(group, 'test-all')
      await Promise.resolve()
      confirmDialog.confirm()
      await Promise.resolve()
      assert.equal(runtime.operationProgress.open, true)
      assert.equal(runtime.operationProgress.busy, true)
      assert.equal(runtime.operationProgress.title, '检测代理组节点')
      assert.equal(runtime.operationProgress.total, 1)
      response.resolve({
        summary: {
          status: 'failed',
          tone: 'danger',
          total: 1,
          succeeded: 0,
          failed: 1,
          max_latency_ms: 0,
          label: '代理组不可用',
          message: '1 个节点全部失败',
        },
        results: [],
        result: null,
      })
      await new Promise((resolve) => setTimeout(resolve, 0))

      assert.equal(runtime.operationProgress.busy, false)
      assert.equal(runtime.operationProgress.tone, 'danger')
      assert.equal(runtime.operationProgress.error, '1 个节点全部失败')
      assert.equal(toastState.toasts.length, 0, '已有执行抽屉时不应重复弹出 Toast')
    } finally {
      proxyApi.testGroup = originalTestGroup
    }
  }

  {
    const response = deferred()
    let requestCount = 0
    const applied = []
    const runtime = useProxyNodeImportRuntime({
      importNodes: () => {
        requestCount += 1
        return response.promise
      },
      onApply: (result) => applied.push(result),
      formatError: (error) => String(error),
    })

    runtime.activate()
    runtime.sourceText.value = 'http://one.example:8080 10\ninvalid-proxy'
    const submission = runtime.submit([])

    assert.equal(runtime.formOpen.value, false)
    assert.equal(runtime.operationProgress.open, true)
    assert.equal(runtime.operationProgress.title, '批量添加代理节点')
    assert.equal(requestCount, 0, '应先渲染抽屉再提交代理导入请求')
    await new Promise((resolve) => setTimeout(resolve, 0))
    assert.equal(requestCount, 1)

    response.resolve({
      nodes: [{ url: 'http://one.example:8080/', image_concurrency_limit: 10 }],
      added_count: 1,
      duplicate_count: 0,
      invalid_count: 1,
      invalid_items: [{ line: 2, raw: 'invalid-proxy', reason: '代理地址格式无效' }],
    })
    await submission

    assert.equal(applied.length, 1)
    assert.equal(runtime.operationProgress.busy, false)
    assert.equal(runtime.operationProgress.tone, 'warning')
    assert.equal(runtime.operationProgress.message, '已添加 1 个，1 行格式错误')
    assert.equal(runtime.closeProgress(), 'resume')
    assert.equal(runtime.formOpen.value, true)
    assert.equal(runtime.sourceText.value, 'invalid-proxy')
  }

  {
    const requestA = deferred()
    const requestB = deferred()
    const requests = [requestA, requestB]
    const applied = []
    const runtime = useProxyNodeImportRuntime({
      importNodes: () => requests.shift().promise,
      onApply: (result) => applied.push(result),
      formatError: (error) => String(error),
    })
    const resultA = {
      nodes: [{ url: 'http://stale.example:8080/', image_concurrency_limit: 10 }],
      added_count: 1,
      duplicate_count: 0,
      invalid_count: 0,
      invalid_items: [],
    }
    const resultB = {
      nodes: [{ url: 'http://current.example:8080/', image_concurrency_limit: 20 }],
      added_count: 1,
      duplicate_count: 0,
      invalid_count: 0,
      invalid_items: [],
    }

    runtime.activate()
    runtime.sourceText.value = 'http://stale.example:8080 10'
    const submissionA = runtime.submit([])
    await new Promise((resolve) => setTimeout(resolve, 0))
    runtime.deactivate()
    runtime.activate()
    runtime.sourceText.value = 'http://current.example:8080 20'
    const submissionB = runtime.submit([])
    await new Promise((resolve) => setTimeout(resolve, 0))

    requestA.resolve(resultA)
    await submissionA
    assert.deepEqual(applied, [])
    assert.equal(runtime.sourceText.value, 'http://current.example:8080 20')
    assert.equal(runtime.submitError.value, '')
    assert.equal(runtime.submitting.value, true)

    requestB.resolve(resultB)
    await submissionB
    assert.deepEqual(applied, [resultB])
    assert.equal(runtime.submitting.value, false)
  }

  {
    const requestA = deferred()
    const requestB = deferred()
    const requests = [requestA, requestB]
    const applied = []
    const runtime = useProxyNodeImportRuntime({
      importNodes: () => requests.shift().promise,
      onApply: (result) => applied.push(result),
      formatError: (error) => error.message,
    })

    runtime.activate()
    runtime.sourceText.value = 'http://stale.example:8080'
    const submissionA = runtime.submit([])
    await new Promise((resolve) => setTimeout(resolve, 0))
    runtime.deactivate()
    runtime.activate()
    runtime.sourceText.value = 'http://current.example:8080'
    const submissionB = runtime.submit([])
    await new Promise((resolve) => setTimeout(resolve, 0))

    requestA.reject(new Error('stale failure'))
    await submissionA
    assert.deepEqual(applied, [])
    assert.equal(runtime.submitError.value, '')
    assert.equal(runtime.sourceText.value, 'http://current.example:8080')
    assert.equal(runtime.submitting.value, true)

    requestB.reject(new Error('current failure'))
    await submissionB
    assert.equal(runtime.submitError.value, 'current failure')
    assert.equal(runtime.submitting.value, false)
  }

  const existingNode = {
    id: 'existing',
    name: '既有节点',
    url: 'http://existing.example:8080/',
    enabled: true,
    image_concurrency_limit: 7,
    notes: 'keep',
  }
  const appended = mergeImportedProxyNodes(
    [existingNode],
    [{ url: 'http://new.example:8080/', image_concurrency_limit: 20 }],
  )
  assert.equal(appended.length, 2)
  assert.equal(appended[0], existingNode)
  assert.equal(appended[1].name, '出口 2')
  assert.equal(appended[1].url, 'http://new.example:8080/')
  assert.equal(appended[1].image_concurrency_limit, 20)

  const emptyDefaultNode = {
    id: 'placeholder',
    name: '出口 1',
    url: '',
    enabled: true,
    image_concurrency_limit: 30,
    notes: '',
  }
  const filledPlaceholder = mergeImportedProxyNodes(
    [emptyDefaultNode],
    [{ url: 'http://first.example:8080/', image_concurrency_limit: 30 }],
  )
  assert.equal(filledPlaceholder.length, 1)
  assert.equal(filledPlaceholder[0].name, '出口 1')

  const customizedEmptyPlaceholder = {
    ...emptyDefaultNode,
    name: '尚未填写地址',
    notes: '这仍然只是空占位项',
    image_concurrency_limit: 7,
  }
  const replacedCustomizedPlaceholder = mergeImportedProxyNodes(
    [customizedEmptyPlaceholder],
    [{ url: 'http://first.example:8080/', image_concurrency_limit: 0 }],
  )
  assert.equal(replacedCustomizedPlaceholder.length, 1)
  assert.equal(replacedCustomizedPlaceholder[0].name, '出口 1')
  assert.equal(replacedCustomizedPlaceholder[0].image_concurrency_limit, 0)

  const originalSaveGroup = proxyApi.saveGroup
  const originalTestGroup = proxyApi.testGroup
  let savedPayload = null
  let testedPayload = null
  proxyApi.saveGroup = async (payload) => {
    savedPayload = payload
    if (payload.nodes.some((node) => node.url === 'not-a-proxy')) {
      throw new Error('代理地址格式无效')
    }
    return {
      revision: 'test-revision',
      group: {
        id: payload.id,
        name: payload.name,
        strategy: 'request_random',
        rotation_interval_minutes: 0,
        enabled: payload.enabled,
        notes: payload.notes,
        nodes: payload.nodes.map((node) => ({
          ...node,
          health: {
            state: 'unknown',
            checked_at: null,
            latency_ms: null,
            error: null,
          },
        })),
        reference_text: `group:${payload.id}`,
        health: {
          state: 'unknown',
          checked_at: null,
          latency_ms: null,
          error: null,
        },
        can_delete: true,
        references: [],
      },
    }
  }
  proxyApi.testGroup = async (payload) => {
    testedPayload = payload
    return {
      summary: {
        status: 'success',
        tone: 'success',
        total: 1,
        succeeded: 1,
        failed: 0,
        max_latency_ms: 18,
        label: '代理组可用',
        message: '1 个节点全部可用，最慢 18ms',
      },
      results: [],
      result: {
        ok: true,
        status: 200,
        latency_ms: 18,
        error: null,
      },
    }
  }
  try {
    const runtime = useProxyGroupRuntime()
    runtime.openCreateGroupModal()
    runtime.groupForm.name = '后端校验测试'
    runtime.groupForm.nodes[0].url = 'not-a-proxy'
    await runtime.saveProxyGroup()
    assert.equal(savedPayload.nodes[0].url, 'not-a-proxy')
    assert.equal(runtime.showGroupModal.value, true)
    assert.equal(runtime.groupForm.name, '后端校验测试')
    assert.equal(runtime.groupForm.nodes[0].url, 'not-a-proxy')

    runtime.openCreateGroupModal()
    runtime.groupForm.name = '批量导入测试'
    savedPayload = null
    runtime.applyNodeImport({
      nodes: [{
        url: 'socks5://persisted.example:1080/',
        image_concurrency_limit: 16,
      }],
      added_count: 1,
      duplicate_count: 0,
      invalid_count: 0,
      invalid_items: [],
    })
    assert.equal(savedPayload, null)
    await runtime.saveProxyGroup()
    assert.deepEqual(
      savedPayload.nodes.map((node) => node.url),
      ['socks5://persisted.example:1080/'],
    )
    assert.deepEqual(
      savedPayload.nodes.map((node) => node.image_concurrency_limit),
      [16],
    )
    assert.equal(runtime.showGroupModal.value, false)

    runtime.openCreateGroupModal()
    runtime.groupForm.name = '草稿检测'
    runtime.groupForm.nodes[0].url = 'socks5://draft.example:1080/'
    const testPromise = runtime.testProxyGroupNode(
      { id: '', name: '草稿检测' },
      runtime.groupForm.nodes[0],
    )
    await Promise.resolve()
    assert.equal(confirmDialog.open.value, true)
    confirmDialog.confirm()
    await testPromise
    assert.deepEqual(testedPayload, { url: 'socks5://draft.example:1080/' })

    runtime.openCreateGroupModal()
    runtime.groupForm.name = '尚未保存'
    let closePromise = runtime.closeGroupModal()
    await Promise.resolve()
    assert.equal(confirmDialog.open.value, true)
    confirmDialog.cancel()
    await closePromise
    assert.equal(runtime.showGroupModal.value, true)

    closePromise = runtime.closeGroupModal()
    await Promise.resolve()
    confirmDialog.confirm()
    await closePromise
    assert.equal(runtime.showGroupModal.value, false)
  } finally {
    proxyApi.saveGroup = originalSaveGroup
    proxyApi.testGroup = originalTestGroup
  }
} finally {
  await server.close()
}
