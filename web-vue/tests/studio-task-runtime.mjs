import assert from 'node:assert/strict'
import { createSSRApp, computed, h, nextTick, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

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

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

try {
  replaceGlobal('window', {
    location: { origin: 'http://console.local' },
  })

  const { useStudioTaskPollingCoordinator } = await server.ssrLoadModule(
    '/src/views/studio/studioTaskPollingCoordinator.ts',
  )
  const {
    editableFileTaskDownloadError,
    editableFileTaskDownloadFilename,
    useEditableFileTaskDownload,
  } = await server.ssrLoadModule('/src/components/studio/editableFileTaskView.ts')
  const { default: StudioMessageItem } = await server.ssrLoadModule(
    '/src/components/studio/StudioMessageItem.vue',
  )
  const { imageTasksApi } = await server.ssrLoadModule('/src/api/imageTasks.ts')
  const { useStudioImageTaskRuntime } = await server.ssrLoadModule(
    '/src/views/studio/studioImageTaskRuntime.ts',
  )
  const {
    buildStudioConversationLookup,
    buildStudioConversationRuntimeIndex,
  } = await server.ssrLoadModule('/src/views/studio/studioConversationState.ts')

  const resumableTask = {
    id: 'image-task-timeout',
    status: 'failed',
    terminal: true,
    mode: 'generate',
    model: 'gpt-image-2',
    size: '1024x1024',
    quality: 'auto',
    stage_code: 'failed',
    stage_label: '等待结果超时',
    created_at: '2026-08-02 10:00:00',
    updated_at: '2026-08-02 10:02:00',
    requested_count: 1,
    succeeded_count: 0,
    failed_count: 1,
    pending_count: 0,
    duration_ms: 120000,
    elapsed_ms: 120000,
    error_code: 'image_poll_timeout',
    public_error: '等待图片结果超时',
    results: [],
    actions: { resume_poll: true },
  }
  const resumableMessageView = {
    id: 'assistant-timeout',
    role: 'assistant',
    mode: 'image',
    content: '',
    createdAt: '2026-08-02T10:00:00Z',
    status: 'error',
    taskId: resumableTask.id,
    error: resumableTask.public_error,
    memoKey: 'assistant-timeout:1',
    task: resumableTask,
    assets: [],
    isImageMessage: true,
    isPendingImageMessage: false,
    isSingleImageResult: false,
    imageSlotCount: 1,
    pendingSlots: [],
    failedSlots: [0],
    imagePendingStageText: '',
    primaryMessage: resumableTask.public_error,
    isCollapsible: false,
    isCollapsed: false,
    markdownContent: '',
    searchQueries: [],
  }
  const resumableHtml = await renderToString(createSSRApp({
    render: () => h(StudioMessageItem, { message: resumableMessageView }),
  }))
  assert.match(resumableHtml, /aria-label="继续任务"/)
  assert.doesNotMatch(resumableHtml, /aria-label="重试并重新提交"/)

  const failedTask = {
    ...resumableTask,
    error_code: 'image_tool_error',
    public_error: '图片生成失败',
    actions: { resume_poll: false },
  }
  const failedHtml = await renderToString(createSSRApp({
    render: () => h(StudioMessageItem, {
      message: {
        ...resumableMessageView,
        id: 'assistant-failed',
        taskId: failedTask.id,
        task: failedTask,
        error: failedTask.public_error,
        primaryMessage: failedTask.public_error,
      },
    }),
  }))
  assert.match(failedHtml, /aria-label="重试并重新提交"/)
  assert.doesNotMatch(failedHtml, /aria-label="继续任务"/)

  const canRun = ref(true)
  const requestedTaskIds = ref(['task-1'])
  const pendingTaskIds = computed(() => requestedTaskIds.value)
  const requestVersions = new Map()
  const timers = new Map()
  const intervals = new Map()
  const pageRuntime = {
    canRun,
    nextRequest(key) {
      const version = (requestVersions.get(key) || 0) + 1
      requestVersions.set(key, version)
      return version
    },
    isLatestRequest(key, version) {
      return canRun.value && requestVersions.get(key) === version
    },
    invalidateRequest(key) {
      requestVersions.set(key, (requestVersions.get(key) || 0) + 1)
    },
    setTimer(key, _delay, callback) {
      timers.set(key, callback)
    },
    clearTimer(key) {
      timers.delete(key)
    },
    setInterval(key, _delay, callback) {
      intervals.set(key, callback)
    },
    clearInterval(key) {
      intervals.delete(key)
    },
  }

  const firstRequest = deferred()
  const loadCalls = []
  const appliedResponses = []
  let clearCount = 0
  const coordinator = useStudioTaskPollingCoordinator({
    pageRuntime,
    requestedTaskIds: computed(() => requestedTaskIds.value),
    pendingTaskIds,
    requestKey: 'request',
    pollTimerKey: 'poll',
    refreshTimerKey: 'refresh',
    loadTasks: async ids => {
      loadCalls.push([...ids])
      if (loadCalls.length === 1) return firstRequest.promise
      return { items: [{ id: ids[0] }], missing_ids: [] }
    },
    applyResponse: response => appliedResponses.push(response),
    clearTasks: () => {
      clearCount += 1
    },
    onRefreshError: error => {
      throw error
    },
  })

  const initialRefresh = coordinator.refresh()
  assert.equal(coordinator.isFetchingTasks.value, true)
  await coordinator.refresh(true)
  assert.deepEqual(loadCalls, [['task-1']])

  firstRequest.resolve({ items: [{ id: 'task-1' }], missing_ids: [] })
  await initialRefresh
  assert.equal(timers.has('refresh'), true)
  timers.get('refresh')()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(loadCalls, [['task-1'], ['task-1']])
  assert.equal(appliedResponses.length, 2)

  await coordinator.refresh()
  assert.equal(loadCalls.length, 2)

  coordinator.schedulePoll()
  assert.equal(intervals.has('poll'), true)

  canRun.value = false
  coordinator.deactivate()
  assert.equal(timers.size, 0)
  assert.equal(intervals.size, 0)
  canRun.value = true
  await coordinator.refresh()
  assert.equal(loadCalls.length, 3)

  requestedTaskIds.value = []
  await nextTick()
  await coordinator.refresh(true)
  assert.equal(clearCount, 1)
  coordinator.dispose()

  const originalResumePoll = imageTasksApi.resumePoll
  const resumeCalls = []
  const failedAssistantMessage = {
    id: 'assistant-timeout',
    role: 'assistant',
    mode: 'image',
    content: '',
    createdAt: '2026-08-02T10:00:00Z',
    status: 'error',
    taskId: resumableTask.id,
    error: resumableTask.public_error,
  }
  const conversation = {
    id: 'conversation-1',
    title: '保留完整对话',
    createdAt: '2026-08-02T10:00:00Z',
    updatedAt: '2026-08-02T10:03:00Z',
    messages: [
      {
        id: 'user-before-timeout',
        role: 'user',
        mode: 'image',
        content: '画一座灯塔',
        createdAt: '2026-08-02T10:00:00Z',
        status: 'done',
      },
      failedAssistantMessage,
      {
        id: 'user-after-timeout',
        role: 'user',
        mode: 'chat',
        content: '这条消息不能被裁剪',
        createdAt: '2026-08-02T10:03:00Z',
        status: 'done',
      },
    ],
  }
  const conversations = ref([conversation])
  const activeConversation = computed(() => conversations.value[0] || null)
  const conversationLookup = computed(() => buildStudioConversationLookup(conversations.value))
  const conversationRuntimeIndex = computed(() => buildStudioConversationRuntimeIndex(conversations.value))
  const resumedTask = {
    ...resumableTask,
    status: 'running',
    terminal: false,
    stage_code: 'polling',
    stage_label: '继续等待图片结果',
    failed_count: 0,
    pending_count: 1,
    error_code: '',
    public_error: '',
    actions: { resume_poll: false },
  }
  imageTasksApi.resumePoll = async taskId => {
    resumeCalls.push(taskId)
    return resumedTask
  }
  try {
    const touchedConversations = []
    const runtime = useStudioImageTaskRuntime({
      pageRuntime,
      activeConversation,
      conversationNotices: computed(() => ({})),
      conversationLookup,
      conversationRuntimeIndex,
      hooks: {
        markConversationNotice: () => {},
        touchConversation: item => touchedConversations.push(item.id),
        onRefreshError: message => { throw new Error(message) },
        formatError: error => String(error),
      },
    })
    runtime.merge([resumableTask])
    const originalMessages = conversation.messages
    const originalMessageIds = conversation.messages.map(message => message.id)

    const task = await runtime.resumePoll(resumableTask.id)

    assert.equal(task, resumedTask)
    assert.deepEqual(resumeCalls, [resumableTask.id])
    assert.deepEqual(runtime.taskById.value.get(resumableTask.id), resumedTask)
    assert.equal(failedAssistantMessage.status, 'running')
    assert.equal(failedAssistantMessage.error, undefined)
    assert.equal(conversation.messages, originalMessages)
    assert.deepEqual(conversation.messages.map(message => message.id), originalMessageIds)
    assert.equal(intervals.has('studio:image-poll'), true)
    assert.deepEqual(touchedConversations, [conversation.id])
    runtime.dispose()
  } finally {
    imageTasksApi.resumePoll = originalResumePoll
  }

  const pptTask = { id: 'ppt-task', kind: 'ppt' }
  const psdTask = { id: 'psd-task', kind: 'psd' }
  assert.equal(
    editableFileTaskDownloadFilename(pptTask, '/files/ppt/result.pptx', 'file'),
    'result.pptx',
  )
  assert.equal(
    editableFileTaskDownloadFilename(psdTask, '/files/psd/', 'file'),
    'psd-psd-task.psd',
  )
  assert.equal(
    editableFileTaskDownloadFilename(pptTask, '/files/ppt/', 'zip'),
    'ppt-ppt-task.zip',
  )
  assert.equal(editableFileTaskDownloadError(new Error('download denied')), 'download denied')
  assert.equal(editableFileTaskDownloadError('download denied'), '文件下载失败')

  const downloadRequest = deferred()
  const downloadCalls = []
  const downloadErrors = []
  const downloadRuntime = useEditableFileTaskDownload({
    onError: message => downloadErrors.push(message),
    downloadFile: async (url, filename) => {
      downloadCalls.push({ url, filename })
      return downloadRequest.promise
    },
  })
  const activeDownload = downloadRuntime.download(pptTask, '/files/ppt/result.pptx', 'file')
  assert.equal(downloadRuntime.isDownloading.value, true)
  assert.equal(await downloadRuntime.download(pptTask, '/files/ppt/result.zip', 'zip'), false)
  downloadRequest.resolve()
  assert.equal(await activeDownload, true)
  assert.equal(downloadRuntime.isDownloading.value, false)
  assert.deepEqual(downloadCalls, [{
    url: '/files/ppt/result.pptx',
    filename: 'result.pptx',
  }])
  assert.deepEqual(downloadErrors, [])

  const failingDownloadRuntime = useEditableFileTaskDownload({
    onError: message => downloadErrors.push(message),
    downloadFile: async () => {
      throw new Error('file expired')
    },
  })
  assert.equal(await failingDownloadRuntime.download(psdTask, '/files/psd/result.psd', 'file'), false)
  assert.deepEqual(downloadErrors, ['file expired'])
} finally {
  restoreGlobal('window', originalWindow)
  await server.close()
}
