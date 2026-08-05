import { getAuthToken, handleUnauthorizedResponse } from './client'
import type { OpenAIV1ChatMessage } from './openaiV1'

export interface ChatStreamInput {
  model: string
  messages: OpenAIV1ChatMessage[]
  reasoningEffort?: string
  signal?: AbortSignal
  onDelta?: (delta: string) => void
}

export interface ChatStreamResult {
  content: string
  rawChunks: number
}

function apiUrl(path: string) {
  const baseUrl = String(import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
  return baseUrl ? `${baseUrl}${path}` : path
}

function extractResponseError(payload: unknown, fallback: string) {
  if (typeof payload === 'string') return payload.trim() || fallback
  if (!payload || typeof payload !== 'object') return fallback
  const record = payload as Record<string, any>
  if (typeof record.detail === 'string') return record.detail
  if (record.detail && typeof record.detail === 'object') {
    if (typeof record.detail.message === 'string') return record.detail.message
    if (typeof record.detail.error === 'string') return record.detail.error
  }
  if (record.error && typeof record.error === 'object' && typeof record.error.message === 'string') {
    return record.error.message
  }
  if (typeof record.error === 'string') return record.error
  if (typeof record.message === 'string') return record.message
  return fallback
}

function textFromContent(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(textFromContent).join('')
  if (!value || typeof value !== 'object') return ''
  const record = value as Record<string, unknown>
  return textFromContent(record.text ?? record.content ?? record.value)
}

function extractStreamError(payload: unknown) {
  if (!payload || typeof payload !== 'object') return ''
  const record = payload as Record<string, any>
  const error = record.error
  if (typeof error === 'string') return error
  if (error && typeof error === 'object') {
    return String(error.message || error.error || error.type || '').trim()
  }
  if (record.type === 'error' && record.message) return String(record.message)
  return ''
}

function extractDelta(payload: unknown) {
  if (!payload || typeof payload !== 'object') return ''
  const record = payload as Record<string, any>

  if (typeof record.delta === 'string') return record.delta
  if (record.delta && typeof record.delta === 'object') {
    const direct = textFromContent(record.delta.text ?? record.delta.content)
    if (direct) return direct
  }

  const choice = record.choices?.[0]
  if (!choice || typeof choice !== 'object') return ''
  const delta = choice.delta
  if (delta && typeof delta === 'object') {
    const content = textFromContent(
      delta.content
      ?? delta.text
      ?? delta.output_text
    )
    if (content) return content
  }
  const text = textFromContent(choice.text)
  if (text) return text
  const message = choice.message
  if (message && typeof message === 'object') return textFromContent(message.content)
  return ''
}

function parseSseEvent(eventText: string) {
  const data = eventText
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')
    .trim()
  return data
}

async function responseError(response: Response) {
  const fallback = `请求失败（HTTP ${response.status}）`
  const text = await response.text().catch(() => '')
  if (!text) return fallback
  try {
    return extractResponseError(JSON.parse(text), fallback)
  } catch {
    return extractResponseError(text, fallback)
  }
}

export async function streamChatCompletion(input: ChatStreamInput): Promise<ChatStreamResult> {
  const token = getAuthToken()
  const response = await fetch(apiUrl('/v1/chat/completions'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      model: input.model.trim() || 'auto',
      messages: input.messages,
      stream: true,
      ...(input.reasoningEffort ? { reasoning_effort: input.reasoningEffort } : {}),
    }),
    signal: input.signal,
  })

  if (!response.ok) {
    if (response.status === 401) handleUnauthorizedResponse()
    throw new Error(await responseError(response))
  }

  if (!response.body) {
    throw new Error('浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let content = ''
  let rawChunks = 0

  const handleEvent = (eventText: string) => {
    const data = parseSseEvent(eventText)
    if (!data) return false
    if (data === '[DONE]') return true
    rawChunks += 1
    let payload: unknown
    try {
      payload = JSON.parse(data)
    } catch {
      // Keep the stream alive if the upstream emits a non-JSON extension event.
      return false
    }
    const error = extractStreamError(payload)
    if (error) throw new Error(error)
    const delta = extractDelta(payload)
    if (delta) {
      content += delta
      input.onDelta?.(delta)
    }
    return false
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let boundary = buffer.search(/\r?\n\r?\n/)
    while (boundary >= 0) {
      const eventText = buffer.slice(0, boundary)
      const separatorLength = buffer.startsWith('\r\n\r\n', boundary) ? 4 : 2
      buffer = buffer.slice(boundary + separatorLength)
      if (handleEvent(eventText)) {
        await reader.cancel().catch(() => {})
        return { content, rawChunks }
      }
      boundary = buffer.search(/\r?\n\r?\n/)
    }
  }

  const rest = decoder.decode()
  if (rest) buffer += rest
  if (buffer.trim()) handleEvent(buffer)

  return { content, rawChunks }
}
