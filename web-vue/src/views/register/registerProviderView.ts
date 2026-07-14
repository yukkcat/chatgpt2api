import { parseProxyReference, serializeProxyReference } from '@/api/proxy'
import type { ProxyGroup } from '@/api/proxy'
import type { GptMailStatus, LegacyRegisterConfig, RegisterProvider } from '@/api/register'

export type RegisterMode = 'total' | 'quota' | 'available'
export type RegisterProxyMode = 'global' | 'direct' | 'group' | 'custom'
export type RuntimeLogLevel = 'info' | 'success' | 'warning' | 'error'

export type GptMailStatusState = {
  loading: boolean
  error: string
  data: GptMailStatus | null
}

export type RegisterProxyControlState = {
  mode: RegisterProxyMode
  groupId: string
  customProxy: string
}

export type RegisterMetricItem = {
  key: string
  label: string
  value: string | number
  meta?: string
}

export type RegisterRuntimeLogLine = {
  key: string
  time: string
  text: string
  level: RuntimeLogLevel
}

export const providerTypeOptions = [
  { value: 'cloudmail_gen', label: 'CloudMail Gen' },
  { value: 'cloudflare_temp_email', label: 'Cloudflare Temp Email' },
  { value: 'tempmail_lol', label: 'TempMail.lol' },
  { value: 'moemail', label: 'MoEmail' },
  { value: 'inbucket', label: 'Inbucket' },
  { value: 'duckmail', label: 'DuckMail' },
  { value: 'gptmail', label: 'GPTMail' },
  { value: 'donemail', label: 'DoneMail' },
  { value: 'yyds_mail', label: 'YYDS Mail' },
  { value: 'ddg_mail', label: 'DDG + CF 收件箱' },
  { value: 'outlook_token', label: 'Microsoft 邮箱凭据池' },
  { value: 'mailnest' , label: 'mailnest.top Outlook 临时邮箱' },
]

export const providerTypeGroups = [{ options: providerTypeOptions }]

export const registerModeOptions = [
  { value: 'total', label: '按数量注册' },
  { value: 'quota', label: '达到额度停止' },
  { value: 'available', label: '达到账号数停止' },
] as const

export const registerModeGroups = [{ options: registerModeOptions }]

export const registerProxyModeOptions = [
  { value: 'global', label: '使用默认代理' },
  { value: 'direct', label: '直连' },
  { value: 'group', label: '代理组' },
  { value: 'custom', label: '自定义代理' },
] as const

export const registerProxyModeGroups = [{ options: registerProxyModeOptions }]

export const cfAuthModeOptions = [
  { value: 'none', label: '不附加' },
  { value: 'bearer', label: 'Bearer' },
  { value: 'x-api-key', label: 'X-API-Key' },
  { value: 'query-key', label: 'Query key' },
] as const

export const cfAuthModeGroups = [{ options: cfAuthModeOptions }]

export const gptMailKeyModeOptions = [
  { value: 'public', label: '公共测试 Key' },
  { value: 'custom', label: '自定义 Key' },
] as const

export const gptMailKeyModeGroups = [{ options: gptMailKeyModeOptions }]

export const outlookModeOptions = [
  { value: 'graph', label: 'Graph API' },
  { value: 'imap', label: 'IMAP' },
  { value: 'auto', label: '自动兜底' },
] as const

export const outlookModeGroups = [{ options: outlookModeOptions }]

export const providerCommonKeys = ['id', 'enable', 'type', 'label'] as const

