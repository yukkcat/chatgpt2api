import apiClient, { type ApiResponse, withResponseMetadata } from './client'
import type { ProxyGroup } from './proxy'

export type AccountLane = 'fast' | 'thinking' | 'pro'
export type AccountSourceType = 'web' | 'codex'
export type AccountBackendStatus = '正常' | '限流' | '异常' | '禁用'
export type AccountStatusCategory = 'normal' | 'limited' | 'abnormal' | 'disabled'
export type AccountEnabledAction = 'enable' | 'disable'
export type AccountQuotaState = 'unlimited' | 'unknown' | 'exhausted' | 'available'
export type AccountProxyMode = 'inherit' | 'direct' | 'group' | 'custom'
export type AccountAccessTokenStatus = 'valid' | 'expiring' | 'invalid'
export type AccountRefreshTokenStatus = 'valid' | 'missing' | 'invalid'
export type AccountCredentialAvailability = 'usable' | 'recoverable' | 'unavailable'
export type AccountPresentationTone = 'neutral' | 'success' | 'warning' | 'error' | 'info'
export type AccountGroupProxyMode = AccountProxyMode | 'profile'

export interface Account {
  id: string
  email: string
  user_id: string
  display_name: string
  plan: string
  plan_label: string
  source: AccountSourceType
  source_label: string
  source_plan_label: string
  backend_status: AccountBackendStatus
  status_category: AccountStatusCategory
  status_label: string
  status_tone: AccountPresentationTone
  status_reason_code: string
  status_reason: string
  status_raw_error: string
  enabled: boolean
  enabled_action: AccountEnabledAction
  enabled_action_label: string
  available: boolean
  access_token_status: AccountAccessTokenStatus
  access_token_label: string
  access_token_tone: AccountPresentationTone
  access_token_issued_at?: number | null
  access_token_expires_at?: number | null
  refresh_token_status: AccountRefreshTokenStatus
  refresh_token_label: string
  refresh_token_tone: AccountPresentationTone
  can_refresh_access_token: boolean
  credential_availability: AccountCredentialAvailability
  credential_availability_label: string
  credential_availability_tone: AccountPresentationTone
  refresh_token_invalid_at?: number | null
  last_token_refresh_at?: number | null
  last_token_refresh_error?: string | null
  last_token_refresh_error_at?: number | null
  quota_remaining: number
  quota_unknown: boolean
  quota_unlimited: boolean
  quota_state: AccountQuotaState
  quota_label: string
  quota_reset_at?: number | null
  group_id: string
  group_name: string
  proxy: string
  proxy_mode: AccountProxyMode
  proxy_group_id: string
  proxy_label: string
  success_count: number
  failure_count: number
  image_inflight: number
  last_remote_check_result: string
  last_remote_check_attempt_at?: number | null
  last_remote_checked_at?: number | null
  created_at?: number | null
  last_used_at?: number | null
}

export type AccountProxyProjection = Pick<
  Account,
  'proxy' | 'proxy_mode' | 'proxy_group_id' | 'proxy_label'
>

export interface AccountDetail extends Account {
  configuration: {
    type: string
    source_type: string
    quota: number
    proxy: string
    group_id: string
  }
  diagnostics: {
    remote_check_error: string
    refresh_error: string
    token_refresh_error: string
    last_invalid_at?: number | null
    last_refresh_error_at?: number | null
    last_token_refresh_at?: number | null
  }
}

export type AccountTestMode = 'chat' | 'image'

export interface AccountTestPayload {
  mode: AccountTestMode
  model: string
  prompt: string
}

export interface AccountTestResult {
  status: 'success' | 'failed'
  status_label: string
  tone: 'success' | 'danger'
  account_id: string
  account_label: string
  mode: AccountTestMode
  mode_label: string
  model: string
  duration_ms: number
  content: string
  quota_before_label: string
  quota_after_label: string
  quota_deducted: boolean
  error_code: string
  error_message: string
}

export interface AccountsResponse {
  accounts: Account[]
  total: number
  all_total?: number
  page?: number
  page_size?: number
}

export interface AccountGroup {
  id: string
  name: string
  proxy?: string
  proxy_group_id?: string
  proxy_mode: AccountGroupProxyMode
  proxy_label: string
  enabled: boolean
  notes?: string
  account_count?: number
}

