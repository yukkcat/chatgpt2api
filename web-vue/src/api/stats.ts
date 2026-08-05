import apiClient from './client'
import type { DashboardResponse, DashboardTimeRangeKey } from '@/types/api'

const DASHBOARD_TIME_RANGES: DashboardTimeRangeKey[] = ['24h', '7d', '30d']
const DASHBOARD_VIEW_SCHEMA_VERSION = 3
type JsonObject = Record<string, unknown>

function contractError(path: string, expected: string): never {
  throw new Error(`Dashboard response contract mismatch at ${path}: expected ${expected}`)
}

function expectObject(value: unknown, path: string): JsonObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) contractError(path, 'object')
  return value as JsonObject
}

function expectString(value: unknown, path: string) {
  if (typeof value !== 'string') contractError(path, 'string')
}

function expectBoolean(value: unknown, path: string) {
  if (typeof value !== 'boolean') contractError(path, 'boolean')
}

function expectNumber(value: unknown, path: string, integer = false) {
  if (typeof value !== 'number' || !Number.isFinite(value) || (integer && !Number.isInteger(value))) {
    contractError(path, integer ? 'finite integer' : 'finite number')
  }
}

function expectNullableNumber(value: unknown, path: string) {
  if (value !== null) expectNumber(value, path)
}

function expectNumberArray(value: unknown, path: string, length: number, integer = false) {
  if (!Array.isArray(value) || value.length !== length) contractError(path, `number[${length}]`)
  value.forEach((item, index) => expectNumber(item, `${path}[${index}]`, integer))
}

function expectNullableNumberArray(value: unknown, path: string, length: number) {
  if (!Array.isArray(value) || value.length !== length) contractError(path, `(number | null)[${length}]`)
  value.forEach((item, index) => {
    if (item !== null) expectNumber(item, `${path}[${index}]`)
  })
}

function expectCountRecord(value: unknown, path: string) {
  const record = expectObject(value, path)
  Object.entries(record).forEach(([key, count]) => expectNumber(count, `${path}.${key}`, true))
}

function expectSeriesRecord(value: unknown, path: string, length: number, integer = false) {
  const record = expectObject(value, path)
  Object.entries(record).forEach(([key, series]) => expectNumberArray(series, `${path}.${key}`, length, integer))
}

function expectNullableSeriesRecord(value: unknown, path: string, length: number) {
  const record = expectObject(value, path)
  Object.entries(record).forEach(([key, series]) => {
    expectNullableNumberArray(series, `${path}.${key}`, length)
  })
}

function expectRangeKey(value: unknown, path: string): DashboardTimeRangeKey {
  if (value !== '24h' && value !== '7d' && value !== '30d') contractError(path, '24h | 7d | 30d')
  return value
}

function validateTotals(value: unknown, path: string) {
  const totals = expectObject(value, path)
  ;['total', 'success', 'failed', 'rate_limited', 'final_failed', 'text_review', 'measured'].forEach((field) => {
    expectNumber(totals[field], `${path}.${field}`, true)
  })
  expectNullableNumber(totals.success_rate, `${path}.success_rate`)
  ;['avg_success_duration_ms', 'p95_success_duration_ms'].forEach((field) => {
    expectNullableNumber(totals[field], `${path}.${field}`)
  })
}

function validateBuckets(value: unknown, path: string, expectedCount: number) {
  if (!Array.isArray(value) || value.length !== expectedCount) {
    contractError(path, `DashboardBucket[${expectedCount}]`)
  }
  value.forEach((item, index) => {
    const bucketPath = `${path}[${index}]`
    const bucket = expectObject(item, bucketPath)
    ;['label', 'start_at', 'end_at'].forEach((field) => expectString(bucket[field], `${bucketPath}.${field}`))
    ;[
      'total_calls', 'success_calls', 'final_failed_calls', 'switch_requests',
      'switch_count', 'switch_recovered',
    ].forEach((field) => expectNumber(bucket[field], `${bucketPath}.${field}`, true))
    ;[
      'success_rate', 'avg_success_duration_ms', 'p95_success_duration_ms',
      'switch_recovery_rate',
    ].forEach((field) => expectNullableNumber(bucket[field], `${bucketPath}.${field}`))
  })
}

function validateSwitching(value: unknown, path: string) {
  const switching = expectObject(value, path)
  ;['requests', 'count', 'recovered'].forEach((field) => expectNumber(switching[field], `${path}.${field}`, true))
  expectNullableNumber(switching.recovery_rate, `${path}.recovery_rate`)
}

