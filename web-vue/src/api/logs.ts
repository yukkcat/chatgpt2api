import apiClient from './client'
import { formatRequestDuration } from '@/lib/requestDuration'
import type {
  CallPresentationStatus,
  PresentationTone,
  RequestDetailPresentation,
  TimelinePresentation,
} from './requestDetail'

export type {
  CallDetailField,
  CallPresentationStatus,
  PresentationTone,
  TimelineCategory,
  TimelinePresentation,
  TimelineTone,
} from './requestDetail'

export type CallBusiness =
  | 'account'
  | 'image_generation'
  | 'image_edit'
  | 'image_chat'
  | 'chat'
  | 'responses'
  | 'messages'
  | 'search'
  | 'file'
  | 'other'

export type CallOutcome =
  | 'success'
  | 'failed'
  | 'rate_limited'
  | 'text_review'
  | 'partial_success'
  | 'unknown'

export type AttemptResultStatus =
  | 'success'
  | 'failed'
  | 'generated_but_delivery_failed'

export type CallPresentation = {
  request: {
    kind: string
    primary: string
    secondary: string
  }
  execution: {
    primary: string
    secondary: string
  }
  status: CallPresentationStatus
  result: {
    text: string
    diagnostics: string
  }
  summary_text: string
  duration: {
    text: string
    breakdown: string
    tone: PresentationTone
  }
  is_failure: boolean
}

export type AttemptPresentation = {
  status: CallPresentationStatus
  failure_label: string
  marker_tone: 'success' | 'danger'
  switch_label: string
  error_code_text: string
  status_code_text: string
  show_failure: boolean
  show_error_details: boolean
  timeline: TimelinePresentation
}

export type AttemptGroupPresentation = {
  slot: number
  slot_label: string
  attempt_count: number
  attempt_text: string
  switch_count: number
  switch_text: string
  status: CallPresentationStatus
}

export type CallDetailPresentation = RequestDetailPresentation & {
  has_attempt_breakdown: boolean
  attempt_groups: AttemptGroupPresentation[]
}

export type AttemptSummary = {
  slot: number
  attempt: number
  account_email: string
  conversation_id: string
  status: string
  outcome: CallOutcome
  result_status: AttemptResultStatus
  duration_ms: number
  status_code: number
  error_code: string
  error_label: string
  public_error: string
  upstream_error: string
  upstream_text: string
  switched_account: boolean | null
  presentation: AttemptPresentation
  timings_ms: Record<string, number>
  monitor: Record<string, unknown>
}

export type CallSummary = {
  id: string
  time: string
  type: string
  summary: string
  business: CallBusiness
  outcome: CallOutcome
  display_status: string
  endpoint: string
  model: string
  started_at: string
  ended_at: string
  duration_ms: number
  key_id: string
  key_name: string
  role: string
  account_email: string
  conversation_id: string
  status_code: number
  error_code: string
  public_error: string
  image_requested_count: number
  image_succeeded_count: number
  image_failed_count: number
  image_result_status: string
  preview_image_url: string
  attempt_count: number
  switch_count: number
  recovered_after_switch: boolean
  presentation: CallPresentation
}

export type CallDetail = CallSummary & {
  request_text: string
  request_text_full: string
  request_text_truncated: boolean
  request_shape: Record<string, unknown>
  request_meta: Record<string, unknown>
  upstream_error: string
  upstream_text: string
  image_urls: string[]
  attempts: AttemptSummary[]
  timings_ms: Record<string, number>
  perf: Record<string, unknown>
  metrics: Record<string, unknown>
  monitor: Record<string, unknown>
  detail_presentation: CallDetailPresentation
  raw_detail: Record<string, unknown>
}

export type SystemLog = CallSummary & {
  detail?: Record<string, any>
}

export type SystemLogsListParams = {
  type?: string
  start_date?: string
  end_date?: string
  status?: string
  endpoint?: string
  model?: string
  account?: string
  conversation_id?: string
  search?: string
  limit?: number
  offset?: number
}

export type SystemLogsResponse = {
  items: CallSummary[]
  total: number
  limit: number
  offset: number
  has_more: boolean
  facets_scope: string
  stats_scope: string
  total_scope: string
  facets: {
    statuses: Record<string, number>
    endpoints: Record<string, number>
    models: Record<string, number>
    accounts: Record<string, number>
  }
  stats: {
    total: number
    success: number
    text_review: number
    failed: number
    limited: number
    image: number
  }
}

export type ImageAttempt = {
  slot: number
  attempt: number
  accountEmail: string
  publicError: string
  upstreamError: string
  upstreamText: string
  presentation: AttemptPresentation
  durationMs: number
}