export interface AccountGroupPayload extends Partial<AccountGroup> {
  create_only?: boolean
}

export interface AccountMutationError {
  id: string
  code: string
  message: string
}

export interface AccountMutationResponse {
  progress_id?: string
  target_ids?: string[]
  status?: string
  added?: number
  skipped?: number
  synced?: number
  refreshed?: number
  updated?: number
  removed?: number
  updated_ids?: string[]
  removed_ids?: string[]
  errors?: AccountMutationError[]
  events?: AccountOperationEvent[]
  status_label?: string
  tone?: AccountOperationTone
  message?: string
  summary_items?: AccountOperationSummaryItem[]
  item?: Account | null
  items?: Account[]
  group_id?: string
  groups?: AccountGroup[]
  proxy_groups?: ProxyGroup[]
}

export interface AccountExportResult {
  blob: Blob
  requested: number
  exported: number
  skipped: number
}

export type AccountOperationEventStatus = 'info' | 'success' | 'failed' | 'skipped'
export type AccountOperationTone = 'info' | 'success' | 'warning' | 'danger'

export interface AccountOperationSummaryItem {
  key: string
  label: string
  value: string | number
  tone?: Exclude<AccountOperationTone, 'info'>
}

export interface AccountOperationEvent {
  sequence: number
  timestamp: string
  account_id: string
  account_label: string
  action: string
  status: AccountOperationEventStatus
  tone: AccountOperationTone
  message: string
}

export interface AccountOperationProgress {
  total: number
  processed: number
  done: boolean
  error?: string | null
  status_label?: string
  tone?: AccountOperationTone
  message?: string
  summary_items?: AccountOperationSummaryItem[]
  stage?:
    | 'read_credentials'
    | 'prepare_accounts'
    | 'save_accounts'
    | 'publish_results'
    | 'sync_accounts'
    | 'completed'
  stage_label?: string
  import_result?: {
    added: number
    skipped: number
    synced: number
    failed: number
  }
  status_counts?: Record<string, number>
  total_quota?: number
  events?: AccountOperationEvent[]
  result?: {
    added?: number
    synced?: number
    refreshed?: number
    skipped?: number
    updated?: number
    removed?: number
    updated_ids?: string[]
    removed_ids?: string[]
    errors?: AccountMutationError[]
    events?: AccountOperationEvent[]
    items?: Account[]
  } | null
}

export type AccountListParams = {
  page?: number
  page_size?: number
  keyword?: string
  status?: 'all' | AccountStatusCategory
  group_id?: string
}

export type AccountSelectionScope = {
  mode: 'explicit' | 'filter' | 'all'
  account_ids?: string[]
  excluded_account_ids?: string[]
  keyword?: string
  status?: 'all' | AccountStatusCategory
  group_id?: string
}

export type AccountSelectionTarget = readonly string[] | AccountSelectionScope

export type AccountSelectionPreview = {
  matching_count: number
  selected_count: number
  excluded_account_ids: string[]
  errors?: AccountMutationError[]
}

export type AccountUpsertPayload = {
  id?: string
  access_token?: string
  type?: string
  source_type?: AccountSourceType
  group_id?: string
  proxy?: string
  quota?: number
}

export type AccountImportPayload = Record<string, unknown>
type AccountImportOptions = {
  syncAfterImport?: boolean
  restore?: boolean
  returnItems?: boolean
}
type AccountImportCleanupResponse = {
  checked?: number
  abnormal?: number
  removed?: number
  updated_ids?: string[]
  removed_ids?: string[]
  errors?: AccountMutationError[]
  events?: AccountOperationEvent[]
}
type BackendAccountsResponse = {
  items?: Account[]
  total?: number
  all_total?: number
  page?: number
  page_size?: number
}

const STATUS_NORMAL: AccountBackendStatus = '正常'
const STATUS_DISABLED: AccountBackendStatus = '禁用'
const EMPTY_MODEL_IDS: Record<AccountLane, string> = { fast: '', thinking: '', pro: '' }
type AccountStatusOperation = 'enable' | 'disable'

function cleanString(value: unknown): string {
  return String(value || '').trim()
}

