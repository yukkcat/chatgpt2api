import { apiClient } from './client'

export type PromptImageMode = '' | 'generate' | 'edit'
export type PromptSourceSyncState = 'disabled' | 'pending' | 'synced' | 'cached' | 'failed'
export type PromptSourceSyncTone = 'muted' | 'success' | 'warning' | 'danger'

export interface PromptLibraryItem {
  id: string
  source_id: string
  source_name: string
  title: string
  prompt: string
  description: string
  preview: string
  link: string
  author: string
  category: string
  sub_category: string
  tags: string[]
  reference_image_urls: string[]
  image_mode: PromptImageMode
  image_model: string
  image_size: string
  image_count: number | null
  created_at: string
}

export interface PromptSource {
  id: string
  name: string
  url: string
  homepage: string
  enabled: boolean
  built_in: boolean
  sort_order: number
  prompt_count: number
  cached: boolean
  sync_state: PromptSourceSyncState
  sync_label: string
  sync_message: string
  sync_tone: PromptSourceSyncTone
  last_sync_at: string
  last_error: string
  last_fetch_ms: number | null
}

export interface PromptSourceError {
  id: string
  name: string
  error: string
}

export type PromptSourceSyncSummaryStatus = 'success' | 'partial' | 'failed'
export type PromptSourceSyncSummaryTone = 'success' | 'warning' | 'danger'

export interface PromptSourceSyncSummary {
  status: PromptSourceSyncSummaryStatus
  tone: PromptSourceSyncSummaryTone
  total: number
  succeeded: number
  failed: number
  message: string
}

export interface PromptLibraryView {
  schema_version: 1
  generated_at: string
  revision: string
  registry_revision: string
  registry_generated_at: string
  synced: boolean
  prompt_count: number
  source_count: number
  enabled_source_count: number
  cached_source_count: number
  source_error_count: number
  sync_summary: PromptSourceSyncSummary
  source_errors: PromptSourceError[]
  items: PromptLibraryItem[]
  sources: PromptSource[]
}

export interface PromptSourcePayload {
  enabled?: boolean
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 0
}

const PROMPT_SOURCE_SYNC_STATES = new Set<PromptSourceSyncState>([
  'disabled',
  'pending',
  'synced',
  'cached',
  'failed',
])
const PROMPT_SOURCE_SYNC_TONES = new Set<PromptSourceSyncTone>([
  'muted',
  'success',
  'warning',
  'danger',
])
const PROMPT_SOURCE_SYNC_SUMMARY_STATUSES = new Set<PromptSourceSyncSummaryStatus>([
  'success',
  'partial',
  'failed',
])
const PROMPT_SOURCE_SYNC_SUMMARY_TONES = new Set<PromptSourceSyncSummaryTone>([
  'success',
  'warning',
  'danger',
])

function validatePromptLibraryView(value: unknown): PromptLibraryView {
  if (!isRecord(value) || value.schema_version !== 1) {
    throw new Error('提示词库响应版本不受支持，请确认前后端版本一致。')
  }
  if (typeof value.revision !== 'string' || !value.revision) {
    throw new Error('提示词库响应缺少 revision。')
  }
  if (!Array.isArray(value.items) || !Array.isArray(value.sources) || !Array.isArray(value.source_errors)) {
    throw new Error('提示词库响应缺少 items、sources 或 source_errors。')
  }

  const counts: Array<[unknown, number, string]> = [
    [value.prompt_count, value.items.length, 'prompt_count'],
    [value.source_count, value.sources.length, 'source_count'],
    [value.source_error_count, value.source_errors.length, 'source_error_count'],
  ]
  for (const [actual, expected, field] of counts) {
    if (!isNonNegativeInteger(actual) || actual !== expected) {
      throw new Error(`提示词库响应中的 ${field} 与列表不一致。`)
    }
  }
  if (!isNonNegativeInteger(value.enabled_source_count) || !isNonNegativeInteger(value.cached_source_count)) {
    throw new Error('提示词库响应中的词源计数无效。')
  }
  if (
    !isRecord(value.sync_summary)
    || !PROMPT_SOURCE_SYNC_SUMMARY_STATUSES.has(value.sync_summary.status as PromptSourceSyncSummaryStatus)
    || !PROMPT_SOURCE_SYNC_SUMMARY_TONES.has(value.sync_summary.tone as PromptSourceSyncSummaryTone)
    || !isNonNegativeInteger(value.sync_summary.total)
    || !isNonNegativeInteger(value.sync_summary.succeeded)
    || !isNonNegativeInteger(value.sync_summary.failed)
    || value.sync_summary.total !== value.enabled_source_count
    || value.sync_summary.failed !== value.source_error_count
    || value.sync_summary.succeeded + value.sync_summary.failed !== value.sync_summary.total
    || typeof value.sync_summary.message !== 'string'
    || !value.sync_summary.message.trim()
  ) {
    throw new Error('提示词库响应中的同步摘要无效。')
  }
  if (!value.items.every((item) => isRecord(item) && typeof item.id === 'string' && typeof item.prompt === 'string')) {
    throw new Error('提示词库响应包含无效提示词。')
  }
  if (!value.sources.every((source) => (
    isRecord(source)
    && typeof source.id === 'string'
    && typeof source.enabled === 'boolean'
    && PROMPT_SOURCE_SYNC_STATES.has(source.sync_state as PromptSourceSyncState)
    && typeof source.sync_label === 'string'
    && typeof source.sync_message === 'string'
    && PROMPT_SOURCE_SYNC_TONES.has(source.sync_tone as PromptSourceSyncTone)
  ))) {
    throw new Error('提示词库响应包含无效词源。')
  }
  return value as unknown as PromptLibraryView
}

async function promptViewRequest(request: Promise<unknown>) {
  return validatePromptLibraryView(await request)
}

export const promptsApi = {
  list: () => promptViewRequest(apiClient.get<never, unknown>('/api/prompts')),
  updateSource: (id: string, payload: PromptSourcePayload) => promptViewRequest(
    apiClient.post<PromptSourcePayload, unknown>(`/api/admin/prompt-sources/${encodeURIComponent(id)}`, payload),
  ),
  refreshSource: (id: string) => promptViewRequest(
    apiClient.post<never, unknown>(`/api/admin/prompt-sources/${encodeURIComponent(id)}/refresh`),
  ),
  refreshSources: () => promptViewRequest(
    apiClient.post<never, unknown>('/api/admin/prompt-sources/refresh'),
  ),
}
