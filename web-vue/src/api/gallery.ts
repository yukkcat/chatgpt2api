import apiClient from './client'

export type GalleryMediaType = 'all' | 'image'
export type GalleryFileMediaType = Exclude<GalleryMediaType, 'all'>
export type GalleryStorage = 'local' | 'webdav' | 'both'

export interface GalleryRow {
  id: string
  path: string
  filename: string
  url: string
  thumbnail_url: string
  size_bytes: number
  created_at: string
  date: string
  media_type: GalleryFileMediaType
  expired: boolean
  expires_at: string | null
  expires_in_seconds: number | null
  tags: string[]
  storage: GalleryStorage
  local: boolean
  webdav: boolean
  available: boolean
  width: number | null
  height: number | null
}

export type GalleryFile = Omit<GalleryRow, 'storage'> & {
  storage: GalleryStorage | 'log' | 'studio'
}

export interface GalleryMediaFacets {
  all: number
  image: number
}

export interface GalleryResponse {
  schema_version: number
  generated_at: string
  items: GalleryRow[]
  total: number
  total_size_bytes: number
  retention_days: number
  facets: {
    media_types: GalleryMediaFacets
    tags: string[]
  }
  media_type: GalleryMediaType
  page: number
  page_size: number
  page_count: number
  has_more: boolean
}

export interface ImageStorageStats {
  disk_total_mb: number
  disk_used_mb: number
  disk_free_mb: number
  image_count: number
  image_size_mb: number
  image_size_bytes: number
}

export interface ImageCompressResult {
  compressed: number
  saved_bytes: number
  saved_mb: number
  message: string
}

export interface ImageCleanupTargetResult {
  removed: number
  freed_mb: number
  target_free_mb: number
  current_free_mb: number
  done: boolean
  dry_run: boolean
  message: string
}

export interface GalleryCleanupResult {
  removed: number
  removed_size_bytes: number
  retention_days: number
  message: string
}

export type GalleryParams = {
  page?: number
  page_size?: number
  media_type?: GalleryMediaType
  tag?: string
  search?: string
  start_date?: string
  end_date?: string
}

function cleanString(value: unknown): string {
  return String(value || '').trim()
}

function defaultFileBaseUrl(): string {
  if (import.meta.env.VITE_API_URL) return String(import.meta.env.VITE_API_URL)
  if (typeof window !== 'undefined') return window.location.origin
  return ''
}

export function resolveGalleryFileUrl(url: string, baseUrl = defaultFileBaseUrl()): string {
  const raw = cleanString(url)
  if (!raw) return ''
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw)) return raw
  if (raw.startsWith('//')) {
    const protocol = typeof window !== 'undefined' ? window.location.protocol : 'https:'
    return `${protocol}${raw}`
  }
  if (!baseUrl) return raw
  const cleanBase = baseUrl.replace(/\/+$/, '')
  const cleanPath = raw.startsWith('/') ? raw : `/${raw.replace(/^\/+/, '')}`
  return `${cleanBase}${cleanPath}`
}

export const galleryApi = {
  getFiles: (params?: GalleryParams) =>
    apiClient.get<never, GalleryResponse>('/api/images', { params: params || undefined }),

  deleteFiles: (paths: string[]) =>
    apiClient.post<{ paths: string[] }, { removed: number }>('/api/images/delete', {
      paths,
    }),

  downloadZip: (paths: string[]) =>
    apiClient.post<{ paths: string[] }, Blob>('/api/images/download', {
      paths,
    }, {
      responseType: 'blob',
    }),

  updateTags: (path: string, tags: string[]) =>
    apiClient.post<{ path: string; tags: string[] }, { ok: boolean; tags: string[] }>('/api/images/tags', {
      path,
      tags,
    }),

  getStorage: () =>
    apiClient.get<never, ImageStorageStats>('/api/images/storage'),

  compressStorage: () =>
    apiClient.post<never, ImageCompressResult>('/api/images/storage/compress'),

  cleanupToTarget: (targetFreeMb: number, dryRun = false) =>
    apiClient.post<never, ImageCleanupTargetResult>('/api/images/storage/cleanup-to-target', null, {
      params: {
        target_free_mb: targetFreeMb,
        dry_run: dryRun,
      },
    }),

  cleanupExpired: () =>
    apiClient.post<never, GalleryCleanupResult>('/api/images/retention-cleanup'),
}