export const providerTypeKeys: Record<string, string[]> = {
  cloudmail_gen: ['api_base', 'admin_email', 'admin_password', 'domain', 'subdomain', 'email_prefix'],
  cloudflare_temp_email: ['api_base', 'admin_password', 'domain'],
  tempmail_lol: ['api_key', 'domain'],
  moemail: ['api_base', 'api_key', 'domain', 'expiry_time'],
  inbucket: ['api_base', 'domain', 'random_subdomain'],
  duckmail: ['api_key', 'default_domain'],
  gptmail: ['key_mode', 'api_key', 'default_domain', 'local_compose'],
  donemail: ['api_base', 'admin_key', 'domain', 'email_prefix', 'message_limit'],
  yyds_mail: ['api_base', 'api_key', 'domain', 'subdomain', 'wildcard'],
  ddg_mail: ['api_base', 'ddg_token', 'cf_inbox_jwt', 'admin_password', 'cf_api_key', 'cf_auth_mode', 'cf_create_path', 'cf_messages_path'],
  outlook_token: ['mailboxes', 'mode', 'imap_host', 'message_limit', 'alias_enabled', 'alias_per_email', 'alias_prefix', 'alias_include_original'],
  mailnest: ['api_key', 'project_code'],
}

export const providerLocalOnlyKeys: Record<string, string[]> = {
  outlook_token: ['mailboxes_count', 'mailboxes_base_count', 'mailboxes_alias_count', 'mailboxes_preview', 'mailboxes_stats', 'mailboxes_parse_stats'],
}

export const defaultRegisterConfig: LegacyRegisterConfig = {
  mail: {
    request_timeout: 30,
    wait_timeout: 30,
    wait_interval: 2,
    user_agent: '',
    providers: [],
  },
  proxy: '',
  total: 10,
  threads: 3,
  mode: 'total',
  target_quota: 100,
  target_available: 10,
  check_interval: 5,
  enabled: false,
  stats: {
    success: 0,
    fail: 0,
    done: 0,
    running: 0,
    threads: 3,
    elapsed_seconds: 0,
    avg_seconds: 0,
    success_rate: 0,
    current_quota: 0,
    current_available: 0,
  },
  logs: [],
}

export function providerType(provider: RegisterProvider) {
  return String(provider.type || 'cloudmail_gen')
}

export function createProviderId(type = 'provider') {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 12)
    : Math.random().toString(36).slice(2, 14).padEnd(12, '0')
  return `${type}-${suffix}`
}

export function defaultProvider(type = 'cloudmail_gen'): RegisterProvider {
  const base = { id: createProviderId(type), enable: true, type }
  switch (type) {
    case 'cloudmail_gen':
      return { ...base, api_base: '', admin_email: '', admin_password: '', domain: [], subdomain: [], email_prefix: '' }
    case 'cloudflare_temp_email':
      return { ...base, api_base: '', admin_password: '', domain: [] }
    case 'tempmail_lol':
      return { ...base, api_key: '', domain: [] }
    case 'moemail':
      return { ...base, api_base: '', api_key: '', domain: [], expiry_time: 0 }
    case 'inbucket':
      return { ...base, api_base: '', domain: [], random_subdomain: true }
    case 'duckmail':
      return { ...base, api_key: '', default_domain: 'duckmail.sbs' }
    case 'gptmail':
      return { ...base, key_mode: 'public', api_key: '', default_domain: '', local_compose: false }
    case 'donemail':
      return { ...base, api_base: '', admin_key: '', domain: [], email_prefix: '', message_limit: 20 }
    case 'yyds_mail':
      return { ...base, api_base: 'https://maliapi.215.im/v1', api_key: '', domain: [], subdomain: '', wildcard: false }
    case 'ddg_mail':
      return {
        ...base,
        api_base: '',
        ddg_token: '',
        cf_inbox_jwt: '',
        admin_password: '',
        cf_api_key: '',
        cf_auth_mode: 'none',
        cf_create_path: '/api/new_address',
        cf_messages_path: '/api/mails',
      }
    case 'outlook_token':
      return {
        ...base,
        mailboxes: '',
        mode: 'auto',
        imap_host: 'outlook.office365.com',
        message_limit: 10,
        alias_enabled: false,
        alias_per_email: 5,
        alias_prefix: 'c2api',
        alias_include_original: true,
      }
    case 'mailnest':
      return { ...base, api_key: '', project_code: '' }
    default:
      return base
  }
}