function uniqueStrings(values: readonly string[]): string[] {
  return Array.from(new Set(values.map(cleanString).filter(Boolean)))
}

type AccountSelectionPayload =
  | { account_ids: string[] }
  | { selection: AccountSelectionScope }

function selectionPayload(target: AccountSelectionTarget): AccountSelectionPayload {
  if (Array.isArray(target)) return { account_ids: uniqueStrings(target) }
  const scope = target as AccountSelectionScope
  return {
    selection: {
      ...scope,
      account_ids: uniqueStrings(scope.account_ids || []),
      excluded_account_ids: uniqueStrings(scope.excluded_account_ids || []),
    },
  }
}

function mutationProgress(
  response: AccountMutationResponse,
  total: number,
): AccountOperationProgress {
  const presentation = accountOperationPresentation(response)
  const processed = Math.max(0, total)
  return {
    total: processed,
    processed,
    done: true,
    error: null,
    ...presentation,
    result: {
      added: response.added,
      synced: response.synced,
      refreshed: response.refreshed,
      skipped: response.skipped,
      updated: response.updated,
      removed: response.removed,
      updated_ids: response.updated_ids || [],
      removed_ids: response.removed_ids || [],
      errors: response.errors || [],
      events: response.events || [],
      items: response.items || [],
    },
  }
}

function accountOperationPresentation(
  response: Pick<
    AccountMutationResponse,
    'status_label' | 'tone' | 'message' | 'summary_items' | 'events'
  >,
) {
  const statusLabel = cleanString(response.status_label)
  const message = typeof response.message === 'string' ? response.message : null
  const tone = response.tone
  if (
    !statusLabel
    || !['info', 'success', 'warning', 'danger'].includes(String(tone || ''))
    || message === null
    || !Array.isArray(response.summary_items)
    || !Array.isArray(response.events)
  ) {
    throw new Error('账号操作响应缺少后端展示投影')
  }
  return {
    status_label: statusLabel,
    tone,
    message,
    summary_items: response.summary_items,
    events: response.events,
  }
}

function errorText(error: AccountMutationError): string {
  return [error.id, error.code, error.message].map(cleanString).filter(Boolean).join(': ')
}

function mutationErrorTexts(errors: AccountMutationError[] | undefined): string[] {
  return Array.isArray(errors) ? errors.map(errorText).filter(Boolean) : []
}

function mapAccountsResponse(response: BackendAccountsResponse): AccountsResponse {
  const accounts = Array.isArray(response.items) ? response.items : []
  return {
    accounts,
    total: Number.isFinite(Number(response.total)) ? Number(response.total) : accounts.length,
    all_total: Number.isFinite(Number(response.all_total)) ? Number(response.all_total) : undefined,
    page: Number.isFinite(Number(response.page)) ? Number(response.page) : undefined,
    page_size: Number.isFinite(Number(response.page_size)) ? Number(response.page_size) : undefined,
  }
}

export function accountOperationPollDelayMs(elapsedMs: number) {
  const elapsed = Math.max(0, Number(elapsedMs || 0))
  if (elapsed < 10_000) return 250
  if (elapsed < 60_000) return 500
  if (elapsed < 5 * 60_000) return 1_000
  return 2_000
}

