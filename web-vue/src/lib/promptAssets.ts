function normalizePromptAssetUrl(url: string) {
  return String(url || '').trim()
}

export function promptPreviewDisplayUrl(url: string) {
  const normalized = normalizePromptAssetUrl(url)
  if (!normalized) return ''
  if (/^(https?:|data:|blob:)/i.test(normalized)) return normalized
  if (normalized.startsWith('/')) return normalized
  return ''
}

export function firstPromptPreviewUrl(input: {
  preview?: string
  reference_image_urls?: string[]
}, brokenUrls?: Set<string>) {
  const candidates = [input.preview, ...(input.reference_image_urls || [])]
  for (const candidate of candidates) {
    const normalized = normalizePromptAssetUrl(candidate || '')
    if (!normalized || brokenUrls?.has(normalized)) continue
    const displayUrl = promptPreviewDisplayUrl(normalized)
    if (displayUrl) return displayUrl
  }
  return ''
}

export function markPromptPreviewBroken(event: Event, primaryUrl: string, onBroken?: (url: string) => void) {
  const image = event.currentTarget as HTMLImageElement | null
  const normalized = normalizePromptAssetUrl(primaryUrl)
  if (normalized) onBroken?.(normalized)
  if (image) image.hidden = true
}