export function normalizeProvider(provider: RegisterProvider): RegisterProvider {
  const type = providerType(provider)
  const normalized = {
    ...defaultProvider(type),
    ...provider,
    id: String(provider.id || provider.provider_id || '').trim() || createProviderId(type),
    type,
    enable: provider.enable !== false,
  }
  if (type === 'gptmail' && !provider.key_mode && isFilled(provider.api_key)) {
    normalized.key_mode = 'custom'
  }
  return normalized
}

export function normalizeRegisterConfig(raw: LegacyRegisterConfig): LegacyRegisterConfig {
  const mail = {
    ...defaultRegisterConfig.mail,
    ...(raw.mail || {}),
    providers: Array.isArray(raw.mail?.providers) ? raw.mail.providers.map(item => normalizeProvider(item)) : [],
  }
  if (!mail.providers.length) {
    mail.providers = [defaultProvider()]
  }
  return {
    ...defaultRegisterConfig,
    ...raw,
    mail,
    stats: { ...defaultRegisterConfig.stats, ...(raw.stats || {}) },
    logs: Array.isArray(raw.logs) ? raw.logs : [],
  }
}

export function providerTitle(_provider: RegisterProvider, index: number) {
  return `邮箱来源 ${index + 1}`
}

export function providerTypeLabel(type: string) {
  return providerTypeOptions.find(item => item.value === type)?.label || type
}

export function registerProxyHint(mode: RegisterProxyMode) {
  if (mode === 'direct') return '本次注册任务强制直连，不读取默认代理。'
  if (mode === 'group') return '注册任务会使用所选代理组；代理组为空时不会偷偷回退到默认代理。'
  if (mode === 'custom') return '仅本注册任务使用该代理地址。'
  return '默认使用系统设置里的默认代理；默认代理设为直连时不使用代理。'
}

export function registerProxyGroupOptions(groups: readonly ProxyGroup[], selectedId = '') {
  const rows = groups.map((group) => ({
    label: `${group.enabled === false ? '停用 · ' : ''}${group.name || group.id}${Array.isArray(group.nodes) ? ` · ${group.nodes.length} 个节点` : ''}`,
    value: group.id,
  }))
  if (selectedId && !rows.some((item) => item.value === selectedId)) {
    rows.unshift({ label: `未知代理组 · ${selectedId}`, value: selectedId })
  }
  return [
    { label: '选择代理组', value: '' },
    ...rows,
  ]
}

export function normalizeRegisterProxyMode(value: string): RegisterProxyMode {
  return ['global', 'direct', 'group', 'custom'].includes(value)
    ? value as RegisterProxyMode
    : 'global'
}

export function registerProxyControlFromValue(value: unknown): RegisterProxyControlState {
  const reference = parseProxyReference(value)
  if (reference.mode === 'group') {
    return { mode: 'group', groupId: reference.value, customProxy: '' }
  }
  if (reference.mode === 'direct') {
    return { mode: 'direct', groupId: '', customProxy: '' }
  }
  if (reference.mode === 'custom' || reference.mode === 'profile') {
    return {
      mode: 'custom',
      groupId: '',
      customProxy: reference.mode === 'profile' ? String(value || '').trim() : reference.value,
    }
  }
  return { mode: 'global', groupId: '', customProxy: '' }
}

export function registerProxyValueFromControl(
  mode: string,
  groupId = '',
  customProxy = '',
): string {
  const nextMode = normalizeRegisterProxyMode(mode)
  if (nextMode === 'global') return serializeProxyReference('global')
  if (nextMode === 'direct') return serializeProxyReference('direct')
  if (nextMode === 'group') return serializeProxyReference('group', groupId)
  return serializeProxyReference('custom', customProxy)
}

export function providerKeysForType(type: string, includeLocalOnly = false) {
  return [
    ...providerCommonKeys,
    ...(providerTypeKeys[type] || []),
    ...(includeLocalOnly ? providerLocalOnlyKeys[type] || [] : []),
  ]
}