async function pollAccountOperation(
  endpoint:
    | '/api/accounts/sync'
    | '/api/accounts/refresh-access-token'
    | '/api/accounts/batch-update'
    | '/api/accounts',
  target: AccountSelectionTarget,
  onProgress?: (progress: AccountOperationProgress) => void,
  options?: {
    targetCount?: number
    method?: 'POST' | 'DELETE'
    extraPayload?: Record<string, unknown>
  },
) {
  const selection = selectionPayload(target)
  const explicitCount = 'account_ids' in selection ? selection.account_ids.length : 0
  const targetCount = Math.max(0, Number(options?.targetCount || explicitCount))
  if (!targetCount && Array.isArray(target)) throw new Error('没有可操作的账号')

  const payload = { ...selection, ...(options?.extraPayload || {}) }
  const start = options?.method === 'DELETE'
    ? await apiClient.request<unknown, AccountMutationResponse>({
        method: 'DELETE',
        url: endpoint,
        data: payload,
      })
    : await apiClient.post<typeof payload, AccountMutationResponse>(endpoint, payload)
  const progressId = cleanString(start.progress_id)
  if (!progressId) return { status: 'ok', progress: null as AccountOperationProgress | null }

  const startedAt = Date.now()
  const deadline = startedAt + (
    targetCount > 100 ? 12 * 60 * 60 * 1000 : Math.max(90_000, targetCount * 15_000)
  )
  while (Date.now() < deadline) {
    const rawProgress = await apiClient.get<never, AccountOperationProgress>(
      `/api/accounts/operations/${encodeURIComponent(progressId)}`,
    )
    const progress = {
      ...rawProgress,
      ...accountOperationPresentation(rawProgress),
    }
    onProgress?.(progress)
    if (progress.done || progress.error) {
      if (progress.error) throw new Error(progress.error)
      return { status: 'ok', progress }
    }
    await new Promise((resolve) => window.setTimeout(
      resolve,
      accountOperationPollDelayMs(Date.now() - startedAt),
    ))
  }

  throw new Error('账号操作超时，请稍后重新打开列表查看结果')
}

async function updateStatusBatch(
  target: AccountSelectionTarget,
  status: AccountBackendStatus,
  operation: AccountStatusOperation,
  onProgress?: (progress: AccountOperationProgress) => void,
  targetCount?: number,
) {
  const payload = selectionPayload(target)
  if ('account_ids' in payload && !payload.account_ids.length) {
    return {
      status: 'ok',
      progress: {
        total: 0,
        processed: 0,
        done: true,
        error: null,
        events: [] as AccountOperationEvent[],
        result: {
          updated: 0,
          removed: 0,
          updated_ids: [] as string[],
          removed_ids: [] as string[],
          errors: [] as AccountMutationError[],
        },
      },
    }
  }
  return pollAccountOperation('/api/accounts/batch-update', target, onProgress, {
    targetCount,
    extraPayload: { status, operation },
  })
}

async function deleteAccounts(
  target: AccountSelectionTarget,
  onProgress?: (progress: AccountOperationProgress) => void,
  targetCount?: number,
) {
  const payload = selectionPayload(target)
  if ('account_ids' in payload && !payload.account_ids.length) {
    return {
      status: 'ok',
      progress: {
        total: 0,
        processed: 0,
        done: true,
        error: null,
        events: [] as AccountOperationEvent[],
        result: {
          removed: 0,
          removed_ids: [] as string[],
          errors: [] as AccountMutationError[],
        },
      },
    }
  }
  return pollAccountOperation('/api/accounts', target, onProgress, {
    targetCount,
    method: 'DELETE',
  })
}

