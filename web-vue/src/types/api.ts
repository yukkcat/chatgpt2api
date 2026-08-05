// API 类型定义

export type ProxyRuntimeClearanceMode = 'none' | 'manual' | 'flaresolverr'

export interface SettingsProxyRuntimeClearance {
  enabled: boolean
  mode: ProxyRuntimeClearanceMode
  cf_cookies: string
  cf_clearance: string
  has_cf_cookies: boolean
  has_cf_clearance: boolean
  user_agent: string
  flaresolverr_url: string
  timeout_sec: number
  refresh_interval: number
  warm_up_on_start: boolean
}

export interface SettingsProxyRuntimeSettings {
  enabled: boolean
  resource_proxy_url: string
  skip_ssl_verify: boolean
  clearance: SettingsProxyRuntimeClearance
}

export interface ProxyRuntimeClearance extends SettingsProxyRuntimeClearance {
  browser: string
}

export interface ProxyRuntimeSettings extends SettingsProxyRuntimeSettings {
  reset_session_status_codes: number[]
  clearance: ProxyRuntimeClearance
}

export interface ProxyRuntimeStatus {
  enabled: boolean
  proxy_source?: string
  has_proxy: boolean
  skip_ssl_verify?: boolean
  clearance_enabled: boolean
  clearance_mode: string
  has_clearance_bundle: boolean
  cached_clearance_hosts: string[]
}

export interface ClearanceTestResult {
  ok: boolean
  status: string
  latency_ms: number
  has_cookies: boolean
  user_agent: string
  error?: string | null
  runtime?: ProxyRuntimeStatus
}

export interface Settings {
  proxy_runtime: SettingsProxyRuntimeSettings
  base_url: string
  refresh_account_interval_minute: number
  image_retention_days: number
  log_retention_days: number
  image_poll_timeout_secs: number
  image_stream_timeout_secs: number
  image_account_concurrency: number
  account_processing_concurrency: number
  image_account_retry_enabled: boolean
  image_upscale_enabled: boolean
  image_upscale_engine: 'sharp_lanczos3' | 'pillow_lanczos'
  image_max_account_attempts: number
  image_remove_conversation_after_result: boolean
  image_settle_enabled: boolean
  image_settle_secs: number
  auto_remove_invalid_accounts: boolean
  auto_remove_rate_limited_accounts: boolean
  log_levels: string[]
  global_system_prompt: string
  sensitive_words: string[]
  ai_review: {
    enabled: boolean
    base_url: string
    api_key: string
    has_api_key: boolean
    model: string
    prompt: string
  }
  image_storage: {
    enabled: boolean
    mode: 'local' | 'webdav' | 'both'
    webdav_url: string
    webdav_username: string
    webdav_password: string
    has_webdav_password: boolean
    webdav_root_path: string
    public_base_url: string
  }
  backup: {
    enabled: boolean
    provider: string
    account_id: string
    access_key_id: string
    secret_access_key: string
    has_secret_access_key: boolean
    bucket: string
    prefix: string
    interval_minutes: number
    rotation_keep: number
    encrypt: boolean
    passphrase: string
    has_passphrase: boolean
    include: Record<string, boolean>
  }
  third_party_apps: {
    infinite_canvas: {
      enabled: boolean
      url: string
    }
  }
}

export interface SettingsFieldMetadata {
  source: 'default' | 'configured' | 'environment'
  default?: unknown
  min?: number | null
  max?: number | null
  options: string[]
  unit?: string | null
  read_only: boolean
  restart_required: boolean
  sensitive: boolean
}

export interface SettingsView {
  schema_version: number
  generated_at: string
  revision: string
  settings: Settings
  fields: Record<string, SettingsFieldMetadata>
}

export interface SettingsMutationResult extends SettingsView {
  changed_fields: string[]
  restart_required: boolean
}

export interface LogEntry {
  time: string
  level: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | 'DEBUG'
  message: string
  row_id?: string
  req_id?: string
  tags?: string[]
  account_id?: string
  text?: string
  layer?: 'system' | 'chat' | 'reverse' | 'other'
  lane?: string
  model?: string
  kind?: string
  stage?: string
  served_label?: string
}

export interface AdminLogGroup {
  id: string
  row_ids: string[]
  status: 'success' | 'error' | 'timeout' | 'in_progress'
  account_id: string
  model: string
  lane: string
  terminal_kind: string
  started_at: string
  ended_at: string
  user_preview: string
  assistant_preview: string
  count: number
}

export interface LogsResponse {
  total: number
  limit: number
  logs: LogEntry[]
}