export function providerHasKnownType(type: string) {
  return Object.prototype.hasOwnProperty.call(providerTypeKeys, type)
}

export function isFilled(value: unknown) {
  return String(value ?? '').trim().length > 0
}

export function listHasValue(value: unknown) {
  if (Array.isArray(value)) return value.some(item => isFilled(item))
  return isFilled(value)
}

export function listFromProviderDraft(value: unknown) {
  if (Array.isArray(value)) return value.map(String).map(item => item.trim()).filter(Boolean)
  return String(value || '')
    .split(/[\n,]/)
    .map(item => item.trim())
    .filter(Boolean)
}

export function providerDraftValue(type: string, key: string, value: unknown) {
  if (key === 'domain') return listFromProviderDraft(value)
  if (key === 'subdomain') {
    if (type === 'cloudmail_gen') return listFromProviderDraft(value)
    if (type === 'yyds_mail') return Array.isArray(value) ? value.join('\n') : String(value || '')
  }
  return value
}

export function providerWithTypeDraft(current: RegisterProvider, type: string): RegisterProvider {
  const defaults = defaultProvider(type)
  const next: RegisterProvider = {
    ...current,
    ...defaults,
    id: String(current.id || current.provider_id || defaults.id || '').trim(),
    type,
    enable: current.enable !== false,
  }

  for (const key of providerKeysForType(type, true)) {
    if (key === 'type' || key === 'enable') continue
    if (current[key] !== undefined) {
      next[key] = providerDraftValue(type, key, current[key])
    }
  }

  next.type = type
  next.enable = current.enable !== false

  return next
}

export function sanitizedProviderPayload(provider: RegisterProvider): RegisterProvider {
  const type = providerType(provider)
  const output: RegisterProvider = providerHasKnownType(type) ? {} : { ...provider }

  if (providerHasKnownType(type)) {
    for (const key of providerKeysForType(type)) {
      if (provider[key] !== undefined) {
        output[key] = providerDraftValue(type, key, provider[key])
      }
    }
  }

  delete output.mailboxes_count
  delete output.mailboxes_base_count
  delete output.mailboxes_alias_count
  delete output.mailboxes_preview
  delete output.mailboxes_stats
  delete output.mailboxes_parse_stats
  delete output.provider_ref
  return output
}

export function legacyRegisterPayload(config: LegacyRegisterConfig): Partial<LegacyRegisterConfig> {
  return {
    mail: {
      ...config.mail,
      providers: (config.mail.providers || []).map(sanitizedProviderPayload),
    },
    proxy: String(config.proxy || '').trim(),
    total: Math.max(1, Number(config.total) || 1),
    threads: Math.max(1, Number(config.threads) || 1),
    mode: (config.mode || 'total') as RegisterMode,
    target_quota: Math.max(1, Number(config.target_quota) || 1),
    target_available: Math.max(1, Number(config.target_available) || 1),
    check_interval: Math.max(1, Number(config.check_interval) || 5),
  }
}

export function providerUsesPublicGptMailKey(provider: RegisterProvider) {
  return providerType(provider) === 'gptmail' && String(provider.key_mode || 'public') !== 'custom'
}

export function pendingOutlookCount(provider: RegisterProvider) {
  return String(provider.mailboxes || '')
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(line => line && line.split('----').length >= 4)
    .length
}

