import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { default: RemoteAccountImportPanel } = await server.ssrLoadModule(
    '/src/components/ai/RemoteAccountImportPanel.vue',
  )

  assert.equal(RemoteAccountImportPanel.props.externalTracking.default, false)
  assert.equal(RemoteAccountImportPanel.emits.includes('started'), true)

  const source = await readFile(
    new URL('../src/components/ai/RemoteAccountImportPanel.vue', import.meta.url),
    'utf8',
  )
  assert.match(source, /externalTracking\?: boolean/)
  assert.match(source, /started: \[value: RemoteAccountImportStarted\]/)

  assert.equal(
    source.match(/if \(props\.externalTracking\) return/g)?.length,
    2,
    'external tracking must hand both remote import modes to the parent before component polling',
  )
  assert.match(source, /emitStarted\('cpa', poolId, importJob\.value, title, names\.length\)/)
  assert.match(source, /emitStarted\('sub2api', serverId, importJob\.value, title, accountIds\.length\)/)

  assert.match(source, /emitRecoverableImportJobs\('cpa', cpaPools\.value, selectedCPAPoolId\.value\)/)
  assert.match(source, /emitRecoverableImportJobs\('sub2api', sub2apiServers\.value, selectedSub2APIServerId\.value\)/)
  assert.match(source, /job\.status !== 'pending' && job\.status !== 'running'/)
  assert.match(source, /emittedImportJobIds\.has\(jobId\)/)
  assert.equal(
    source.match(/emit\('progress', \{ title, total: (?:names|accountIds)\.length \}\)/g)?.length,
    2,
    'both remote imports must publish initial progress before starting the request',
  )
  assert.equal(
    source.match(/emit\('progress', \{ title, total: (?:names|accountIds)\.length, error: message \}\)/g)?.length,
    2,
    'start failures must reach the parent operation drawer under external tracking',
  )
  assert.equal(
    source.match(/if \(!props\.externalTracking\) toast\.error\(message\)/g)?.length,
    2,
    'external tracking must not duplicate remote import failures in both the drawer and a toast',
  )
} finally {
  await server.close()
}
