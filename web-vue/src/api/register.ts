import apiClient from './client'

export type OutlookMailboxParseStats = {
  raw_lines?: number
  non_empty?: number
  valid?: number
  duplicates?: number
  invalid?: number
  skipped?: number
  existing_total?: number
  saved_total?: number
  issues?: Array<{
    line?: number
    reason?: string
    email?: string
  }>
  [key: string]: unknown
}

export type RegisterProvider = {
  id?: string
  provider_id?: string
  enable?: boolean
  type?: string
  label?: string
  api_base?: string
  api_key?: string
  admin_key?: string
  admin_email?: string
  admin_password?: string
  ddg_token?: string
  cf_inbox_jwt?: string
  cf_api_base?: string
  cf_api_key?: string
  cf_auth_mode?: string
  cf_create_path?: string
  cf_messages_path?: string
  default_domain?: string
  key_mode?: 'public' | 'custom' | string
  local_compose?: boolean
  email_prefix?: string
  subdomain?: string | string[]
  domain?: string[]
  cf_domain?: string[]
  random_subdomain?: boolean
  wildcard?: boolean
  expiry_time?: number
  mailboxes?: string
  mailboxes_count?: number
  mailboxes_base_count?: number
  mailboxes_alias_count?: number
  mailboxes_preview?: string[]
  alias_enabled?: boolean
  alias_per_email?: number
  alias_prefix?: string
  alias_include_original?: boolean
  mailboxes_stats?: {
    unused?: number
    in_use?: number
    used?: number
    login_required?: number
    token_invalid?: number
    failed?: number
    available?: number
    busy?: number
    retryable?: number
    invalid?: number
    abnormal?: number
    [key: string]: number | undefined
  }
  mailboxes_parse_stats?: OutlookMailboxParseStats
  mode?: 'graph' | 'imap' | 'auto' | string
  imap_host?: string
  message_limit?: number
  [key: string]: unknown
}

export type LegacyRegisterConfig = {
  mail: {
    request_timeout?: number
    wait_timeout?: number
    wait_interval?: number
    user_agent?: string
    providers?: RegisterProvider[]
    [key: string]: unknown
  }
  proxy: string
  total: number
  threads: number
  mode: 'total' | 'quota' | 'available' | string
  target_quota: number
  target_available: number
  check_interval: number
  enabled: boolean
  stats?: {
    success?: number
    fail?: number
    done?: number
    running?: number
    threads?: number
    elapsed_seconds?: number
    avg_seconds?: number
    success_rate?: number
    current_quota?: number
    current_available?: number
    [key: string]: unknown
  }
  logs?: Array<{
    time: string
    text: string
    level?: string
  }>
}

export type GptMailStatus = {
  ok?: boolean
  key_mode?: string
  api_base?: string
  source?: string
  is_active?: boolean
  daily_limit?: number | null
  used_today?: number | null
  remaining_today?: number | null
  total_limit?: number | null
  total_usage?: number | null
  remaining_total?: number | null
  reset_at?: string
  seconds_until_reset?: number | null
  checked_at?: string
  key_hint?: string
  local_compose?: boolean
  default_domain?: string
}

export const registerApi = {
  getConfig() {
    return apiClient.get<any, { register: LegacyRegisterConfig }>('/api/register')
  },
  updateConfig(payload: Partial<LegacyRegisterConfig>) {
    return apiClient.post<any, { register: LegacyRegisterConfig }>('/api/register', payload)
  },
  startLegacy() {
    return apiClient.post<any, { register: LegacyRegisterConfig }>('/api/register/start')
  },
  stopLegacy() {
    return apiClient.post<any, { register: LegacyRegisterConfig }>('/api/register/stop')
  },
  resetLegacy() {
    return apiClient.post<any, { register: LegacyRegisterConfig }>('/api/register/reset')
  },
  resetOutlookPool(scope: 'all' | 'retryable' | 'invalid' | 'unused' | 'failed' = 'all') {
    return apiClient.post<any, { register: LegacyRegisterConfig }>('/api/register/outlook-pool/reset', { scope })
  },
  getGptMailStatus(provider: RegisterProvider, force = true) {
    return apiClient.post<any, { status: GptMailStatus }>('/api/register/gptmail/status', { provider, force })
  },
  refreshGptMailKey(provider: RegisterProvider, force = true) {
    return apiClient.post<any, { status: GptMailStatus }>('/api/register/gptmail/refresh-key', { provider, force })
  },
}
