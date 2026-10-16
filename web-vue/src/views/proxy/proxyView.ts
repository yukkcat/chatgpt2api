import type { ActionMenuItem } from 'nanocat-ui'
import type { ProxyGroup, ProxyNode, ProxyTestResult, ProxyTestTone } from '@/api/proxy'
import { actionMenuGroups } from '@/components/ai/menuItems'

export type DefaultProxyMode = 'direct' | 'group' | 'custom'
export type FallbackProxyMode = 'off' | 'direct' | 'group' | 'custom'
export type ProxyTestSummaryTone = 'success' | 'warning' | 'error'

export function proxyTestToastType(tone: ProxyTestTone): ProxyTestSummaryTone {
  if (tone === 'success') return 'success'
  if (tone === 'warning') return 'warning'
  return 'error'
}

export const defaultProxyModeOptions = [
  { label: 'Direct', value: 'direct' },
  { label: 'Proxy group', value: 'group' },
  { label: 'Custom proxy', value: 'custom' },
] as const

export const fallbackProxyModeOptions = [
  { label: 'Off', value: 'off' },
  { label: 'Direct', value: 'direct' },
  { label: 'Proxy group', value: 'group' },
  { label: 'Custom proxy', value: 'custom' },
] as const

const defaultProxyModes = new Set<string>(defaultProxyModeOptions.map((item) => item.value))
const fallbackProxyModes = new Set<string>(fallbackProxyModeOptions.map((item) => item.value))

export function toDefaultProxyMode(value: string | string[]): DefaultProxyMode {
  const raw = Array.isArray(value) ? value[0] : value
  return defaultProxyModes.has(raw) ? raw as DefaultProxyMode : 'direct'
}

export function toFallbackProxyMode(value: string | string[]): FallbackProxyMode {
  const raw = Array.isArray(value) ? value[0] : value
  return fallbackProxyModes.has(raw) ? raw as FallbackProxyMode : 'off'
}

export function proxyGroupReference(group: Pick<ProxyGroup, 'reference_text'>) {
  return group.reference_text
}

function signatureValue(value: unknown): string {
  return String(value ?? '').trim().replaceAll('|', '/')
}

function boundedSignatureText(value: unknown, limit = 160): string {
  const text = signatureValue(value)
  if (text.length <= limit) return text
  return `${text.length}:${text.slice(0, limit)}:${text.slice(-24)}`
}

function proxyNodeSignature(node: ProxyNode) {
  return [
    node.id,
    node.name,
    boundedSignatureText(node.url, 96),
    node.enabled !== false ? 1 : 0,
    node.image_concurrency_limit,
    node.health.state,
    node.health.latency_ms,
    boundedSignatureText(node.health.error),
    node.health.checked_at,
    boundedSignatureText(node.notes),
  ].map(signatureValue).join(',')
}

function testingKeyForGroup(group: ProxyGroup, testingKey: string) {
  if (testingKey === `group:${group.id}:all`) return testingKey
  return group.nodes.some((node) => testingKey === proxyNodeTestKey(group, node)) ? testingKey : ''
}

export function proxyGroupRowSignature(group: ProxyGroup, testingKey: string, savingGroupId: string, deletingGroupId: string) {
  return [
    group.id,
    group.name,
    group.enabled !== false ? 1 : 0,
    group.strategy,
    group.rotation_interval_minutes,
    boundedSignatureText(group.notes),
    group.nodes.map(proxyNodeSignature).join(';'),
    group.can_delete ? 1 : 0,
    group.references.map((reference) => boundedSignatureText(reference, 96)).join(','),
    testingKeyForGroup(group, testingKey),
    savingGroupId === group.id ? savingGroupId : '',
    deletingGroupId === group.id ? deletingGroupId : '',
  ].map(signatureValue).join('|')
}

