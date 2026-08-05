import MarkdownIt from 'markdown-it'
import { highlightStudioCode } from '@/lib/studioMarkdownHighlighter'

export type StudioCodeFormatter = (code: string, language: string) => string

interface StudioMarkdownRenderOptions {
  cache?: boolean
  highlight?: boolean
  codeFormatter?: StudioCodeFormatter | null
}

const MAX_RENDER_CACHE_SIZE = 360
const CODE_FENCE_RE = /(^|\n)[ \t]{0,3}(`{3,}|~{3,})/
const HTML_LIKE_FENCE_RE = /(^|\n)[ \t]{0,3}(`{3,}|~{3,})[ \t]*(html?|xhtml|xml|vue|svg)\b/i
const renderCache = new Map<string, string>()

const markdownWithHighlight = createMarkdownRenderer(true)
const markdownPlain = createMarkdownRenderer(false)

function createMarkdownRenderer(enableHighlight: boolean) {
  const instance = new MarkdownIt({
    html: false,
    linkify: true,
    breaks: true,
  })

  instance.renderer.rules.fence = (tokens, idx, _options, env) => {
    const token = tokens[idx]
    const language = getFenceLanguage(token.info)
    const code = formatFenceCode(
      String(token.content || ''),
      language,
      enableHighlight,
      (env as StudioMarkdownRenderOptions | undefined)?.codeFormatter,
    )
    const highlighted = enableHighlight
      ? highlightStudioCode(code, language)
      : instance.utils.escapeHtml(code)
    const langLabel = instance.utils.escapeHtml(language)

    return `<div class="studio-code-shell" data-language="${langLabel}">`
      + `<div class="studio-code-header">`
      + `<span class="studio-code-language">${langLabel}</span>`
      + `<button type="button" class="studio-code-copy" title="复制代码">复制</button>`
      + `</div>`
      + `<pre class="hljs studio-code-pre">`
      + `<code class="language-${langLabel}">${highlighted}</code>`
      + `</pre>`
      + `</div>`
  }

  return instance
}

export function renderStudioMarkdown(content: string, options: StudioMarkdownRenderOptions = {}) {
  const key = String(content || '')
  const highlight = options.highlight !== false
  const hasFormatter = Boolean(options.codeFormatter)
  if (options.cache === false) return renderPreparedStudioMarkdown(key, highlight, options.codeFormatter)

  const cacheKey = `${highlight ? 'highlight' : 'plain'}:${hasFormatter ? 'formatted' : 'raw'}:${key}`
  const cached = renderCache.get(cacheKey)
  if (cached !== undefined) {
    renderCache.delete(cacheKey)
    renderCache.set(cacheKey, cached)
    return cached
  }

  const rendered = renderPreparedStudioMarkdown(key, highlight, options.codeFormatter)
  renderCache.set(cacheKey, rendered)
  while (renderCache.size > MAX_RENDER_CACHE_SIZE) {
    const firstKey = renderCache.keys().next().value
    if (firstKey === undefined) break
    renderCache.delete(firstKey)
  }
  return rendered
}

function renderPreparedStudioMarkdown(
  content: string,
  highlight: boolean,
  codeFormatter?: StudioCodeFormatter | null,
) {
  const renderer = highlight ? markdownWithHighlight : markdownPlain
  return renderer.render(content, { codeFormatter })
}

function getFenceLanguage(info: string) {
  return String(info || '').trim().split(/\s+/)[0] || 'text'
}

function formatFenceCode(
  code: string,
  language: string,
  enableFormat: boolean,
  codeFormatter?: StudioCodeFormatter | null,
) {
  if (!enableFormat || !codeFormatter) return code
  if (!isHtmlLikeLanguage(language)) return code

  try {
    return codeFormatter(code, language)
  } catch {
    return code
  }
}

export function needsStudioCodeFormatter(content: string) {
  const text = String(content || '')
  if (!text) return false
  return HTML_LIKE_FENCE_RE.test(text)
}

export function hasStudioCodeContent(content: string) {
  const text = String(content || '')
  if (!text) return false
  return CODE_FENCE_RE.test(text)
}

function isHtmlLikeLanguage(language: string) {
  return /^(html?|xhtml|xml|vue|svg)$/i.test(String(language || '').trim().replace(/^language-/, ''))
}