export interface AdminLogStats {
  memory: {
    total: number
    by_level: Record<string, number>
    capacity: number
  }
  active?: {
    source: 'file' | 'memory'
    total: number
  }
  errors: {
    count: number
    recent: LogEntry[]
  }
  chat_count: number
}

export interface AdminLogsResponse extends LogsResponse {
  filters?: {
    level?: string | null
    search?: string | null
    start_time?: string | null
    end_time?: string | null
  }
  groups?: AdminLogGroup[]
  stats: AdminLogStats
}

export interface VersionInfoResponse {
  version: string
  tag: string
  commit: string
}

export interface VersionCheckResponse extends VersionInfoResponse {
  repository: string
  latest_tag: string
  latest_version: string
  release_url: string
  is_latest: boolean
  update_available: boolean
  check_error?: string
}

export type DashboardTimeRangeKey = '24h' | '7d' | '30d'

export interface DashboardMeta {
  schema_version: number
  generated_at: string
  metrics_schema_version: number
  selected_range: DashboardTimeRangeKey
  available_ranges: DashboardTimeRangeKey[]
}

export interface DashboardMetrics {
  status: 'ready' | 'degraded'
  ready: boolean
  stale: boolean
  source: string
  source_revision: string | null
  last_ingested_at: string | null
  freshness_ms: number | null
  checkpoint_at: string | null
  failure_reason: string | null
  retention_days: number
}

export interface DashboardAccountStats {
  total: number
  cumulative_total: number
  active: number
  limited: number
  abnormal: number
  disabled: number
  total_quota: number
  unlimited_quota_count: number
  unknown_quota_count: number
  total_success: number
  total_fail: number
  by_type: Record<string, number>
  healthy: boolean
}

export interface DashboardTotals {
  total: number
  success: number
  failed: number
  rate_limited: number
  final_failed: number
  text_review: number
  measured: number
  success_rate: number | null
  avg_success_duration_ms: number | null
  p95_success_duration_ms: number | null
}

export interface DashboardBucket {
  label: string
  start_at: string
  end_at: string
  total_calls: number
  success_calls: number
  final_failed_calls: number
  success_rate: number | null
  avg_success_duration_ms: number | null
  p95_success_duration_ms: number | null
  switch_requests: number
  switch_count: number
  switch_recovered: number
  switch_recovery_rate: number | null
}

export interface DashboardSwitching {
  requests: number
  count: number
  recovered: number
  recovery_rate: number | null
}

export interface DashboardModelStats {
  name: string
  total_calls: number
  success_calls: number
  failed_calls: number
  rate_limited_calls: number
  final_failed_calls: number
  text_review_calls: number
  measured_calls: number
  success_rate: number | null
  avg_success_duration_ms: number | null
  p95_success_duration_ms: number | null
  call_series: number[]
  success_series: number[]
  failed_series: number[]
  rate_limited_series: number[]
  final_failed_series: number[]
  text_review_series: number[]
  avg_success_duration_series_ms: Array<number | null>
}

export interface DashboardTrend {
  labels: string[]
  total_requests: number[]
  success_requests: number[]
  failed_requests: number[]
  rate_limited_requests: number[]
  final_failed_requests: number[]
  text_review_requests: number[]
  measured_requests: number[]
  success_rate: Array<number | null>
  switch_requests: number[]
  switch_count: number[]
  switch_recovered: number[]
  model_requests: Record<string, number[]>
  model_success_requests: Record<string, number[]>
  model_failed_requests: Record<string, number[]>
  model_rate_limited_requests: Record<string, number[]>
  model_text_review_requests: Record<string, number[]>
  model_avg_success_duration_ms: Record<string, Array<number | null>>
}

export interface DashboardWindow {
  requested: DashboardTimeRangeKey
  start_at: string
  end_at: string
  bucket_unit: 'hour' | 'day'
  bucket_count: number
}

export interface DashboardRangeStats {
  time_range: DashboardTimeRangeKey
  bucket_unit: 'hour' | 'day'
  window: DashboardWindow
  totals: DashboardTotals
  switching: DashboardSwitching
  buckets: DashboardBucket[]
  models: DashboardModelStats[]
  trend: DashboardTrend
}

export interface DashboardResponse {
  status: 'ok' | 'degraded'
  healthy: boolean
  version: string
  meta: DashboardMeta
  metrics: DashboardMetrics
  accounts: DashboardAccountStats
  storage: {
    application_database: Record<string, unknown>
    image_storage: {
      enabled: boolean
      mode: 'local' | 'webdav' | 'both'
      status: 'not_checked'
      available: boolean | null
      image_count: number | null
      image_size_bytes: number | null
    }
  }
  ranges: Record<DashboardTimeRangeKey, DashboardRangeStats>
}