export function providerRequirementMessages(provider: RegisterProvider) {
  const type = providerType(provider)
  const missing: string[] = []
  const requireValue = (value: unknown, label: string) => {
    if (!isFilled(value)) missing.push(label)
  }
  const requireList = (value: unknown, label: string) => {
    if (!listHasValue(value)) missing.push(label)
  }

  switch (type) {
    case 'cloudmail_gen':
      requireValue(provider.api_base, 'CloudMail URL')
      requireValue(provider.admin_email, '管理员邮箱')
      requireValue(provider.admin_password, 'Admin Password')
      requireList(provider.domain, '邮箱域名')
      break
    case 'cloudflare_temp_email':
      requireValue(provider.api_base, 'API Base')
      requireValue(provider.admin_password, 'Admin Password')
      requireList(provider.domain, '域名')
      break
    case 'moemail':
      requireValue(provider.api_base, 'API Base')
      requireValue(provider.api_key, 'API Key')
      requireList(provider.domain, '域名')
      break
    case 'inbucket':
      requireValue(provider.api_base, 'API Base')
      requireList(provider.domain, '基础域名')
      break
    case 'duckmail':
      requireValue(provider.api_key, 'API Key')
      break
    case 'gptmail':
      if (!providerUsesPublicGptMailKey(provider)) requireValue(provider.api_key, 'API Key')
      if (provider.local_compose) requireValue(provider.default_domain, '默认域名')
      break
    case 'donemail':
      requireValue(provider.api_base, 'DoneMail URL')
      requireValue(provider.admin_key, 'Admin Key')
      requireList(provider.domain, '域名')
      break
    case 'yyds_mail':
      requireValue(provider.api_key, 'API Key')
      break
    case 'ddg_mail':
      requireValue(provider.api_base, 'CF API Base')
      requireValue(provider.ddg_token, 'DDG Token')
      requireValue(provider.cf_inbox_jwt, 'CF Inbox JWT')
      break
    case 'outlook_token': {
      const savedCount = Number(provider.mailboxes_count || 0)
      if (savedCount <= 0 && pendingOutlookCount(provider) <= 0) missing.push('Microsoft 邮箱凭据池')
      break
    }
    case 'mailnest':
      requireValue(provider.api_key, 'API Key')
      requireValue(provider.project_code, 'Project Code')
      break
    default:
      break
  }

  return missing
}

export function providerUsesApiBase(provider: RegisterProvider) {
  return ['cloudmail_gen', 'cloudflare_temp_email', 'moemail', 'inbucket', 'yyds_mail', 'ddg_mail', 'donemail'].includes(providerType(provider))
}

export function providerUsesApiKey(provider: RegisterProvider) {
  return ['tempmail_lol', 'moemail', 'duckmail', 'gptmail', 'yyds_mail', 'mailnest'].includes(providerType(provider))
}

export function providerUsesAdminPassword(provider: RegisterProvider) {
  return ['cloudmail_gen', 'cloudflare_temp_email', 'ddg_mail'].includes(providerType(provider))
}

export function providerUsesDefaultDomain(provider: RegisterProvider) {
  return ['duckmail', 'gptmail'].includes(providerType(provider))
}

export function providerUsesDomainList(provider: RegisterProvider) {
  return ['cloudmail_gen', 'tempmail_lol', 'cloudflare_temp_email', 'moemail', 'inbucket', 'yyds_mail', 'donemail'].includes(providerType(provider))
}

export function apiBaseLabel(provider: RegisterProvider) {
  const type = providerType(provider)
  if (type === 'cloudmail_gen') return 'CloudMail URL'
  if (type === 'ddg_mail') return 'CF API Base'
  if (type === 'donemail') return 'DoneMail URL'
  return 'API Base'
}

export function apiBasePlaceholder(provider: RegisterProvider) {
  const type = providerType(provider)
  if (type === 'donemail') return 'https://sow.us.kg'
  if (type === 'yyds_mail') return 'https://maliapi.215.im/v1'
  return ''
}

export function domainLabel(provider: RegisterProvider) {
  const type = providerType(provider)
  if (type === 'inbucket') return '基础域名'
  if (type === 'cloudmail_gen') return '邮箱域名'
  return '域名'
}

export function domainPlaceholder(provider: RegisterProvider) {
  const type = providerType(provider)
  if (type === 'inbucket') return '每行一个基础域名，可配合随机子域名'
  if (type === 'cloudmail_gen') return '每行一个邮箱域名'
  if (type === 'cloudflare_temp_email') return '每行一个域名'
  if (type === 'moemail') return '每行一个域名'
  if (type === 'tempmail_lol') return '每行一个域名，可留空使用服务默认'
  if (type === 'yyds_mail') return '每行一个域名，可留空'
  if (type === 'donemail') return '每行一个 DoneMail 已接收域名'
  return '每行一个域名'
}