export type SystemLogRow = {
  id: string
  raw: SystemLog
  time: string
  type: string
  summary: string
  business: CallBusiness
  outcome: CallOutcome
  endpoint: string
  model: string
  status: string
  keyId: string
  keyName: string
  role: string
  accountEmail: string
  conversationId: string
  durationMs: string
  startedAt: string
  endedAt: string
  requestText: string
  requestTextFull: string
  requestTextTruncated: boolean
  error: string
  rawUpstreamMessage: string
  rawUpstreamError: string
  urls: string[]
  imageUrls: string[]
  imageAttempts: ImageAttempt[]
  imageRequestedCount: number
  imageSucceededCount: number
  imageFailedCount: number
  attemptCount: number
  accountSwitchCount: number
  presentation: CallPresentation
  detailPresentation: CallDetailPresentation
  preview: string
  rawJson: string
}

export type NormalizeSystemLogRowOptions = {
  apiBaseUrl?: string
}

function cleanString(value: unknown): string {
  return String(value || '').trim()
}

function normalizePreviewUrl(url: string, apiBaseUrl = ''): string {
  const value = cleanString(url)
  if (!value || value.startsWith('file-service://')) return ''
  if (value.startsWith('/images/') || value.startsWith('/image-thumbnails/')) return value
  if (value.startsWith('images/') || value.startsWith('image-thumbnails/')) return `/${value}`
  if (/^https?:\/\//i.test(value)) {
    try {
      const parsed = new URL(value)
      if (parsed.pathname.startsWith('/images/') || parsed.pathname.startsWith('/image-thumbnails/')) {
        return `${parsed.pathname}${parsed.search}${parsed.hash}`
      }
    } catch {
      return value
    }
    return value
  }
  if (value.startsWith('/') && apiBaseUrl) return `${apiBaseUrl}${value}`
  return ''
}

function normalizePreviewUrls(urls: string[], apiBaseUrl = ''): string[] {
  return Array.from(new Set(urls.map((url) => normalizePreviewUrl(url, apiBaseUrl)).filter(Boolean)))
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return String(value ?? '')
  }
}

export function summarizeLogText(value: string, max = 220): string {
  const clean = value.replace(/\s+/g, ' ').trim()
  if (clean.length <= max) return clean
  return `${clean.slice(0, max - 1)}…`
}

export const formatLogDuration = formatRequestDuration

function rawRecord(value: unknown): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, any>
    : {}
}

export function normalizeSystemLogRow(item: CallSummary, index: number, options: NormalizeSystemLogRowOptions = {}): SystemLogRow {
  const previewImageUrl = cleanString(item.preview_image_url)
  const imageUrls = normalizePreviewUrls(previewImageUrl ? [previewImageUrl] : [], options.apiBaseUrl)
  const durationMs = cleanString(item.duration_ms)
  const summary = cleanString(item.summary)
  const error = cleanString(item.public_error)
  const imageRequestedCount = normalizeNonNegativeNumber(item.image_requested_count)
  const imageSucceededCount = normalizeNonNegativeNumber(item.image_succeeded_count)
  const imageFailedCount = normalizeNonNegativeNumber(item.image_failed_count)
  const attemptCount = normalizeNonNegativeNumber(item.attempt_count)
  const accountSwitchCount = normalizeNonNegativeNumber(item.switch_count)
  const time = cleanString(item.time)
  const raw = item as SystemLog

  return {
    id: cleanString(item.id) || `log-${index}`,
    raw,
    time,
    type: cleanString(item.type),
    summary,
    business: item.business,
    outcome: item.outcome,
    endpoint: cleanString(item.endpoint),
    model: cleanString(item.model),
    status: cleanString(item.display_status),
    keyId: cleanString(item.key_id),
    keyName: cleanString(item.key_name),
    role: cleanString(item.role),
    accountEmail: cleanString(item.account_email),
    conversationId: cleanString(item.conversation_id),
    durationMs,
    startedAt: cleanString(item.started_at),
    endedAt: cleanString(item.ended_at),
    requestText: '',
    requestTextFull: '',
    requestTextTruncated: false,
    error,
    rawUpstreamMessage: '',
    rawUpstreamError: '',
    urls: previewImageUrl ? [previewImageUrl] : [],
    imageUrls,
    imageAttempts: [],
    imageRequestedCount,
    imageSucceededCount,
    imageFailedCount,
    attemptCount,
    accountSwitchCount,
    presentation: item.presentation,
    detailPresentation: emptyDetailPresentation(),
    preview: summarizeLogText(summary || error),
    rawJson: '',
  }
}

