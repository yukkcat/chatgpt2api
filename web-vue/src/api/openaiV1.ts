import apiClient from './client'

export interface OpenAIV1SearchSource {
  title: string
  url: string
  snippet: string
  source_type: string
}

export interface OpenAIV1SearchImageGroup {
  queries: string[]
  aspect_ratio?: string
  num_per_query?: number
}

export interface OpenAIV1SearchResult {
  conversation_id: string
  status: string
  answer: string
  sources: OpenAIV1SearchSource[]
  image_groups: OpenAIV1SearchImageGroup[]
  assistant_message_id: string
  create_time: number
  _account_email?: string
}

export type OpenAIV1ChatContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string } }
  | { type: 'input_image'; image_url?: string; url?: string }

export interface OpenAIV1ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string | OpenAIV1ChatContentPart[]
}

export const openaiV1Api = {
  search: (prompt: string) => apiClient.post<{ prompt: string }, OpenAIV1SearchResult>('/v1/search', { prompt }),
}
