import { streamChatCompletion } from '@/api/chatStream'
import { openaiV1Api, type OpenAIV1ChatContentPart, type OpenAIV1ChatMessage } from '@/api/openaiV1'
import {
  DEFAULT_IMAGE_MODEL,
  DEFAULT_IMAGE_QUALITY,
  imageTasksApi,
  normalizeImageCount,
  type ImageTask,
} from '@/api/imageTasks'
import type { StudioComposeMode, StudioConversation, StudioImageForm, StudioMessage } from '@/components/studio/types'
import {
  extractStudioSearchImageGroupsFromText,
  formatStudioSearchResult,
  normalizeStudioSearchImageGroups,
  normalizeStudioSearchSources,
} from './studioSearchView'
import { errorMessage } from '@/lib/errorMessage'

export type StudioChatReplyHandlers = {
  onDelta: (delta: string) => void
}

export type StudioSearchReply = {
  content: string
  sources?: StudioMessage['searchSources']
  imageGroups?: StudioMessage['searchImageGroups']
}

export type StudioImageTaskInput = {
  prompt: string
  files: File[]
  imageForm: StudioImageForm
}

export function buildStudioChatMessages(conversation: StudioConversation, currentAssistantId: string): OpenAIV1ChatMessage[] {
  return conversation.messages
    .filter((message) => {
      if (message.id === currentAssistantId) return false
      if (message.error) return false
      if (!message.content.trim() && !hasChatVisionReferences(message)) return false
      if (message.role === 'assistant' && message.mode !== 'chat' && message.mode !== 'search') return false
      return true
    })
    .map((message): OpenAIV1ChatMessage => ({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: buildStudioChatContextContent(message),
    }))
    .slice(-32)
}

export function studioModeRequestErrorFallback(mode: StudioComposeMode) {
  if (mode === 'image') return '图片生成失败'
  if (mode === 'file') return '文件任务提交失败'
  if (mode === 'search') return '搜索请求失败'
  return '对话请求失败'
}

export function studioModeRetryErrorFallback(mode: StudioComposeMode) {
  if (mode === 'image') return '图片重新生成失败'
  if (mode === 'file') return '文件任务重新提交失败'
  if (mode === 'search') return '搜索重新请求失败'
  return '对话重新生成失败'
}

export function studioErrorMessage(error: unknown, fallback: string) {
  return errorMessage(error, fallback)
}

export async function streamStudioChatReply(input: {
  conversation: StudioConversation
  currentAssistantId: string
  model: string
  reasoningEffort: string
  signal: AbortSignal
  handlers: StudioChatReplyHandlers
}) {
  await streamChatCompletion({
    model: input.model,
    messages: buildStudioChatMessages(input.conversation, input.currentAssistantId),
    reasoningEffort: input.reasoningEffort,
    signal: input.signal,
    onDelta: input.handlers.onDelta,
  })
}

export async function runStudioSearchRequest(prompt: string, ownerId: string): Promise<StudioSearchReply> {
  const result = await openaiV1Api.search(prompt)
  const sources = normalizeStudioSearchSources(result.sources)
  const imageGroups = normalizeStudioSearchImageGroups(result.image_groups) || extractStudioSearchImageGroupsFromText(result.answer)
  return {
    content: formatStudioSearchResult(result, ownerId, sources?.length || 0),
    sources,
    imageGroups,
  }
}

export async function createStudioImageTask(input: StudioImageTaskInput): Promise<ImageTask> {
  const model = input.imageForm.model || DEFAULT_IMAGE_MODEL
  const n = normalizeImageCount(input.imageForm.n)
  const size = input.imageForm.size
  const quality = input.imageForm.quality || DEFAULT_IMAGE_QUALITY

  return input.files.length
    ? imageTasksApi.createEdit({
      prompt: input.prompt,
      files: input.files,
      model,
      n,
      size,
      quality,
    })
    : imageTasksApi.createGeneration({
      prompt: input.prompt,
      model,
      n,
      size,
      quality,
    })
}

function buildStudioChatContextContent(message: StudioMessage): OpenAIV1ChatMessage['content'] {
  const text = buildStudioChatContextText(message)
  if (!hasChatVisionReferences(message)) return text

  const parts: OpenAIV1ChatContentPart[] = []
  if (text.trim()) parts.push({ type: 'text', text })
  for (const image of message.referenceImages || []) {
    if (!image.dataUrl) continue
    parts.push({ type: 'image_url', image_url: { url: image.dataUrl } })
  }
  return parts.length ? parts : text
}

function buildStudioChatContextText(message: StudioMessage) {
  if (message.role === 'user' && message.mode === 'image') return `画图请求：${message.content}`
  if (message.role === 'user' && message.mode === 'search') return `搜索请求：${message.content}`
  if (message.role === 'user' && message.mode === 'file') return `${message.fileKind === 'psd' ? 'PSD' : 'PPT'} 文件请求：${message.content}`
  return message.content
}

function hasChatVisionReferences(message: StudioMessage) {
  return message.role === 'user'
    && message.mode === 'chat'
    && Boolean(message.referenceImages?.some((image) => image.dataUrl))
}