export const accountsApi = {
  list: async (params?: AccountListParams) => {
    const response = await apiClient.get<never, BackendAccountsResponse>('/api/accounts', {
      params: params || undefined,
    })
    return mapAccountsResponse(response)
  },

  get: async (accountId: string) => {
    const response = await apiClient.get<never, { item: AccountDetail }>(
      `/api/accounts/${encodeURIComponent(cleanString(accountId))}`,
    )
    return response.item
  },

  testAccount: (accountId: string, payload: AccountTestPayload) =>
    apiClient.post<AccountTestPayload, AccountTestResult>(
      `/api/accounts/${encodeURIComponent(cleanString(accountId))}/test`,
      payload,
    ),

  getAccessToken: async (accountId: string) => {
    const response = await apiClient.get<never, { access_token: string }>(
      `/api/accounts/${encodeURIComponent(cleanString(accountId))}/access-token`,
    )
    return cleanString(response.access_token)
  },

  getRefreshToken: async (accountId: string) => {
    const response = await apiClient.get<never, { refresh_token: string }>(
      `/api/accounts/${encodeURIComponent(cleanString(accountId))}/refresh-token`,
    )
    return cleanString(response.refresh_token)
  },

  listGroups: () =>
    apiClient.get<never, { groups: AccountGroup[]; proxy_groups?: ProxyGroup[] }>('/api/account-groups'),

  saveGroup: (payload: AccountGroupPayload) =>
    apiClient.post<AccountGroupPayload, { group: AccountGroup; groups: AccountGroup[]; proxy_groups?: ProxyGroup[] }>(
      '/api/account-groups',
      payload,
    ),

  deleteGroup: (id: string) =>
    apiClient.delete<never, {
      deleted: string
      groups: AccountGroup[]
      proxy_groups?: ProxyGroup[]
      updated_ids?: string[]
      removed_ids?: string[]
      errors?: AccountMutationError[]
    }>(`/api/account-groups/${encodeURIComponent(id)}`),

  upsert: async (payload: AccountUpsertPayload) => {
    const accountId = cleanString(payload.id)
    if (accountId) {
      const response = await apiClient.post<
        {
          id: string
          type?: string
          source_type?: AccountSourceType
          quota?: number
          proxy?: string
          group_id?: string
        },
        AccountMutationResponse
      >('/api/accounts/update', {
        id: accountId,
        type: payload.type,
        source_type: payload.source_type,
        quota: payload.quota,
        proxy: payload.proxy,
        group_id: payload.group_id,
      })
      return {
        status: 'ok',
        account: response.item || undefined,
        updated_ids: response.updated_ids || [],
        removed_ids: response.removed_ids || [],
        errors: response.errors || [],
        events: response.events || [],
        progress: mutationProgress(response, 1),
      }
    }

    const accessToken = cleanString(payload.access_token)
    if (!accessToken) throw new Error('请填写 access token')
    const response = await apiClient.post<
      { tokens: string[]; accounts: AccountImportPayload[]; return_items: boolean },
      AccountMutationResponse
    >('/api/accounts', {
      tokens: [],
      accounts: [{
        access_token: accessToken,
        type: payload.type,
        source_type: payload.source_type,
        status: STATUS_NORMAL,
        quota: payload.quota,
        proxy: payload.proxy,
        group_id: payload.group_id,
      }],
      return_items: true,
    })
    return {
      status: 'ok',
      account: response.items?.[0],
      updated_ids: response.updated_ids || [],
      removed_ids: response.removed_ids || [],
      errors: response.errors || [],
      events: response.events || [],
      progress: mutationProgress(response, 1),
    }
  },

  importAccounts: async (
    accountPayloads: AccountImportPayload[],
    fallbackSourceType: AccountSourceType = 'web',
    options: AccountImportOptions = {},
  ) => {
    const deduped = new Map<string, AccountImportPayload>()
    for (const payload of accountPayloads) {
      if (!payload || typeof payload !== 'object') continue
      const accessToken = cleanString(payload.access_token || payload.accessToken || payload.cookie)
      if (!accessToken) continue
      const nextPayload: AccountImportPayload = {
        ...payload,
        access_token: accessToken,
        source_type: cleanString(payload.source_type) || fallbackSourceType,
        status: cleanString(payload.status) || STATUS_NORMAL,
      }
      delete nextPayload.accessToken
      deduped.set(accessToken, nextPayload)
    }
    const accounts = Array.from(deduped.values())
    if (!accounts.length) {
      return {
        status: 'ok',
        added: 0,
        skipped: 0,
        synced: 0,
        updated_ids: [] as string[],
        removed_ids: [] as string[],
        errors: [] as string[],
        events: [] as AccountOperationEvent[],
      }
    }
    const response = await apiClient.post<
      {
        tokens: string[]
        accounts: AccountImportPayload[]
        sync_after_import: boolean
        restore: boolean
        return_items: boolean
      },
      AccountMutationResponse
    >('/api/accounts', {
      tokens: [],
      accounts,
      sync_after_import: options.syncAfterImport ?? true,
      restore: options.restore ?? false,
      return_items: options.returnItems ?? false,
    })
    return {
      status: 'ok',
      added: Number(response.added || 0),
      skipped: Number(response.skipped || 0),
      synced: Number(response.synced || 0),
      updated_ids: response.updated_ids || [],
      removed_ids: response.removed_ids || [],
      errors: mutationErrorTexts(response.errors),
      events: response.events || [],
      progress: mutationProgress(response, Math.max(0, Number(response.updated || 0) + Number(response.removed || 0))),
    }
  },

  importTokens: (tokens: string[], sourceType: AccountSourceType) =>
    accountsApi.importAccounts(
      uniqueStrings(tokens).map((accessToken) => ({ access_token: accessToken, source_type: sourceType })),
      sourceType,
    ),

  cleanupImportedAbnormalAccounts: async (accountIds: string[], remove = false) => {
    const ids = uniqueStrings(accountIds)
    if (!ids.length) {
      return {
        status: 'ok',
        checked: 0,
        abnormal: 0,
        removed: 0,
        updated_ids: [] as string[],
        removed_ids: [] as string[],
        errors: [] as AccountMutationError[],
        events: [] as AccountOperationEvent[],
      }
    }
    const response = await apiClient.post<
      { account_ids: string[]; remove: boolean },
      AccountImportCleanupResponse
    >('/api/accounts/import-cleanup', { account_ids: ids, remove })
    return {
      status: 'ok',
      checked: Number(response.checked || 0),
      abnormal: Number(response.abnormal || 0),
      removed: Number(response.removed || 0),
      updated_ids: response.updated_ids || [],
      removed_ids: response.removed_ids || [],
      errors: response.errors || [],
      events: response.events || [],
    }
  },

  syncAccountsWithProgress: (
    target: AccountSelectionTarget,
    onProgress?: (progress: AccountOperationProgress) => void,
    targetCount?: number,
  ) => pollAccountOperation('/api/accounts/sync', target, onProgress, { targetCount }),

  refreshAccessTokensWithProgress: (
    target: AccountSelectionTarget,
    onProgress?: (progress: AccountOperationProgress) => void,
    targetCount?: number,
  ) => pollAccountOperation('/api/accounts/refresh-access-token', target, onProgress, { targetCount }),

  previewSelection: (selection: AccountSelectionScope) =>
    apiClient.post<
      { selection: AccountSelectionScope },
      AccountSelectionPreview
    >('/api/accounts/selection-preview', { selection }),

  exportAccounts: async (
    target: AccountSelectionTarget,
    format: 'json' | 'zip' | 'txt' = 'json',
  ): Promise<AccountExportResult> => {
    const response = await apiClient.post<
      ReturnType<typeof selectionPayload> & { format: 'json' | 'zip' | 'txt' },
      ApiResponse<Blob>
    >('/api/accounts/export', {
      ...selectionPayload(target),
      format,
    }, withResponseMetadata({ responseType: 'blob' }))
    const requested = Math.max(0, Number(response.headers['x-export-requested'] || 0))
    const exported = Math.max(0, Number(response.headers['x-exported'] || 0))
    const skipped = Math.max(0, Number(response.headers['x-skipped'] || requested - exported))
    return { blob: response.data, requested, exported, skipped }
  },

  bindGroup: async (target: AccountSelectionTarget, groupId: string) => {
    const payload = selectionPayload(target)
    const response = await apiClient.post<
      typeof payload & { group_id: string },
      AccountMutationResponse
    >('/api/accounts/group', {
      ...payload,
      group_id: groupId,
    })
    return {
      status: 'ok',
      updated: Number(response.updated || 0),
      removed: Number(response.removed || 0),
      updated_ids: response.updated_ids || [],
      removed_ids: response.removed_ids || [],
      errors: response.errors || [],
      events: response.events || [],
      progress: mutationProgress(response, Math.max(0, Number(response.updated || 0) + Number(response.removed || 0))),
      group_id: response.group_id || groupId,
      groups: response.groups || [],
    }
  },

  bulkEnable: (
    target: AccountSelectionTarget,
    onProgress?: (progress: AccountOperationProgress) => void,
    targetCount?: number,
  ) => updateStatusBatch(target, STATUS_NORMAL, 'enable', onProgress, targetCount),
  bulkDisable: (
    target: AccountSelectionTarget,
    onProgress?: (progress: AccountOperationProgress) => void,
    targetCount?: number,
  ) => updateStatusBatch(target, STATUS_DISABLED, 'disable', onProgress, targetCount),
  bulkDelete: (
    target: AccountSelectionTarget,
    onProgress?: (progress: AccountOperationProgress) => void,
    targetCount?: number,
  ) => deleteAccounts(target, onProgress, targetCount),

  resolveCookie: async (_cookie: string) => ({
    status: 'unsupported',
    snlm0e: '',
    model_ids: { ...EMPTY_MODEL_IDS },
  }),
}
