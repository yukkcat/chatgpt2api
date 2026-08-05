import { getStringPreference, preferenceKeys, setStringPreference } from './preferences'

export type ThemeMode = 'light' | 'dark' | 'system'

type ResolvedTheme = 'light' | 'dark'

export function normalizeThemeMode(value: unknown): ThemeMode {
  if (value === 'dark' || value === 'mono-dark') return 'dark'
  if (value === 'light') return 'light'
  return 'system'
}

export function getStoredThemeMode(): ThemeMode {
  return normalizeThemeMode(getStringPreference(preferenceKeys.themeMode, 'system'))
}

export function resolveThemeMode(mode: ThemeMode): ResolvedTheme {
  if (mode !== 'system') return mode
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyThemeMode(mode: ThemeMode): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const resolved = resolveThemeMode(mode)
  root.dataset.themePreference = mode
  if (resolved === 'dark') {
    root.dataset.theme = 'dark'
    root.style.colorScheme = 'dark'
    return
  }
  delete root.dataset.theme
  root.style.colorScheme = 'light'
}

export function setStoredThemeMode(mode: ThemeMode): void {
  const normalized = normalizeThemeMode(mode)
  setStringPreference(preferenceKeys.themeMode, normalized)
  applyThemeMode(normalized)
}
