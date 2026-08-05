import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { default: OperationProgressDrawer } = await server.ssrLoadModule(
    '/src/components/ai/OperationProgressDrawer.vue',
  )

  assert.equal(OperationProgressDrawer.props.determinate, undefined)
  assert.equal(OperationProgressDrawer.props.tone.default, 'success')
  assert.equal(OperationProgressDrawer.props.presentation, undefined)

  const [
    logsSource,
    detailSource,
    progressSource,
    gallerySource,
    featureStyles,
    accountsSource,
    accountProgressSource,
    proxySource,
    proxyImportSource,
    logsTableSource,
    requestDetailDrawerSource,
  ] = await Promise.all([
    readFile(new URL('../src/views/Logs.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/logs/LogsDetailDrawer.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/ai/OperationProgressDrawer.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/Gallery.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/styles/features.css', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/Accounts.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/accounts/AccountOperationDrawer.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/Proxy.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/proxy/ProxyNodeImportModal.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/logs/LogsSystemTable.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/ai/RequestDetailDrawer.vue', import.meta.url), 'utf8'),
  ])

  assert.match(logsSource, /<OperationProgressDrawer/)
  assert.match(logsSource, /import OperationProgressDrawer from '@\/components\/ai\/OperationProgressDrawer\.vue'/)
  assert.equal(
    logsSource.match(/<ConfirmDialog\b/g)?.length,
    1,
    'single and batch deletion should share one concise confirmation dialog',
  )

  assert.doesNotMatch(detailSource, /app-side-panel-motion/)
  assert.doesNotMatch(progressSource, /app-side-panel-motion/)
  assert.match(detailSource, /<RequestDetailDrawer/)
  assert.match(detailSource, /import RequestDetailDrawer from '@\/components\/ai\/RequestDetailDrawer\.vue'/)
  assert.match(detailSource, /import RequestDetailTimeline from '@\/views\/logs\/RequestDetailTimeline\.vue'/)
  assert.match(requestDetailDrawerSource, /<DrawerShell/)
  assert.match(requestDetailDrawerSource, /<SideDock/)
  assert.doesNotMatch(requestDetailDrawerSource, /<Teleport\b/)
  assert.doesNotMatch(detailSource, /placement="end"/)
  assert.doesNotMatch(detailSource, /h-\[calc\(100dvh-2rem\)\]/)
  assert.match(progressSource, /<DrawerShell/)
  assert.match(progressSource, /<SideDock/)
  assert.doesNotMatch(progressSource, /<Teleport\b/)
  assert.doesNotMatch(progressSource, /ModalShell/)
  assert.doesNotMatch(progressSource, /presentation/)
  assert.match(progressSource, /任务记录/)
  assert.match(progressSource, /operation-progress-event__marker/)
  assert.doesNotMatch(progressSource, /LoadingState/)
  assert.doesNotMatch(featureStyles, /\.app-side-panel-motion\s*\{/)
  assert.doesNotMatch(featureStyles, /@keyframes app-side-panel-enter/)
  assert.doesNotMatch(accountsSource, /\bsticky-actions\b/)
  assert.match(accountProgressSource, /<OperationProgressDrawer/)
  assert.match(accountProgressSource, /import OperationProgressDrawer from '@\/components\/ai\/OperationProgressDrawer\.vue'/)
  assert.doesNotMatch(accountProgressSource, /account-operation-event__marker/)
  assert.doesNotMatch(accountProgressSource, /<Teleport\b/)
  assert.doesNotMatch(accountProgressSource, /<aside\b/)
  assert.doesNotMatch(proxySource, /\bsticky-actions\b/)
  assert.match(proxyImportSource, /<ModalShell[\s\S]*?:open="formOpen"/)
  assert.match(
    proxyImportSource,
    /<OperationProgressDrawer/,
    '代理批量导入的执行反馈应使用统一右侧抽屉',
  )
  assert.doesNotMatch(logsTableSource, /\bsticky-actions\b/)

  assert.match(
    gallerySource,
    /<OperationProgressDrawer/,
    'gallery batch feedback should use the same drawer presentation as logs',
  )
  assert.match(logsSource, /<OperationProgressDrawer[\s\S]*?:events="operationProgress\.events"/)
  assert.match(gallerySource, /<OperationProgressDrawer[\s\S]*?:events="operationProgress\.events"/)
} finally {
  await server.close()
}