export function normalizeSystemLogDetail(item: CallDetail, options: NormalizeSystemLogRowOptions = {}): SystemLogRow {
  const row = normalizeSystemLogRow(item, 0, options)
  const rawDetail = rawRecord(item.raw_detail)
  const attempts = normalizeImageAttempts(item.attempts)
  const sourceUrls = Array.isArray(item.image_urls) ? item.image_urls.map(cleanString).filter(Boolean) : []
  const imageUrls = normalizePreviewUrls(sourceUrls, options.apiBaseUrl)
  const detail: Record<string, any> = {
    ...rawDetail,
    call_id: item.id,
    endpoint: item.endpoint,
    model: item.model,
    status: item.display_status || item.outcome,
    key_id: item.key_id,
    key_name: item.key_name,
    role: item.role,
    account_email: item.account_email,
    conversation_id: item.conversation_id,
    started_at: item.started_at,
    ended_at: item.ended_at,
    duration_ms: item.duration_ms,
    status_code: item.status_code,
    error_code: item.error_code,
    public_error: item.public_error,
    error: item.public_error,
    request_text: item.request_text,
    request_text_full: item.request_text_full,
    request_text_truncated: item.request_text_truncated,
    request_shape: item.request_shape,
    request_meta: item.request_meta,
    upstream_error: item.upstream_error,
    raw_upstream_message: item.upstream_text,
    image_urls: sourceUrls,
    image_attempts: item.attempts,
    image_requested_count: item.image_requested_count,
    image_succeeded_count: item.image_succeeded_count,
    image_failed_count: item.image_failed_count,
    image_result_status: item.image_result_status,
    timings_ms: item.timings_ms,
    perf: item.perf,
    metrics: item.metrics,
    monitor: item.monitor,
  }
  return {
    ...row,
    raw: { ...item, detail },
    requestText: cleanString(item.request_text),
    requestTextFull: cleanString(item.request_text_full) || cleanString(item.request_text),
    requestTextTruncated: item.request_text_truncated === true,
    rawUpstreamMessage: cleanString(item.upstream_text),
    rawUpstreamError: cleanString(item.upstream_error),
    urls: sourceUrls,
    imageUrls,
    imageAttempts: attempts,
    detailPresentation: item.detail_presentation,
    rawJson: prettyJson(rawDetail),
  }
}

function emptyDetailPresentation(): CallDetailPresentation {
  return {
    primary_fields: [],
    diagnostic_fields: [],
    has_attempt_breakdown: false,
    auto_expand_timeline: false,
    attempt_groups: [],
    timeline: emptyTimelinePresentation(),
  }
}

function emptyTimelinePresentation(): TimelinePresentation {
  return {
    segments: [],
    legend_items: [],
    groups: [],
  }
}

function normalizeSystemParams(params?: SystemLogsListParams) {
  const limit = Number(params?.limit || 500)
  const offset = Number(params?.offset || 0)
  return {
    type: cleanString(params?.type),
    start_date: cleanString(params?.start_date),
    end_date: cleanString(params?.end_date),
    status: cleanString(params?.status),
    endpoint: cleanString(params?.endpoint),
    model: cleanString(params?.model),
    account: cleanString(params?.account),
    conversation_id: cleanString(params?.conversation_id),
    search: cleanString(params?.search),
    limit: Number.isFinite(limit) ? Math.min(Math.max(Math.trunc(limit), 1), 20000) : 500,
    offset: Number.isFinite(offset) ? Math.max(Math.trunc(offset), 0) : 0,
  }
}

function normalizeNonNegativeNumber(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed) : 0
}

function normalizeImageAttempts(value: AttemptSummary[]): ImageAttempt[] {
  return value
    .map((item) => ({
      slot: Math.max(1, normalizeNonNegativeNumber(item.slot)),
      attempt: Math.max(1, normalizeNonNegativeNumber(item.attempt)),
      accountEmail: cleanString(item.account_email),
      publicError: cleanString(item.public_error),
      upstreamError: cleanString(item.upstream_error),
      upstreamText: cleanString(item.upstream_text),
      presentation: item.presentation,
      durationMs: normalizeNonNegativeNumber(item.duration_ms),
    }))
    .sort((left, right) => left.slot - right.slot || left.attempt - right.attempt)
}

export const logsApi = {
  listSystem: async (params?: SystemLogsListParams) => {
    return apiClient.get<never, SystemLogsResponse>('/api/logs', {
      params: normalizeSystemParams(params),
    })
  },

  get: async (id: string) =>
    apiClient.get<never, CallDetail>(`/api/logs/${encodeURIComponent(id)}`),

  delete: async (ids: string[]) =>
    apiClient.post<{ ids: string[] }, { removed: number }>('/api/logs/delete', { ids }),
}