export function gptMailKeyModeLabel(provider: RegisterProvider) {
  return providerUsesPublicGptMailKey(provider) ? '公共' : '自定义'
}

export function numeric(value: unknown) {
  return Number(value || 0) || 0
}

export function outlookPoolSummary(provider: RegisterProvider) {
  const stats = provider.mailboxes_stats || {}
  const inUse = numeric(stats.in_use)
  const loginRequired = numeric(stats.login_required)
  const tokenInvalid = numeric(stats.token_invalid)
  const failed = numeric(stats.failed)
  const retryable = numeric(stats.retryable) || failed
  const invalid = numeric(stats.invalid) || loginRequired + tokenInvalid

  return {
    saved: numeric(provider.mailboxes_count),
    pending: pendingOutlookCount(provider),
    available: numeric(stats.available) || numeric(stats.unused),
    used: numeric(stats.used),
    inUse,
    loginRequired,
    tokenInvalid,
    failed,
    retryable,
    invalid,
    abnormal: retryable + invalid,
  }
}

export function outlookAliasSummary(provider: RegisterProvider) {
  const base = numeric(provider.mailboxes_base_count || provider.mailboxes_count)
  const alias = numeric(provider.mailboxes_alias_count)
  const perEmail = numeric(provider.alias_per_email)
  const includeOriginal = provider.alias_include_original !== false
  const multiplier = provider.alias_enabled ? perEmail + (includeOriginal ? 1 : 0) : 1
  const pending = pendingOutlookCount(provider)
  return {
    enabled: Boolean(provider.alias_enabled),
    base,
    alias,
    perEmail,
    includeOriginal,
    multiplier,
    pending,
    pendingExpanded: provider.alias_enabled ? pending * multiplier : pending,
  }
}

export function outlookAliasHint(provider: RegisterProvider) {
  const summary = outlookAliasSummary(provider)
  if (!summary.enabled) return '未启用加号别名，注册时直接使用导入邮箱。'
  if (summary.pending > 0) {
    return `保存后本次导入约展开为 ${summary.pendingExpanded} 个注册地址；登录和收信仍使用原邮箱凭据。`
  }
  if (summary.base > 0) {
    return `已保存 ${summary.base} 个原邮箱，当前规则生成 ${summary.alias} 个别名地址；登录和收信仍使用原邮箱凭据。`
  }
  return '保存后会为 Outlook / Hotmail 地址生成加号别名；登录和收信仍使用原邮箱凭据。'
}

export function outlookPoolHint(provider: RegisterProvider) {
  const summary = outlookPoolSummary(provider)
  if (summary.pending > 0) return `有 ${summary.pending} 个待保存，保存配置后进入 Microsoft 邮箱池。`
  if (summary.saved <= 0) return '还没有保存 Microsoft 邮箱材料。'
  if (summary.invalid > 0) return `有 ${summary.invalid} 个异常邮箱，需要重新获取 refresh_token 或重新导入材料。`
  if (summary.retryable > 0 || summary.inUse > 0) return `有 ${summary.retryable} 个临时失败、${summary.inUse} 个占用，可在更多维护里释放后重试。`
  if (summary.available <= 0) return '库存已用完，请导入新的 Microsoft 邮箱材料。'
  return `已保存 ${summary.saved} 个 Microsoft 邮箱材料。`
}

export function gptMailSecondsUntilReset(status: GptMailStatus, now = Date.now()) {
  const resetAt = Date.parse(String(status.reset_at || ''))
  if (Number.isFinite(resetAt)) {
    return Math.ceil((resetAt - now) / 1000)
  }
  const seconds = Number(status.seconds_until_reset)
  if (!Number.isFinite(seconds) || seconds <= 0) return null
  const checkedAt = Date.parse(String(status.checked_at || ''))
  if (Number.isFinite(checkedAt)) {
    return Math.ceil((checkedAt + seconds * 1000 - now) / 1000)
  }
  return Math.ceil(seconds)
}

