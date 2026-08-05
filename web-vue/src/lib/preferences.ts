export const preferenceKeys = {
  sidebarCollapsed: 'sidebar-collapsed',
  accountsViewMode: 'accounts-view-mode',
  accountsPageSize: 'accounts-page-size',
  systemLogLimit: 'system-log-limit',
  galleryPageSize: 'gallery-page-size',
  listLayoutMode: 'list-layout-mode',
  publicLogFoldState: 'public-log-fold-state',
  imageTaskLocalIds: 'image-task-local-ids',
  imageTaskConversations: 'image-task-conversations',
  imageTaskActiveConversationId: 'image-task-active-conversation-id',
  studioActiveMode: 'studio-active-mode',
  studioActiveConversationId: 'studio-active-conversation-id',
  studioChatModel: 'studio-chat-model',
  studioChatReasoningEffort: 'studio-chat-reasoning-effort',
  studioConversationBadges: 'studio-conversation-badges',
  studioConversations: 'studio-conversations',
  studioFullscreen: 'studio-fullscreen',
  studioFileKind: 'studio-file-kind',
  studioImageModel: 'studio-image-model',
  studioSidebarWidth: 'studio-sidebar-width',
  themeMode: 'theme-mode',
} as const

type PreferenceKey = typeof preferenceKeys[keyof typeof preferenceKeys]

function storage(): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function getStringPreference(key: PreferenceKey, fallback = ''): string {
  const value = storage()?.getItem(key)
  return value == null ? fallback : value
}

export function setStringPreference(key: PreferenceKey, value: string): void {
  storage()?.setItem(key, value)
}

export function getBooleanPreference(key: PreferenceKey, fallback = false): boolean {
  const value = getStringPreference(key)
  if (!value) return fallback
  return value === 'true'
}

export function setBooleanPreference(key: PreferenceKey, value: boolean): void {
  setStringPreference(key, value ? 'true' : 'false')
}

export function getNumberPreference(
  key: PreferenceKey,
  fallback: number,
  options: { allowed?: readonly number[]; min?: number; max?: number } = {},
): number {
  const parsed = Number(getStringPreference(key))
  if (!Number.isFinite(parsed)) return fallback
  const next = Math.trunc(parsed)
  if (options.allowed && !options.allowed.includes(next)) return fallback
  if (typeof options.min === 'number' && next < options.min) return fallback
  if (typeof options.max === 'number' && next > options.max) return fallback
  return next
}

export function setNumberPreference(key: PreferenceKey, value: number): void {
  setStringPreference(key, String(value))
}

export function getJsonPreference<T>(key: PreferenceKey, fallback: T): T {
  const value = getStringPreference(key)
  if (!value) return fallback
  try {
    return JSON.parse(value) as T
  } catch {
    return fallback
  }
}

export function setJsonPreference(key: PreferenceKey, value: unknown): void {
  setStringPreference(key, JSON.stringify(value))
}

export function removePreference(key: PreferenceKey): void {
  storage()?.removeItem(key)
}
