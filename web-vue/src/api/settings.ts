import apiClient from './client'
import type {
  Settings,
  SettingsMutationResult,
  SettingsView,
} from '@/types/api'

export interface BackupTestResult {
  ok: boolean
  status?: number
  error?: string | null
}

export interface ImageStorageTestResult {
  ok: boolean
  status?: number
  error?: string | null
}

export interface ImageStorageSyncResult {
  uploaded: number
  skipped: number
  failed: number
}

export interface RetentionCleanupRequest {
  log_retention_days?: number
  image_retention_days?: number
}

export interface RetentionCleanupSection {
  removed: number
  kept?: number
  removed_size_bytes: number
  retention_days: number
  dry_run: boolean
}

export interface RetentionCleanupResult {
  dry_run: boolean
  logs: RetentionCleanupSection
  images: RetentionCleanupSection
  total_removed: number
  total_size_bytes: number
}

export interface AccountCleanupRequest {
  auto_remove_invalid_accounts?: boolean
  auto_remove_rate_limited_accounts?: boolean
}

export interface AccountCleanupResult {
  dry_run: boolean
  invalid: number
  rate_limited: number
  total_removed: number
  auto_remove_invalid_accounts: boolean
  auto_remove_rate_limited_accounts: boolean
}

export interface BackupState {
  running?: boolean
  last_status?: string
  last_started_at?: string
  last_finished_at?: string
  last_object_key?: string
  last_error?: string
}

export interface BackupItem {
  key: string
  name?: string
  size?: number
  size_bytes?: number
  last_modified?: string
  encrypted?: boolean
}

export interface BackupRunResult {
  key: string
  size: number
  encrypted: boolean
}

export type ThirdPartyAppsSettings = Settings['third_party_apps']
export const PUBLIC_SETTINGS_CHANGED_EVENT = 'chatgpt2api:public-settings-changed'

export interface PublicThirdPartyAppsSettings {
  infinite_canvas: {
    enabled: boolean
    url: string
  }
}

export interface PublicThirdPartyAppsView {
  api_base_url: string
  third_party_apps: PublicThirdPartyAppsSettings
}

type SettingsPatchValue<T> = T extends readonly unknown[]
  ? T
  : T extends object
    ? { [K in keyof T as K extends `has_${string}` | 'provider' ? never : K]?: SettingsPatchValue<T[K]> }
    : T

export type SettingsPatch = SettingsPatchValue<Settings>
type SettingsUpdateRequest = SettingsPatch & { revision: string }

function cloneJsonValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function valuesEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

function buildLeafPatch(next: unknown, previous: unknown): unknown {
  if (valuesEqual(next, previous)) return undefined
  if (!isRecord(next)) return cloneJsonValue(next)

  const baseline = isRecord(previous) ? previous : {}
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(next)) {
    if (key.startsWith('has_') || key === 'provider') continue
    const child = buildLeafPatch(value, baseline[key])
    if (typeof child !== 'undefined') result[key] = child
  }
  return Object.keys(result).length ? result : undefined
}

export function prepareSettingsForEdit(value: Settings): Settings {
  return cloneJsonValue(value)
}

export function prepareSettingsPatch(settings: Settings, baseline: Settings): SettingsPatch {
  const patch = buildLeafPatch(settings, baseline)
  return (isRecord(patch) ? patch : {}) as SettingsPatch
}

export const settingsApi = {
  get: () => apiClient.get<never, SettingsView>('/api/settings'),

  async getThirdPartyApps(): Promise<PublicThirdPartyAppsView> {
    const response = await apiClient.get<never, PublicThirdPartyAppsView>('/api/third-party-apps')
    return cloneJsonValue(response)
  },

  updatePartial: (payload: SettingsUpdateRequest) =>
    apiClient.patch<SettingsUpdateRequest, SettingsMutationResult>('/api/settings', cloneJsonValue(payload)),

  testBackup: () =>
    apiClient.post<Record<string, never>, { result: BackupTestResult }>('/api/backup/test', {}),

  listBackups: () =>
    apiClient.get<never, { items: BackupItem[]; state: BackupState }>('/api/backups'),

  runBackup: () =>
    apiClient.post<Record<string, never>, { result: BackupRunResult }>('/api/backups/run', {}),

  deleteBackup: (key: string) =>
    apiClient.post<{ key: string }, { ok: boolean }>('/api/backups/delete', { key }),

  testImageStorage: () =>
    apiClient.post<Record<string, never>, { result: ImageStorageTestResult }>('/api/image-storage/test', {}),

  syncImageStorage: () =>
    apiClient.post<Record<string, never>, { result: ImageStorageSyncResult }>('/api/image-storage/sync', {}),

  previewRetentionCleanup: (payload: RetentionCleanupRequest = {}) =>
    apiClient.post<RetentionCleanupRequest, RetentionCleanupResult>('/api/settings/retention-cleanup/preview', payload),

  runRetentionCleanup: (payload: RetentionCleanupRequest = {}) =>
    apiClient.post<RetentionCleanupRequest, RetentionCleanupResult>('/api/settings/retention-cleanup/run', payload),

  previewAccountCleanup: (payload: AccountCleanupRequest = {}) =>
    apiClient.post<AccountCleanupRequest, AccountCleanupResult>('/api/settings/account-cleanup/preview', payload),

  runAccountCleanup: (payload: AccountCleanupRequest = {}) =>
    apiClient.post<AccountCleanupRequest, AccountCleanupResult>('/api/settings/account-cleanup/run', payload),
}
