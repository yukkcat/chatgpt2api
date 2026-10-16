import type { GalleryFile } from '@/api/gallery'
import type {
  PresentationTone,
  SystemLogsResponse,
  SystemLogRow,
} from '@/api/logs'

export type LogFilterOption = { label: string; value: string }
export type LogGroupedSelectOption = LogFilterOption & { disabled?: boolean }
export type LogGroupedSelectGroup = {
  label?: string
  options: LogGroupedSelectOption[]
}

export type SystemLogFilters = {
  search: string
  startDate: string
  endDate: string
  status: string
  endpoint: string
  model: string
  account: string
  conversationId: string
  type: string
}

export type AdvancedLogFilterKey = 'type' | 'status' | 'model' | 'account'

export type LogMetricItem = {
  label: string
  value: string | number
  class: string
}

export type LogStatusTone = PresentationTone

type AdvancedConditionGroup = {
  key: AdvancedLogFilterKey
  label: string
  options: LogFilterOption[]
}

export type LogPreviewImage = {
  url: string
  title?: string
  filename?: string
  alt?: string
  broken?: boolean
}

export type SystemLogRowSignatureInput = {
  selected: boolean
  firstImageBroken: boolean
}

type LogDurationDisplay = {
  total: string
  breakdown: string
}

export type LogCellDisplay = {
  primary: string
  secondary: string
}

export type LogRequestDisplay = LogCellDisplay & {
  kind: string
  parameters?: string
}

export const typeOptions = [
  { label: 'Call logs', value: 'call' },
  { label: 'Account logs', value: 'account' },
  { label: 'All types', value: '' },
]

export const systemLogPageSizeOptions = [20, 50, 100, 200, 500]

export const statusOptions = [
  { label: 'All statuses', value: '' },
  { label: 'Success', value: 'success' },
  { label: 'Failed', value: 'failed' },
  { label: 'Rate limited / restricted', value: 'limited' },
]

export const systemQuickFilterOptions: LogGroupedSelectOption[] = [
  { label: 'Failures only', value: 'quick:status:failed' },
  { label: 'Image edits', value: 'quick:endpoint:/v1/images/edits' },
  { label: 'Image generation', value: 'quick:endpoint:/v1/images/generations' },
]

export const quickEndpointValues = ['/v1/images/edits', '/v1/images/generations'] as const

export const systemQuickFilterGroups: LogGroupedSelectGroup[] = [
  { options: systemQuickFilterOptions },
]

export function cleanLogString(value: unknown): string {
  if (value === undefined || value === null) return ''
  return String(value).trim()
}

function signatureValue(value: unknown): string {
  return cleanLogString(value).replaceAll('|', '/')
}

function boundedSignatureText(value: unknown, limit = 180): string {
  const text = signatureValue(value)
  if (text.length <= limit) return text
  return `${text.length}:${text.slice(0, limit)}:${text.slice(-24)}`
}

export function optionFromFacet(facet: Record<string, number>, allLabel: string): LogFilterOption[] {
  return [
    { label: allLabel, value: '' },
    ...Object.keys(facet)
      .map(cleanLogString)
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b))
      .map((value) => ({ label: `${value} (${facet[value] || 0})`, value })),
  ]
}

export function buildAdvancedConditionMenuGroups(
  modelFacet: Record<string, number>,
  accountFacet: Record<string, number>,
): LogGroupedSelectGroup[] {
  const groups: AdvancedConditionGroup[] = [
    {
      key: 'type',
      label: 'Type',
      options: [
        { label: 'Call logs', value: 'call' },
        { label: 'Account logs', value: 'account' },
        { label: 'All types', value: '' },
      ],
    },
    {
      key: 'status',
      label: 'Status',
      options: statusOptions,
    },
    {
      key: 'model',
      label: 'Model',
      options: optionFromFacet(modelFacet, 'All models'),
    },
    {
      key: 'account',
      label: 'Account',
      options: optionFromFacet(accountFacet, 'All accounts'),
    },
  ]

  return groups.map((group) => ({
    label: group.label,
    options: group.options.map((option) => ({
      label: option.label,
      value: advancedConditionOptionValue(group.key, option.value),
    })),
  }))
}