function validateMetrics(value: unknown) {
  const metrics = expectObject(value, 'response.metrics')
  if (metrics.status !== 'ready' && metrics.status !== 'degraded') {
    contractError('response.metrics.status', 'ready | degraded')
  }
  expectBoolean(metrics.ready, 'response.metrics.ready')
  expectBoolean(metrics.stale, 'response.metrics.stale')
  expectString(metrics.source, 'response.metrics.source')
  ;['source_revision', 'last_ingested_at', 'checkpoint_at', 'failure_reason'].forEach((field) => {
    if (metrics[field] !== null) expectString(metrics[field], `response.metrics.${field}`)
  })
  if (metrics.freshness_ms !== null) expectNumber(metrics.freshness_ms, 'response.metrics.freshness_ms', true)
  expectNumber(metrics.retention_days, 'response.metrics.retention_days', true)
  if (metrics.ready === metrics.stale) contractError('response.metrics', 'ready and stale to be opposites')
  if ((metrics.status === 'ready') !== metrics.ready) contractError('response.metrics.status', 'consistent with ready')
}

function validateWindow(value: unknown, path: string, expectedRange: DashboardTimeRangeKey) {
  const window = expectObject(value, path)
  if (expectRangeKey(window.requested, `${path}.requested`) !== expectedRange) {
    contractError(`${path}.requested`, expectedRange)
  }
  expectString(window.start_at, `${path}.start_at`)
  expectString(window.end_at, `${path}.end_at`)
  const expectedBucketUnit = expectedRange === '24h' ? 'hour' : 'day'
  if (window.bucket_unit !== expectedBucketUnit) contractError(`${path}.bucket_unit`, expectedBucketUnit)
  const expectedBucketCount = expectedRange === '24h' ? 24 : expectedRange === '7d' ? 7 : 30
  expectNumber(window.bucket_count, `${path}.bucket_count`, true)
  if (window.bucket_count !== expectedBucketCount) contractError(`${path}.bucket_count`, String(expectedBucketCount))
}

function validateTrend(value: unknown, path: string) {
  const trend = expectObject(value, path)
  if (!Array.isArray(trend.labels)) contractError(`${path}.labels`, 'string[]')
  trend.labels.forEach((label, index) => expectString(label, `${path}.labels[${index}]`))
  const pointCount = trend.labels.length
  ;[
    'total_requests', 'success_requests', 'failed_requests', 'rate_limited_requests', 'final_failed_requests',
    'text_review_requests', 'measured_requests', 'switch_requests',
    'switch_count', 'switch_recovered',
  ].forEach((field) => expectNumberArray(trend[field], `${path}.${field}`, pointCount, true))
  expectNullableNumberArray(trend.success_rate, `${path}.success_rate`, pointCount)
  ;[
    'model_requests', 'model_success_requests', 'model_failed_requests',
    'model_rate_limited_requests', 'model_text_review_requests',
  ].forEach((field) => expectSeriesRecord(trend[field], `${path}.${field}`, pointCount, true))
  expectNullableSeriesRecord(
    trend.model_avg_success_duration_ms,
    `${path}.model_avg_success_duration_ms`,
    pointCount,
  )
  return pointCount
}

function validateModel(value: unknown, path: string, pointCount: number) {
  const model = expectObject(value, path)
  expectString(model.name, `${path}.name`)
  ;[
    'total_calls', 'success_calls', 'failed_calls', 'rate_limited_calls', 'final_failed_calls',
    'text_review_calls', 'measured_calls',
  ].forEach((field) => {
    expectNumber(model[field], `${path}.${field}`, true)
  })
  expectNullableNumber(model.success_rate, `${path}.success_rate`)
  if (model.avg_success_duration_ms !== null) {
    expectNumber(model.avg_success_duration_ms, `${path}.avg_success_duration_ms`)
  }
  if (model.p95_success_duration_ms !== null) {
    expectNumber(model.p95_success_duration_ms, `${path}.p95_success_duration_ms`)
  }
  ;[
    'call_series', 'success_series', 'failed_series', 'rate_limited_series', 'final_failed_series', 'text_review_series',
  ].forEach((field) => expectNumberArray(model[field], `${path}.${field}`, pointCount, true))
  expectNullableNumberArray(
    model.avg_success_duration_series_ms,
    `${path}.avg_success_duration_series_ms`,
    pointCount,
  )
}

