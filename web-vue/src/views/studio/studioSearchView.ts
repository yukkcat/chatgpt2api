import type { OpenAIV1SearchImageGroup, OpenAIV1SearchResult, OpenAIV1SearchSource } from '@/api/openaiV1'
import type { StudioSearchImageGroup, StudioSearchSource } from '@/components/studio/types'

export type StudioLegacySearchResult = {
  content: string
  sources?: StudioSearchSource[]
}

export function cleanStudioText(value: unknown) {
  return String(value ?? '').trim()
}

export function normalizeStudioSearchImageGroups(value: unknown): StudioSearchImageGroup[] | undefined {
  if (!Array.isArray(value)) return undefined
  const groups = value
    .map((item): StudioSearchImageGroup | null => {
      if (!item || typeof item !== 'object') return null
      const raw = item as OpenAIV1SearchImageGroup & { aspectRatio?: unknown; numPerQuery?: unknown; query?: unknown; queries?: unknown }
      const rawQueries = Array.isArray(raw.queries)
        ? raw.queries
        : Array.isArray(raw.query)
          ? raw.query
          : typeof raw.query === 'string'
            ? [raw.query]
            : []
      const queries = rawQueries.map((query) => cleanStudioText(query)).filter(Boolean).slice(0, 6)
      if (!queries.length) return null
      const aspectRatio = cleanStudioText(raw.aspect_ratio ?? raw.aspectRatio)
      const numPerQueryValue = Number(raw.num_per_query ?? raw.numPerQuery)
      return {
        queries,
        aspectRatio: aspectRatio || undefined,
        numPerQuery: Number.isFinite(numPerQueryValue) && numPerQueryValue > 0 ? numPerQueryValue : undefined,
      }
    })
    .filter((item): item is StudioSearchImageGroup => Boolean(item))
    .slice(0, 4)
  return groups.length ? groups : undefined
}

export function extractStudioSearchImageGroupsFromText(value: unknown): StudioSearchImageGroup[] | undefined {
  const text = cleanStudioText(value)
  if (!text) return undefined
  const groups: unknown[] = []
  text.replace(/\ue200image_group\ue202([^\ue201]*)\ue201/g, (_match, payload: string) => {
    try {
      groups.push(JSON.parse(payload || '{}'))
    } catch {
      // ignore malformed upstream marker
    }
    return ''
  })
  return normalizeStudioSearchImageGroups(groups)
}

export function normalizeStudioSearchSources(value: unknown): StudioSearchSource[] | undefined {
  if (!Array.isArray(value)) return undefined
  const sources = value
    .map((item): StudioSearchSource | null => {
      if (!item || typeof item !== 'object') return null
      const raw = item as OpenAIV1SearchSource
      const source = {
        title: cleanStudioText(raw.title),
        url: cleanStudioText(raw.url),
        snippet: cleanStudioText(raw.snippet),
      }
      return source.title || source.url || source.snippet ? source : null
    })
    .filter((item): item is StudioSearchSource => Boolean(item))
  return sources.length ? sources : undefined
}

export function splitStudioLegacySearchResult(content: string): StudioLegacySearchResult {
  const match = content.match(/\n{2,}\*\*来源\*\*\n([\s\S]+)$/)
  if (!match || typeof match.index !== 'number') return { content }
  const sources = match[1]
    .split('\n')
    .map(parseStudioLegacySearchSourceLine)
    .filter((source): source is StudioSearchSource => Boolean(source))
  if (!sources.length) return { content }
  return { content: content.slice(0, match.index).trim(), sources }
}

export function cleanStudioSearchAnswer(value: unknown) {
  return cleanStudioText(value)
    .replace(/\ue200cite\ue202([^\ue201]*)\ue201/g, (_match, citationId: string) => {
      const matched = String(citationId || '').match(/search(\d+)/)
      return matched ? `[${Number(matched[1]) + 1}]` : ''
    })
    .replace(/\ue200image_group\ue202([^\ue201]*)\ue201/g, '')
    .replace(/\ue200(?!cite\ue202|image_group\ue202)[a-zA-Z0-9_]+\ue202[^\ue201]*\ue201/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function linkStudioSearchCitations(content: string, ownerId: string, sourceCount: number) {
  const encodedOwnerId = encodeURIComponent(ownerId)
  return content.replace(/\[(\d{1,2})\](?!\()/g, (matched, rawIndex: string) => {
    const index = Number(rawIndex)
    if (!Number.isInteger(index) || index < 1) return matched
    if (!sourceCount || index > sourceCount) return ''
    return `[${index}](studio-citation:${encodedOwnerId}:${index})`
  }).replace(/\s+([，。！？；：,.!?;:])/g, '$1')
}

export function formatStudioSearchResult(result: OpenAIV1SearchResult, ownerId: string, sourceCount: number) {
  const answer = cleanStudioSearchAnswer(result.answer) || '搜索完成，但上游没有返回摘要。'
  return linkStudioSearchCitations(answer, ownerId, sourceCount)
}

function parseStudioLegacySearchSourceLine(line: string): StudioSearchSource | null {
  const raw = cleanStudioText(line)
  if (!raw) return null
  const match = raw.match(/^\d+\.\s+(?:\[([^\]]+)\]\(([^)]+)\)|(.+?))(?:\s+—\s+(.+))?$/)
  if (!match) return null
  const title = cleanStudioText((match[1] || match[3] || '').replace(/\\([\[\]])/g, '$1'))
  const url = cleanStudioText(match[2]).replace(/%20/g, ' ').replace(/%29/g, ')')
  const snippet = cleanStudioText(match[4])
  return title || url || snippet ? { title, url, snippet } : null
}
