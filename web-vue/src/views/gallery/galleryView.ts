import type { GalleryFile, ImageStorageStats } from '@/api/gallery'

export const galleryPageSizeOptions = [24, 48, 96] as const

type GalleryCounts = {
  all: number
  image: number
}

type GalleryMetricItem = {
  label: string
  value: string | number
  icon: string
  iconClass: string
  iconBgClass: string
}

type GalleryStorageItem = {
  label: string
  value: string
}

export type GalleryFileCardSignatureInput = {
  selected: boolean
  previewable: boolean
  copied: boolean
  imageUrl: string
  storageLabel: string
  sizeLabel: string
  dimensions: string
  timeRemaining: string
}

function signatureValue(value: unknown): string {
  return String(value ?? '').trim().replaceAll('|', '/')
}

function boundedSignatureText(value: unknown, limit = 160): string {
  const text = signatureValue(value)
  if (text.length <= limit) return text
  return `${text.length}:${text.slice(0, limit)}:${text.slice(-24)}`
}

export function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export function formatMb(value: number): string {
  return formatSize(Number(value || 0) * 1024 * 1024)
}

export function formatTimeRemaining(seconds: number): string {
  if (seconds <= 0) return '已过期'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}天 ${hours}小时`
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`
}

export function formatDimensions(file: GalleryFile): string {
  return file.width && file.height ? `${file.width}x${file.height}` : ''
}

export function storageLabel(file: GalleryFile): string {
  if (file.storage === 'both') return '本地+云'
  if (file.storage === 'webdav') return '云端'
  return '本地'
}

export function galleryFileCardSignature(file: GalleryFile, input: GalleryFileCardSignatureInput): string {
  return [
    file.path,
    boundedSignatureText(file.filename),
    boundedSignatureText(input.imageUrl, 220),
    input.selected ? 1 : 0,
    input.previewable ? 1 : 0,
    input.copied ? 1 : 0,
    file.expired ? 1 : 0,
    input.storageLabel,
    input.sizeLabel,
    input.dimensions,
    input.timeRemaining,
    file.tags.map((tag) => boundedSignatureText(tag, 64)).join(','),
  ].map(signatureValue).join('|')
}

export function canPreviewFile(file: GalleryFile, brokenPaths: ReadonlySet<string>): boolean {
  return file.available && !brokenPaths.has(file.path)
}

export function parseTags(value: string): string[] {
  return Array.from(new Set(value.split(/[,\s，、]+/).map((tag) => tag.trim()).filter(Boolean)))
}

export function buildTagOptions(tags: readonly string[]) {
  return [
    { label: '全部标签', value: 'all' },
    ...tags.map((tag) => ({ label: tag, value: tag })),
  ]
}

export function formatPaginationSummary(currentPage: number, pageCount: number, totalItems: number): string {
  return `第 ${currentPage} / ${pageCount} 页，共 ${totalItems} 张`
}

export function formatStorageUsagePercent(stats: ImageStorageStats | null | undefined): string {
  if (!stats || stats.disk_total_mb <= 0) return '-'
  const percent = Math.min(100, Math.max(0, (stats.disk_used_mb / stats.disk_total_mb) * 100))
  return `${percent.toFixed(1)}%`
}

export function storageUsageBarWidth(percent: string): string {
  return percent === '-' ? '0%' : percent
}

export function buildStorageCardItems(stats: ImageStorageStats | null | undefined, totalSize: number): GalleryStorageItem[] {
  return [
    { label: '磁盘总量', value: stats ? formatMb(stats.disk_total_mb) : '-' },
    { label: '已用空间', value: stats ? formatMb(stats.disk_used_mb) : '-' },
    { label: '剩余空间', value: stats ? formatMb(stats.disk_free_mb) : '-' },
    { label: '图库占用', value: stats ? formatSize(stats.image_size_bytes) : formatSize(totalSize) },
  ]
}

export function buildStorageSummaryItems(
  stats: ImageStorageStats | null | undefined,
  counts: GalleryCounts,
  totalItems: number,
  totalSize: number,
): GalleryStorageItem[] {
  return [
    { label: '图库文件', value: `${stats ? stats.image_count : counts.all} 个` },
    { label: '当前筛选结果', value: `${totalItems} 个 / ${formatSize(totalSize)}` },
  ]
}

export function buildGalleryMetricItems(
  totalItems: number,
  storageStats: ImageStorageStats | null | undefined,
  counts: GalleryCounts,
  totalSize: number,
): GalleryMetricItem[] {
  return [
    { label: '当前视图', value: totalItems, icon: 'lucide:image', iconClass: 'text-cyan-600', iconBgClass: 'bg-transparent' },
    { label: '图库总量', value: storageStats ? storageStats.image_count : counts.all, icon: 'lucide:archive', iconClass: 'text-violet-600', iconBgClass: 'bg-transparent' },
    { label: '当前占用', value: formatSize(totalSize), icon: 'lucide:database', iconClass: 'text-emerald-600', iconBgClass: 'bg-transparent' },
    { label: '磁盘剩余', value: storageStats ? formatSize(storageStats.disk_free_mb * 1024 * 1024) : '-', icon: 'lucide:hard-drive', iconClass: 'text-amber-600', iconBgClass: 'bg-transparent' },
  ]
}