function validateRange(value: unknown, path: string, expectedRange: DashboardTimeRangeKey) {
  const range = expectObject(value, path)
  if (expectRangeKey(range.time_range, `${path}.time_range`) !== expectedRange) {
    contractError(`${path}.time_range`, expectedRange)
  }
  const expectedBucketUnit = expectedRange === '24h' ? 'hour' : 'day'
  if (range.bucket_unit !== expectedBucketUnit) contractError(`${path}.bucket_unit`, expectedBucketUnit)
  validateWindow(range.window, `${path}.window`, expectedRange)
  validateTotals(range.totals, `${path}.totals`)
  validateSwitching(range.switching, `${path}.switching`)
  const pointCount = validateTrend(range.trend, `${path}.trend`)
  const expectedPointCount = expectedRange === '24h' ? 24 : expectedRange === '7d' ? 7 : 30
  if (pointCount !== expectedPointCount) contractError(`${path}.trend.labels`, `string[${expectedPointCount}]`)
  validateBuckets(range.buckets, `${path}.buckets`, expectedPointCount)
  if (!Array.isArray(range.models)) contractError(`${path}.models`, 'array')
  range.models.forEach((model, index) => validateModel(model, `${path}.models[${index}]`, pointCount))
}

function validateAccounts(value: unknown) {
  const accounts = expectObject(value, 'response.accounts')
  ;[
    'total', 'cumulative_total', 'active', 'limited', 'abnormal', 'disabled',
    'total_quota', 'unlimited_quota_count', 'unknown_quota_count', 'total_success', 'total_fail',
  ].forEach((field) => expectNumber(accounts[field], `response.accounts.${field}`, true))
  expectCountRecord(accounts.by_type, 'response.accounts.by_type')
  expectBoolean(accounts.healthy, 'response.accounts.healthy')
}

function validateStorage(value: unknown) {
  const storage = expectObject(value, 'response.storage')
  expectObject(storage.application_database, 'response.storage.application_database')
  const imageStorage = expectObject(storage.image_storage, 'response.storage.image_storage')
  expectBoolean(imageStorage.enabled, 'response.storage.image_storage.enabled')
  if (imageStorage.mode !== 'local' && imageStorage.mode !== 'webdav' && imageStorage.mode !== 'both') {
    contractError('response.storage.image_storage.mode', 'local | webdav | both')
  }
  if (imageStorage.status !== 'not_checked') {
    contractError('response.storage.image_storage.status', 'not_checked')
  }
  if (imageStorage.available !== null) {
    expectBoolean(imageStorage.available, 'response.storage.image_storage.available')
  }
  ;['image_count', 'image_size_bytes'].forEach((field) => {
    if (imageStorage[field] !== null) {
      expectNumber(imageStorage[field], `response.storage.image_storage.${field}`, true)
    }
  })
}

function parseDashboardResponse(value: unknown): DashboardResponse {
  const root = expectObject(value, 'response')
  if (root.status !== 'ok' && root.status !== 'degraded') contractError('response.status', 'ok | degraded')
  expectBoolean(root.healthy, 'response.healthy')
  expectString(root.version, 'response.version')

  const meta = expectObject(root.meta, 'response.meta')
  expectNumber(meta.schema_version, 'response.meta.schema_version', true)
  if (meta.schema_version !== DASHBOARD_VIEW_SCHEMA_VERSION) {
    contractError('response.meta.schema_version', String(DASHBOARD_VIEW_SCHEMA_VERSION))
  }
  expectString(meta.generated_at, 'response.meta.generated_at')
  expectNumber(meta.metrics_schema_version, 'response.meta.metrics_schema_version', true)
  expectRangeKey(meta.selected_range, 'response.meta.selected_range')
  if (!Array.isArray(meta.available_ranges)) contractError('response.meta.available_ranges', 'array')
  const availableRanges = meta.available_ranges.map((item, index) => (
    expectRangeKey(item, `response.meta.available_ranges[${index}]`)
  ))
  if (
    availableRanges.length !== DASHBOARD_TIME_RANGES.length ||
    DASHBOARD_TIME_RANGES.some((range) => !availableRanges.includes(range))
  ) {
    contractError('response.meta.available_ranges', '24h, 7d and 30d exactly once')
  }

  validateMetrics(root.metrics)
  validateAccounts(root.accounts)
  validateStorage(root.storage)
  const ranges = expectObject(root.ranges, 'response.ranges')
  DASHBOARD_TIME_RANGES.forEach((range) => validateRange(ranges[range], `response.ranges.${range}`, range))
  return value as DashboardResponse
}

export const statsApi = {
  async overview(signal?: AbortSignal): Promise<DashboardResponse> {
    const response = await apiClient.get<never, unknown>('/api/dashboard', { signal })
    return parseDashboardResponse(response)
  },
}
