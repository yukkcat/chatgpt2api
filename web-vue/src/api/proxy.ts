import apiClient from './client'
import type { ClearanceTestResult, ProxyRuntimeSettings, ProxyRuntimeStatus } from '@/types/api'

export interface ProxyTestResult {
  ok: boolean
  status: number
  latency_ms: number
  error?: string | null
  proxy_source?: string
  has_proxy?: boolean
}

export interface ProxyHealth {
  state: 'unknown' | 'healthy' | 'unhealthy'
  checked_at: string | null
  latency_ms: number | null
  error: string | null
}

export interface ProxyNode {
  id: string
  name: string
  url: string
  enabled: boolean
  image_concurrency_limit: number
  notes: string
  health: ProxyHealth
}

export interface ProxyGroup {
  id: string
  name: string
  strategy: 'request_random' | 'time_window' | 'round_robin'
  rotation_interval_minutes: number
  enabled: boolean
  notes: string
  nodes: ProxyNode[]
  reference_text: string
  health: ProxyHealth
  can_delete: boolean
  references: string[]
}

export interface ProxyNodePayload {
  id?: string
  name?: string
  url?: string
  enabled?: boolean
  image_concurrency_limit?: number | string | null
  notes?: string
}

export type ProxyGroupPayload = {
  id?: string
  name?: string
  strategy?: ProxyGroup['strategy']
  rotation_interval_minutes?: number
  enabled?: boolean
  notes?: string
  nodes?: ProxyNodePayload[]
  create_only?: boolean
}

export type LegacyProxyReferenceMode = 'global' | 'direct' | 'profile' | 'group' | 'custom'

export interface ProxyReference {
  mode: 'direct' | 'group' | 'custom'
  group_id: string
  url: string
}

export interface ProxyEffectiveReference {
  source: 'disabled' | 'direct' | 'group' | 'custom' | 'profile'
  label: string
  configured: boolean
  available: boolean
  has_proxy: boolean
  group_id: string
}

export interface ProxyView {
  schema_version: number
  generated_at: string
  revision: string
  default_reference: ProxyReference
  fallback_reference: ProxyReference | null
  effective_default: ProxyEffectiveReference
  effective_fallback: ProxyEffectiveReference
  groups: ProxyGroup[]
}

export type ProxyTestStatus = 'success' | 'partial' | 'failed'
export type ProxyTestTone = 'success' | 'warning' | 'danger'

export interface ProxyTestSummary {
  status: ProxyTestStatus
  tone: ProxyTestTone
  total: number
  succeeded: number
  failed: number
  max_latency_ms: number
  label: string
  message: string
}

export interface ProxyGroupTestResponse {
  summary: ProxyTestSummary
  results: Array<{ node_id: string; result: ProxyTestResult }>
  result: ProxyTestResult | null
}

export interface ProxyNodeImportNode {
  url: string
  image_concurrency_limit: number
}

export interface ProxyNodeImportInvalidItem {
  line: number
  raw: string
  reason: string
}

export interface ProxyNodeImportResult {
  nodes: ProxyNodeImportNode[]
  added_count: number
  duplicate_count: number
  invalid_count: number
  invalid_items: ProxyNodeImportInvalidItem[]
}

export type { ClearanceTestResult, ProxyRuntimeSettings, ProxyRuntimeStatus }

export function serializeProxyReference(mode: LegacyProxyReferenceMode, value = ''): string {
  const raw = String(value || '').trim()
  if (mode === 'global') return ''
  if (mode === 'direct') return 'direct'
  if (mode === 'profile') return raw ? `profile:${raw}` : ''
  if (mode === 'group') return raw ? `group:${raw}` : ''
  return raw
}

export const proxyApi = {
  test: (url: string) =>
    apiClient.post<{ url: string }, { result: ProxyTestResult }>('/api/proxy/test', { url }),

  getView: () =>
    apiClient.get<never, ProxyView>('/api/proxy/view'),

  saveDefaults: (payload: { default_reference: ProxyReference; fallback_reference: ProxyReference | null }) =>
    apiClient.post<typeof payload, {
      default_reference: ProxyReference
      fallback_reference: ProxyReference | null
      effective_default: ProxyEffectiveReference
      effective_fallback: ProxyEffectiveReference
      revision: string
    }>('/api/proxy/defaults', payload),

  saveGroup: (payload: ProxyGroupPayload) =>
    apiClient.post<ProxyGroupPayload, { group: ProxyGroup; revision: string }>(
      '/api/proxy/groups',
      payload,
    ),

  deleteGroup: (id: string) =>
    apiClient.delete<never, { deleted_id: string; revision: string }>(
      `/api/proxy/groups/${encodeURIComponent(id)}`,
    ),

  testGroup: (payload: { id?: string; node_id?: string; url?: string }) =>
    apiClient.post<
      { id?: string; node_id?: string; url?: string },
      ProxyGroupTestResponse
    >('/api/proxy/groups/test', payload),

  getRuntime: () =>
    apiClient.get<never, { runtime: ProxyRuntimeSettings; status: ProxyRuntimeStatus }>('/api/proxy/runtime'),

  testClearance: (targetUrl = 'https://chatgpt.com') =>
    apiClient.post<{ target_url: string }, { result: ClearanceTestResult }>(
      '/api/proxy/clearance/test',
      { target_url: targetUrl },
    ),

  importNodes: (payload: { text: string; existing_urls?: string[] }) =>
    apiClient.post<typeof payload, ProxyNodeImportResult>(
      '/api/proxy/nodes/import',
      payload,
    ),
}
