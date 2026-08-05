import apiClient from './client'
import type {
  AccountMutationResponse,
  AccountOperationEvent,
  AccountOperationSummaryItem,
  AccountOperationTone,
} from './accounts'

export interface OAuthLoginStartResponse {
  session_id: string
  authorize_url: string
  expires_in: string
  redirect_uri_prefix: string
}

export interface CPAImportJob {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  stage: 'read_credentials' | 'save_accounts' | 'sync_accounts' | 'completed'
  stage_label: string
  stage_total: number
  stage_completed: number
  terminal: boolean
  progress_total: number
  progress_completed: number
  status_label: string
  tone: AccountOperationTone
  error: string
  summary_items: AccountOperationSummaryItem[]
  result_message: string
  result_tone: AccountOperationTone
  created_at: string
  updated_at: string
  total: number
  completed: number
  added: number
  skipped: number
  synced: number
  failed: number
  failed_total: number
  errors: Array<{ stage: 'fetch' | 'sync'; name: string; error: string }>
  events?: AccountOperationEvent[]
}

export type RemoteAccountImportMode = 'cpa' | 'sub2api'

export interface RemoteAccountImportStarted {
  mode: RemoteAccountImportMode
  source_id: string
  job: CPAImportJob
  title: string
  total: number
}

export interface CPAPool {
  id: string
  name: string
  base_url: string
  import_job?: CPAImportJob | null
}

export interface CPARemoteFile {
  name: string
  email: string
}

export interface Sub2APIServer {
  id: string
  name: string
  base_url: string
  email: string
  has_api_key: boolean
  group_id: string
  import_job?: CPAImportJob | null
}

export interface Sub2APIRemoteAccount {
  id: string
  name: string
  email: string
  plan_type: string
  status: string
  expires_at: string
  remote_group_id?: string
  remote_group_name?: string
  has_access_token?: boolean
}

export interface Sub2APIRemoteGroup {
  id: string
  name: string
  description: string
  platform: string
  status: string
  account_count: number
  active_account_count: number
}

export interface Sub2APIImportGroupBinding {
  remote_group_id: string
  name: string
  account_ids: string[]
}

export const accountImportsApi = {
  startOAuthLogin: (emailHint = '') =>
    apiClient.post<{ email_hint: string }, OAuthLoginStartResponse>(
      '/api/accounts/oauth/start',
      { email_hint: emailHint },
    ),

  finishOAuthLogin: (sessionId: string, callback: string) =>
    apiClient.post<{ session_id: string; callback: string }, AccountMutationResponse>(
      '/api/accounts/oauth/finish',
      { session_id: sessionId, callback },
    ),

  listCPAPools: () =>
    apiClient.get<never, { pools: CPAPool[] }>('/api/cpa/pools'),

  createCPAPool: (pool: { name: string; base_url: string; secret_key: string }) =>
    apiClient.post<{ name: string; base_url: string; secret_key: string }, { pool: CPAPool; pools: CPAPool[] }>(
      '/api/cpa/pools',
      pool,
    ),

  updateCPAPool: (poolId: string, updates: { name?: string; base_url?: string; secret_key?: string }) =>
    apiClient.post<{ name?: string; base_url?: string; secret_key?: string }, { pool: CPAPool; pools: CPAPool[] }>(
      `/api/cpa/pools/${encodeURIComponent(poolId)}`,
      updates,
    ),

  deleteCPAPool: (poolId: string) =>
    apiClient.delete<never, { pools: CPAPool[] }>(
      `/api/cpa/pools/${encodeURIComponent(poolId)}`,
    ),

  listCPAPoolFiles: (poolId: string) =>
    apiClient.get<never, { pool_id: string; files: CPARemoteFile[] }>(
      `/api/cpa/pools/${encodeURIComponent(poolId)}/files`,
    ),

  startCPAImport: (poolId: string, names: string[]) =>
    apiClient.post<{ names: string[] }, { import_job: CPAImportJob | null }>(
      `/api/cpa/pools/${encodeURIComponent(poolId)}/import`,
      { names },
    ),

  getCPAImportJob: (poolId: string) =>
    apiClient.get<never, { import_job: CPAImportJob | null }>(
      `/api/cpa/pools/${encodeURIComponent(poolId)}/import`,
    ),

  listSub2APIServers: () =>
    apiClient.get<never, { servers: Sub2APIServer[] }>('/api/sub2api/servers'),

  createSub2APIServer: (server: {
    name: string
    base_url: string
    email: string
    password: string
    api_key: string
    group_id: string
  }) =>
    apiClient.post<
      { name: string; base_url: string; email: string; password: string; api_key: string; group_id: string },
      { server: Sub2APIServer; servers: Sub2APIServer[] }
    >('/api/sub2api/servers', server),

  updateSub2APIServer: (
    serverId: string,
    updates: {
      name?: string
      base_url?: string
      email?: string
      password?: string
      api_key?: string
      group_id?: string
    },
  ) =>
    apiClient.post<
      { name?: string; base_url?: string; email?: string; password?: string; api_key?: string; group_id?: string },
      { server: Sub2APIServer; servers: Sub2APIServer[] }
    >(`/api/sub2api/servers/${encodeURIComponent(serverId)}`, updates),

  deleteSub2APIServer: (serverId: string) =>
    apiClient.delete<never, { servers: Sub2APIServer[] }>(
      `/api/sub2api/servers/${encodeURIComponent(serverId)}`,
    ),

  listSub2APIServerGroups: (serverId: string) =>
    apiClient.get<never, { server_id: string; groups: Sub2APIRemoteGroup[] }>(
      `/api/sub2api/servers/${encodeURIComponent(serverId)}/groups`,
    ),

  listSub2APIServerAccounts: (serverId: string, groupId?: string | null) =>
    apiClient.get<never, { server_id: string; accounts: Sub2APIRemoteAccount[] }>(
      `/api/sub2api/servers/${encodeURIComponent(serverId)}/accounts`,
      groupId === undefined ? undefined : { params: { group_id: groupId ?? '' } },
    ),

  startSub2APIImport: (
    serverId: string,
    accountIds: string[],
    options: {
      group_bindings?: Sub2APIImportGroupBinding[]
      create_account_groups?: boolean
    } = {},
  ) =>
    apiClient.post<
      { account_ids: string[]; group_bindings?: Sub2APIImportGroupBinding[]; create_account_groups?: boolean },
      { import_job: CPAImportJob | null }
    >(
      `/api/sub2api/servers/${encodeURIComponent(serverId)}/import`,
      { account_ids: accountIds, ...options },
    ),

  getSub2APIImportJob: (serverId: string) =>
    apiClient.get<never, { import_job: CPAImportJob | null }>(
      `/api/sub2api/servers/${encodeURIComponent(serverId)}/import`,
    ),
}
