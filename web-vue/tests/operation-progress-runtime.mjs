import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const operationDrawerSource = await readFile(
    new URL('../src/components/ai/OperationProgressDrawer.vue', import.meta.url),
    'utf8',
  )
  const accountDrawerSource = await readFile(
    new URL('../src/views/accounts/AccountOperationDrawer.vue', import.meta.url),
    'utf8',
  )
  assert.match(operationDrawerSource, /:show-backdrop="false"/)
  assert.match(operationDrawerSource, /max-width="clamp\(22rem, 30vw, 32rem\)"/)
  assert.match(operationDrawerSource, /<CloseButton\s+icon="lucide:minus"/)
  assert.match(operationDrawerSource, /label="收起任务面板"/)
  assert.doesNotMatch(operationDrawerSource, /<Button[^>]*aria-label="收起任务面板"/)
  assert.match(operationDrawerSource, /open && !minimized/)
  assert.match(operationDrawerSource, /<SideDock/)
  assert.match(operationDrawerSource, /aria-label="展开任务面板"/)
  assert.equal(operationDrawerSource.includes('<Teleport'), false)
  assert.equal(operationDrawerSource.includes('position: fixed'), false)
  assert.match(accountDrawerSource, /<OperationProgressDrawer/)

  const { useOperationProgressRuntime } = await server.ssrLoadModule(
    '/src/composables/useOperationProgressRuntime.ts',
  )

  const runtime = useOperationProgressRuntime()
  await runtime.start({
    title: '批量删除图片',
    subtitle: '已选择 3 张',
    total: 3,
    message: '正在处理...',
  })

  const { events: startedEvents, ...startedState } = runtime.state
  assert.deepEqual({ ...startedState }, {
    open: true,
    title: '批量删除图片',
    subtitle: '已选择 3 张',
    total: 3,
    current: 0,
    statusLabel: '处理中',
    message: '正在处理...',
    error: '',
    busy: true,
    tone: 'info',
  })
  assert.equal(startedEvents.length, 1)
  assert.equal(startedEvents[0].label, '开始处理')
  assert.equal(startedEvents[0].message, '正在处理...')
  assert.equal(startedEvents[0].tone, 'info')

  runtime.succeed('已删除 3 张图片', 3)
  assert.equal(runtime.state.busy, false)
  assert.equal(runtime.state.current, 3)
  assert.equal(runtime.state.statusLabel, '已完成')
  assert.equal(runtime.state.message, '已删除 3 张图片')
  assert.equal(runtime.state.tone, 'success')
  assert.equal(runtime.state.events.length, 2)
  assert.equal(runtime.state.events[1].label, '已完成')
  assert.equal(runtime.state.events[1].message, '已删除 3 张图片')
  assert.equal(runtime.state.events[1].tone, 'success')
  assert.equal(runtime.close(), true)
  assert.equal(runtime.state.open, false)

  await runtime.start({ title: '批量添加代理节点', total: 2, message: '正在处理...' })
  runtime.warn('已添加 1 个，1 行格式错误', 2)
  assert.equal(runtime.state.busy, false)
  assert.equal(runtime.state.current, 2)
  assert.equal(runtime.state.tone, 'warning')
  assert.equal(runtime.state.statusLabel, '部分完成')
  assert.equal(runtime.state.events.length, 2)
  assert.equal(runtime.state.events[1].tone, 'warning')
  assert.equal(runtime.close(), true)

  await runtime.start({ title: '批量删除日志', total: 2, message: '正在处理...' })
  runtime.record({ label: '删除日志', message: '已处理第 1 批', tone: 'info' })
  runtime.fail('删除失败')
  assert.equal(runtime.state.busy, false)
  assert.equal(runtime.state.error, '删除失败')
  assert.equal(runtime.state.tone, 'danger')
  assert.deepEqual(
    runtime.state.events.map(({ label, message, tone }) => ({ label, message, tone })),
    [
      { label: '开始处理', message: '正在处理...', tone: 'info' },
      { label: '删除日志', message: '已处理第 1 批', tone: 'info' },
      { label: '失败', message: '删除失败', tone: 'danger' },
    ],
  )
  assert.equal(runtime.close(), true)

  assert.match(accountDrawerSource, /<OperationProgressDrawer/)
  assert.doesNotMatch(accountDrawerSource, /account-operation-event__marker/)
} finally {
  await server.close()
}
