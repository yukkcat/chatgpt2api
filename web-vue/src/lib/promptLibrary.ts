import type { PromptLibraryItem, PromptSource } from '@/api/prompts'

export const ALL_PROMPT_SOURCE = 'all'
export const ALL_PROMPT_CATEGORY = '全部'

export function promptCategoryLabel(item: Pick<PromptLibraryItem, 'category' | 'sub_category'>) {
  return [item.category, item.sub_category].filter(Boolean).join(' / ')
}

export function cleanPromptDisplayText(value: unknown) {
  const text = String(value || '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")

  return text
    .replace(/<\s*br\s*\/?>/gi, ' ')
    .replace(/<\/(p|div|li|h[1-6])>/gi, ' ')
    .replace(/<img\b[^>\n]*(?:>|$)/gi, ' ')
    .replace(/!\[[^\]]*]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)]\([^)]*\)/g, '$1')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function promptDisplaySummary(item: PromptLibraryItem) {
  return (
    cleanPromptDisplayText(item.description) ||
    cleanPromptDisplayText(item.prompt) ||
    cleanPromptDisplayText(promptCategoryLabel(item)) ||
    cleanPromptDisplayText(item.source_name) ||
    '图片提示词'
  )
}

export function promptSourceLabel(source: PromptSource) {
  return source.name || source.url || source.id
}

export function promptSyncTime(value: string) {
  if (!value) return '未同步'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未知'
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function promptSearchText(item: PromptLibraryItem) {
  return [
    item.title,
    cleanPromptDisplayText(item.description),
    item.preview,
    item.link,
    cleanPromptDisplayText(item.prompt),
    item.category,
    item.sub_category,
    item.source_name,
    ...item.tags,
  ].join('\n').toLowerCase()
}

export function filterPromptItems(
  items: PromptLibraryItem[],
  filters: {
    keyword?: string
    sourceId?: string
    category?: string
  },
) {
  const needle = String(filters.keyword || '').trim().toLowerCase()
  const sourceId = filters.sourceId || ALL_PROMPT_SOURCE
  const category = filters.category || ALL_PROMPT_CATEGORY
  return items.filter((item) => {
    if (sourceId !== ALL_PROMPT_SOURCE && item.source_id !== sourceId) return false
    if (category !== ALL_PROMPT_CATEGORY && promptCategoryLabel(item) !== category) return false
    if (!needle) return true
    return promptSearchText(item).includes(needle)
  })
}

export function categoryOptionsFor(items: PromptLibraryItem[]) {
  const categories = new Set<string>()
  for (const item of items) {
    const label = promptCategoryLabel(item)
    if (label) categories.add(label)
  }
  return [ALL_PROMPT_CATEGORY, ...Array.from(categories).sort((a, b) => a.localeCompare(b, 'zh-CN'))]
}