export function requestDisplay(item: SystemLogRow): LogRequestDisplay {
  return item.presentation.request
}

export function executionDisplay(item: SystemLogRow): LogCellDisplay {
  return item.presentation.execution
}

export function outcomeText(item: SystemLogRow): string {
  return item.presentation.result.text
}

export function resultDiagnostics(item: SystemLogRow): string {
  return item.presentation.result.diagnostics
}

export function summaryText(item: SystemLogRow): string {
  return item.presentation.summary_text
}

export function statusLabel(item: SystemLogRow): string {
  return item.presentation.status.label
}

export function statusTone(item: SystemLogRow): LogStatusTone {
  return item.presentation.status.tone
}

export function logDurationDisplay(item: SystemLogRow): LogDurationDisplay {
  return {
    total: item.presentation.duration.text,
    breakdown: item.presentation.duration.breakdown,
  }
}

export function logDurationTone(item: SystemLogRow): LogStatusTone {
  return item.presentation.duration.tone
}

export function systemLogRowSignature(item: SystemLogRow, input: SystemLogRowSignatureInput): string {
  const durationDisplay = logDurationDisplay(item)
  const request = requestDisplay(item)
  const execution = executionDisplay(item)
  return [
    item.id,
    input.selected ? 1 : 0,
    input.firstImageBroken ? 1 : 0,
    boundedSignatureText(item.time),
    boundedSignatureText(request.primary, 96),
    boundedSignatureText(request.kind, 64),
    boundedSignatureText(request.secondary, 128),
    boundedSignatureText(request.parameters, 160),
    boundedSignatureText(item.presentation.result.resolution, 160),
    boundedSignatureText(execution.primary, 96),
    boundedSignatureText(execution.secondary, 96),
    boundedSignatureText(durationDisplay.total, 64),
    boundedSignatureText(durationDisplay.breakdown, 160),
    boundedSignatureText(statusLabel(item), 64),
    statusTone(item),
    boundedSignatureText(outcomeText(item)),
    boundedSignatureText(resultDiagnostics(item), 160),
    item.imageRequestedCount,
    item.imageSucceededCount,
    item.imageUrls.length,
    item.attemptCount,
    item.accountSwitchCount,
    item.imageUrls.slice(0, 4).map((url) => boundedSignatureText(url, 96)).join(','),
    boundedSignatureText(item.preview),
    item.presentation.is_failure ? 1 : 0,
  ].map(signatureValue).join('|')
}