export function proxyGroupActionItems(
  group: ProxyGroup,
  testingKey: string,
  savingGroupId: string,
  deletingGroupId: string,
): ActionMenuItem[] {
  const allKey = `group:${group.id}:all`
  return actionMenuGroups(
    [
      {
        key: 'test-all',
        label: testingKey === allKey ? 'Testing...' : 'Test all nodes',
        disabled: testingKey === allKey || group.nodes.length === 0,
      },
    ],
    [
      {
        key: 'toggle-enabled',
        label: savingGroupId === group.id
          ? 'Processing...'
          : group.enabled ? 'Disable proxy group' : 'Enable proxy group',
        disabled: savingGroupId === group.id,
      },
    ],
    [
      {
        key: 'delete',
        label: deletingGroupId === group.id
          ? 'Deleting...'
          : group.can_delete
            ? 'Delete proxy group'
            : `Cannot delete · ${group.references.join(', ') || 'In use'}`,
        danger: true,
        disabled: deletingGroupId === group.id || !group.can_delete,
      },
    ],
  )
}

export function proxyGroupOptions(
  groups: readonly ProxyGroup[],
  selectedId = '',
) {
  const rows = groups.map((group) => ({
    label: `${group.enabled === false ? 'Disabled · ' : ''}${group.name || group.id}${Array.isArray(group.nodes) ? ` · ${group.nodes.length} nodes` : ''}`,
    value: group.id,
  }))
  if (selectedId && !rows.some((item) => item.value === selectedId)) {
    rows.unshift({ label: `Unknown proxy group · ${selectedId}`, value: selectedId })
  }
  return [
    { label: 'Select a proxy group', value: '' },
    ...rows,
  ]
}

export function buildProxyPreview(
  mode: FallbackProxyMode,
  selectedGroupId: string,
  customInput: string,
  groups: readonly Pick<ProxyGroup, 'id' | 'name'>[],
) {
  if (mode === 'off') return 'Off'
  if (mode === 'direct') return 'Direct'
  if (mode === 'group') {
    const group = groups.find((item) => item.id === selectedGroupId)
    return selectedGroupId ? `Proxy group: ${group?.name || selectedGroupId}` : 'Proxy group: not selected'
  }
  return customInput || 'Custom proxy: not set'
}

export function proxyNodeTestKey(group: Pick<ProxyGroup, 'id'>, node: Pick<ProxyNode, 'id'>) {
  return `group:${group.id}:${node.id}`
}

export function isProxyNodeTesting(group: Pick<ProxyGroup, 'id'>, node: Pick<ProxyNode, 'id'>, testingKey: string) {
  return testingKey === `group:${group.id}:all` || testingKey === proxyNodeTestKey(group, node)
}

export function proxyNodeTestSummary(
  group: Pick<ProxyGroup, 'id'>,
  node: ProxyNode,
  testResults: Readonly<Record<string, ProxyTestResult>>,
  testingKey: string,
) {
  if (isProxyNodeTesting(group, node, testingKey)) return 'Testing...'
  const result = testResults[proxyNodeTestKey(group, node)]
  if (result?.ok) return `HTTP ${result.status || '-'} · ${result.latency_ms || 0}ms`
  if (result && !result.ok) return result.error || 'Test failed'
  if (node.health.state === 'unhealthy') return node.health.error || 'Test failed'
  if (node.health.state === 'healthy') return `${node.health.latency_ms || 0}ms`
  return 'Not tested yet'
}

export function proxyNodeTestClass(
  group: Pick<ProxyGroup, 'id'>,
  node: ProxyNode,
  testResults: Readonly<Record<string, ProxyTestResult>>,
  testingKey: string,
) {
  if (isProxyNodeTesting(group, node, testingKey)) return 'text-sky-600'
  const result = testResults[proxyNodeTestKey(group, node)]
  if (result) return result.ok ? 'text-emerald-600' : 'text-rose-600'
  if (node.health.state === 'unhealthy') return 'text-rose-600'
  if (node.health.state === 'healthy') return 'text-emerald-600'
  return 'text-muted-foreground'
}