export function formatGptMailNumber(value: unknown) {
  const number = Number(value)
  if (!Number.isFinite(number)) return ''
  if (number < 0) return '不限'
  return new Intl.NumberFormat().format(number)
}

export function formatGptMailDuration(seconds: unknown) {
  const total = Number(seconds)
  if (!Number.isFinite(total) || total <= 0) return ''
  if (total < 60) return `${Math.ceil(total)}s 后重置`
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (hours > 0) return `${hours}h ${minutes}m 后重置`
  return `${Math.max(1, minutes)}m 后重置`
}

export function gptMailStatusTone(state: GptMailStatusState) {
  if (state.loading) return 'info'
  if (state.error) return 'danger'
  if (!state.data) return 'muted'
  if (state.data.is_active === false) return 'warning'
  return 'success'
}

export function gptMailStatusTitle(state: GptMailStatusState, provider: RegisterProvider) {
  if (state.loading) return '检测中'
  if (state.error) return '检测失败'
  if (!state.data) return providerUsesPublicGptMailKey(provider) ? '公共 Key' : '未检测'
  return state.data.is_active === false ? '不可用' : '可用'
}

export function gptMailRemainingText(status?: GptMailStatus | null) {
  if (!status) return ''
  if (String(status.key_mode || '') === 'custom') {
    const remaining = formatGptMailNumber(status.remaining_total)
    const total = formatGptMailNumber(status.total_limit)
    if (remaining && total) return `${remaining} / ${total}`
    if (remaining) return remaining
  }
  return formatGptMailNumber(status.remaining_today ?? status.remaining_total)
}

export function gptMailResetText(status?: GptMailStatus | null, now = Date.now(), formatClock: (value?: string | null) => string = defaultFormatClock) {
  if (!status) return ''
  if (String(status.key_mode || '') === 'custom' && !status.reset_at && !status.seconds_until_reset) return ''
  const seconds = gptMailSecondsUntilReset(status, now)
  const countdown = formatGptMailDuration(seconds)
  if (countdown) return countdown
  if (seconds !== null && seconds <= 0) return '等待刷新'
  if (status.reset_at) return `${formatClock(status.reset_at)} 重置`
  return ''
}

export function gptMailStatusHint(
  state: GptMailStatusState,
  provider: RegisterProvider,
  formatClock: (value?: string | null) => string = defaultFormatClock,
) {
  if (state.error) return state.error
  if (provider.local_compose && !String(provider.default_domain || '').trim()) {
    return '本地拼接模式需要填写默认域名。'
  }
  if (provider.local_compose) {
    return '本地拼接会少调用一次生成邮箱接口；请确认默认域名当前可用。'
  }
  if (!state.data) {
    return providerUsesPublicGptMailKey(provider)
      ? '使用 GPTMail 公共测试 Key，启动注册时后端会自动获取并缓存。'
      : '填写自定义 Key 后可检测总额度和剩余额度。'
  }
  if (String(state.data.key_mode || provider.key_mode || '') === 'custom') {
    const totalUsed = formatGptMailNumber(state.data.total_usage)
    const totalLimit = formatGptMailNumber(state.data.total_limit)
    const totalRemaining = formatGptMailNumber(state.data.remaining_total)
    const checkedText = state.data.checked_at ? `检测于 ${formatClock(state.data.checked_at)}` : '状态已更新'
    const resetText = state.data.reset_at ? `重置时间 ${formatClock(state.data.reset_at)}` : '自定义 Key 未返回独立重置时间'
    if (totalUsed && totalLimit) {
      return `总计已用 ${totalUsed} / ${totalLimit}${totalRemaining ? `，剩余 ${totalRemaining}` : ''}，${checkedText}；${resetText}。`
    }
    if (totalRemaining) return `总剩余 ${totalRemaining}，${checkedText}；${resetText}。`
    return `${checkedText}；${resetText}。`
  }
  const used = formatGptMailNumber(state.data.used_today)
  const limit = formatGptMailNumber(state.data.daily_limit)
  if (used && limit) return `今日已用 ${used} / ${limit}，${state.data.checked_at ? `检测于 ${formatClock(state.data.checked_at)}` : '状态已更新'}。`
  return state.data.checked_at ? `状态已更新，检测于 ${formatClock(state.data.checked_at)}。` : '状态已更新。'
}