export function filenameFromUrl(url: string): string {
  const value = cleanLogString(url)
  if (!value) return '-'
  try {
    const parsed = new URL(value, 'https://local.invalid')
    return decodeURIComponent(parsed.pathname.split('/').pop() || value)
  } catch {
    return decodeURIComponent(value.split(/[/?#]/)[0]?.split('/').pop() || value)
  }
}

export function buildLogPreviewImages(
  item: SystemLogRow | null | undefined,
  isPreviewBroken: (url: string) => boolean,
): LogPreviewImage[] {
  if (!item) return []
  return item.imageUrls.map((url, index) => {
    const sourceUrl = item.urls[index] || url
    return {
      url,
      title: sourceUrl,
      filename: filenameFromUrl(sourceUrl),
      alt: `Log result image ${index + 1}`,
      broken: isPreviewBroken(url),
    }
  })
}

export function buildLogPreviewGalleryFile(image: LogPreviewImage | null | undefined): GalleryFile | null {
  if (!image) return null
  const filename = image.filename || filenameFromUrl(image.title || image.url) || 'log-preview-image'
  return {
    id: image.title || image.url,
    filename,
    path: image.title || image.url,
    url: image.url,
    thumbnail_url: image.url,
    size_bytes: 0,
    created_at: '',
    date: '',
    media_type: 'image',
    expired: false,
    expires_at: null,
    expires_in_seconds: null,
    tags: [],
    storage: 'log',
    local: false,
    webdav: false,
    available: true,
    width: null,
    height: null,
    genbox_push: null,
  }
}

export function systemMetricItems(logMeta: Pick<SystemLogsResponse, 'stats' | 'stats_scope'>): LogMetricItem[] {
  const stats = logMeta.stats
  const pageScope = logMeta.stats_scope === 'page'
  return [
    { label: pageScope ? 'Page total' : 'Total', value: stats.total, class: 'text-foreground' },
    { label: pageScope ? 'Page successes' : 'Success', value: stats.success, class: 'text-emerald-600' },
    { label: pageScope ? 'Page text' : 'Text', value: stats.text_review, class: 'text-violet-600' },
    { label: pageScope ? 'Page failures' : 'Failed', value: stats.failed, class: 'text-rose-600' },
    { label: pageScope ? 'Page rate limits' : 'Rate limited', value: stats.limited, class: 'text-amber-600' },
    { label: pageScope ? 'Page images' : 'Image endpoint', value: stats.image, class: 'text-cyan-600' },
  ]
}

export function activeSystemFilterCount(filters: SystemLogFilters): number {
  return [
    filters.search,
    filters.startDate,
    filters.endDate,
    filters.status,
    filters.endpoint,
    filters.model,
    filters.account,
    filters.conversationId,
    filters.type !== 'call' ? filters.type || 'all' : '',
  ].filter(Boolean).length
}

export function advancedConditionCount(filters: Pick<SystemLogFilters, 'type' | 'status' | 'model' | 'account'>): number {
  return [
    filters.type !== 'call' ? filters.type || 'all' : '',
    filters.status,
    filters.model,
    filters.account,
  ].filter(Boolean).length
}

export function advancedConditionOptionValue(key: AdvancedLogFilterKey, value: string): string {
  return `advanced:${key}:${encodeURIComponent(value)}`
}

export function parseAdvancedConditionOptionValue(key: string): { conditionKey: AdvancedLogFilterKey; value: string } | null {
  const match = key.match(/^advanced:(type|status|model|account):(.*)$/)
  if (!match) return null
  return {
    conditionKey: match[1] as AdvancedLogFilterKey,
    value: decodeURIComponent(match[2] || ''),
  }
}

export function latestAdvancedConditionValue(values: readonly string[], key: AdvancedLogFilterKey): string | null {
  const matched = values
    .map(parseAdvancedConditionOptionValue)
    .filter((item): item is { conditionKey: AdvancedLogFilterKey; value: string } => Boolean(item && item.conditionKey === key))
  if (matched.length === 0) return null
  return matched[matched.length - 1].value
}

export function buildAdvancedConditionSelection(filters: Pick<SystemLogFilters, 'type' | 'status' | 'model' | 'account'>): string[] {
  const values: string[] = []
  if (filters.type !== 'call') values.push(advancedConditionOptionValue('type', filters.type))
  if (filters.status) values.push(advancedConditionOptionValue('status', filters.status))
  if (filters.model) values.push(advancedConditionOptionValue('model', filters.model))
  if (filters.account) values.push(advancedConditionOptionValue('account', filters.account))
  return values
}

export function buildSystemQuickFilterSelection(filters: Pick<SystemLogFilters, 'status' | 'endpoint'>): string[] {
  const values: string[] = []
  if (filters.status === 'failed') values.push('quick:status:failed')
  if (filters.endpoint === '/v1/images/edits') values.push('quick:endpoint:/v1/images/edits')
  if (filters.endpoint === '/v1/images/generations') values.push('quick:endpoint:/v1/images/generations')
  return values
}

export function latestQuickEndpointValue(values: readonly string[]): string | null {
  const matched = values
    .filter((item) => item.startsWith('quick:endpoint:'))
    .map((item) => item.slice('quick:endpoint:'.length))
  return matched.length ? matched[matched.length - 1] : null
}

export function isQuickEndpointValue(value: string): boolean {
  return (quickEndpointValues as readonly string[]).includes(value)
}