export function formatClock(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString()
}

export function arrayText(value: unknown) {
  if (Array.isArray(value)) return value.map(String).join('\n')
  return String(value || '')
}

export function registerMetricItems(
  stats: NonNullable<LegacyRegisterConfig['stats']>,
  threads = 0,
): RegisterMetricItem[] {
  return [
    { key: 'success', label: '成功', value: stats.success || 0, meta: `成功率 ${stats.success_rate || 0}%` },
    { key: 'fail', label: '失败', value: stats.fail || 0 },
    { key: 'done', label: '完成', value: stats.done || 0 },
    { key: 'running', label: '运行 / 线程', value: `${stats.running || 0} / ${stats.threads || threads || 0}` },
    { key: 'elapsed', label: '运行时间', value: `${stats.elapsed_seconds || 0}s` },
    { key: 'avg', label: '平均耗时', value: `${stats.avg_seconds || 0}s` },
    { key: 'quota', label: '当前额度', value: stats.current_quota || 0 },
    { key: 'available', label: '正常账号', value: stats.current_available || 0 },
  ]
}

export function enabledRegisterProviderCount(providers: readonly RegisterProvider[]) {
  return providers.filter(provider => provider.enable !== false).length
}

export function registerProviderIssueCount(providers: readonly RegisterProvider[]) {
  return providers
    .filter(provider => provider.enable !== false)
    .reduce((total, provider) => total + providerRequirementMessages(provider).length, 0)
}

export function registerActionDisabled(
  config: LegacyRegisterConfig | null | undefined,
  legacySaving: boolean,
  enabledCount: number,
  issueCount: number,
) {
  if (legacySaving || !config) return true
  if (config.enabled) return false
  return enabledCount === 0 || issueCount > 0
}

export function registerRuntimeHint(
  config: LegacyRegisterConfig | null | undefined,
  enabledCount: number,
  issueCount: number,
) {
  if (enabledCount === 0) return '至少启用一个邮箱来源。'
  if (issueCount > 0) return `还有 ${issueCount} 项必填配置未完成。`
  if (config?.enabled) return '任务运行中，配置已锁定。'
  return '启动前会自动保存当前配置。'
}

export function registerRuntimeLogLines(
  logs: NonNullable<LegacyRegisterConfig['logs']>,
  format: (value?: string | null) => string = formatClock,
): RegisterRuntimeLogLine[] {
  return logs.slice().reverse().map((item, index) => ({
    key: registerRuntimeLogLineKey(item, logs.length - index - 1),
    time: format(item.time),
    text: item.text || '-',
    level: normalizeRuntimeLogLevel(item.level),
  }))
}

function registerRuntimeLogLineKey(
  item: NonNullable<LegacyRegisterConfig['logs']>[number],
  sourceIndex: number,
): string {
  const time = String(item.time || 'log').replaceAll('|', '/')
  const level = String(item.level || 'info').replaceAll('|', '/')
  const text = String(item.text || '-').replaceAll('|', '/')
  const sample = text.length <= 96 ? text : `${text.length}:${text.slice(0, 72)}:${text.slice(-16)}`
  return `${time}|${level}|${sample}|${sourceIndex}`
}

export function normalizeRuntimeLogLevel(level?: string): RuntimeLogLevel {
  if (level === 'red' || level === 'error') return 'error'
  if (level === 'green' || level === 'success') return 'success'
  if (level === 'yellow' || level === 'warning') return 'warning'
  return 'info'
}

function defaultFormatClock(value?: string | null) {
  return formatClock(value)
}
