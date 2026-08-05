import { normalizeImageCount } from '@/api/imageTasks'
import type {
  StudioConversation,
  StudioConversationBadgeState,
  StudioImageCompareSource,
  StudioMessage,
  StudioMessageStatus,
  StudioReferenceImage,
} from '@/components/studio/types'
import { getJsonPreference, preferenceKeys, setJsonPreference } from '@/lib/preferences'
import {
  cleanStudioSearchAnswer,
  cleanStudioText,
  extractStudioSearchImageGroupsFromText,
  linkStudioSearchCitations,
  normalizeStudioSearchImageGroups,
  normalizeStudioSearchSources,
  splitStudioLegacySearchResult,
} from './studioSearchView'

export type StudioImageTaskMessageEntry = {
  conversation: StudioConversation
  message: StudioMessage
}

export type StudioFileTaskMessageEntry = {
  conversation: StudioConversation
  message: StudioMessage
}

export type StudioConversationLookup = {
  byId: Map<string, StudioConversation>
  validIds: Set<string>
}

export type StudioConversationRuntimeIndex = {
  pendingImageTaskIds: string[]
  pendingFileTaskIds: string[]
  runningCounts: Record<string, number>
  imageTaskMessageEntries: StudioImageTaskMessageEntry[]
  fileTaskMessageEntries: StudioFileTaskMessageEntry[]
}

export function createStudioId(prefix: string) {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function buildStudioConversationTitle(content: string) {
  const title = content.trim().replace(/\s+/g, ' ')
  return title.length > 18 ? `${title.slice(0, 18)}...` : title || '新对话'
}

export function loadStudioConversations(): StudioConversation[] {
  const items = getJsonPreference<unknown[]>(preferenceKeys.studioConversations, [])
  if (!Array.isArray(items)) return []
  return items.map(normalizeStudioConversation).filter((item): item is StudioConversation => Boolean(item)).slice(0, 80)
}

export function loadStudioConversationNotices(): Record<string, StudioConversationBadgeState> {
  const raw = getJsonPreference<Record<string, unknown>>(preferenceKeys.studioConversationBadges, {})
  const notices: Record<string, StudioConversationBadgeState> = {}
  Object.entries(raw || {}).forEach(([id, state]) => {
    if (state === 'done' || state === 'error') notices[id] = state
  })
  return notices
}

export function persistStudioConversations(conversations: StudioConversation[]) {
  const payload = conversations.slice(0, 80).map((conversation) => ({
    ...conversation,
    messages: conversation.messages.slice(-160).map((message) => ({
      ...message,
      status: message.status === 'streaming' || message.status === 'sending' ? 'done' : message.status,
    })),
  }))
  setJsonPreference(preferenceKeys.studioConversations, payload)
}

export function persistStudioConversationNotices(
  notices: Record<string, StudioConversationBadgeState>,
  validIds: Set<string>,
) {
  const payload = Object.fromEntries(
    Object.entries(notices).filter(([id, state]) => validIds.has(id) && (state === 'done' || state === 'error')),
  )
  setJsonPreference(preferenceKeys.studioConversationBadges, payload)
}

export function buildStudioConversationLookup(conversations: StudioConversation[]): StudioConversationLookup {
  const byId = new Map<string, StudioConversation>()
  const validIds = new Set<string>()

  conversations.forEach((conversation) => {
    byId.set(conversation.id, conversation)
    validIds.add(conversation.id)
  })

  return { byId, validIds }
}

export function buildStudioConversationRuntimeIndex(conversations: StudioConversation[]): StudioConversationRuntimeIndex {
  const pendingImageIds = new Set<string>()
  const pendingFileIds = new Set<string>()
  const runningCounts: Record<string, number> = {}
  const imageTaskMessageEntries: StudioImageTaskMessageEntry[] = []
  const fileTaskMessageEntries: StudioFileTaskMessageEntry[] = []

  conversations.forEach((conversation) => {
    let running = 0
    conversation.messages.forEach((message) => {
      if (message.mode === 'image' && message.taskId) imageTaskMessageEntries.push({ conversation, message })
      if (message.mode === 'file' && message.fileTaskId && !message.fileTaskDeleted) {
        fileTaskMessageEntries.push({ conversation, message })
      }
      if (isStudioImageMessageRunning(message)) {
        running += 1
        if (message.taskId) pendingImageIds.add(message.taskId)
      } else if (isStudioFileMessageRunning(message)) {
        running += 1
        if (message.fileTaskId) pendingFileIds.add(message.fileTaskId)
      } else if (message.status === 'sending' || message.status === 'streaming') {
        running += 1
      }
    })

    if (running > 0) runningCounts[conversation.id] = running
  })

  return {
    pendingImageTaskIds: Array.from(pendingImageIds).slice(0, 160),
    pendingFileTaskIds: Array.from(pendingFileIds).slice(0, 160),
    runningCounts,
    imageTaskMessageEntries,
    fileTaskMessageEntries,
  }
}

export function isStudioImageMessageRunning(message: StudioMessage) {
  return message.mode === 'image' && (message.status === 'queued' || message.status === 'running')
}

export function isStudioFileMessageRunning(message: StudioMessage) {
  return message.mode === 'file' && (message.status === 'queued' || message.status === 'running')
}

function normalizeStudioConversation(item: unknown): StudioConversation | null {
  if (!item || typeof item !== 'object') return null
  const raw = item as Partial<StudioConversation>
  const messages = Array.isArray(raw.messages)
    ? raw.messages.map(normalizeStudioMessage).filter((message): message is StudioMessage => Boolean(message)).slice(-160)
    : []
  return {
    id: cleanStudioText(raw.id) || createStudioId('studio'),
    title: cleanStudioText(raw.title) || '新对话',
    createdAt: cleanStudioText(raw.createdAt) || new Date().toISOString(),
    updatedAt: cleanStudioText(raw.updatedAt) || new Date().toISOString(),
    messages,
  }
}

function normalizeStudioMessage(item: unknown): StudioMessage | null {
  if (!item || typeof item !== 'object') return null
  const raw = item as Partial<StudioMessage>
  const content = cleanStudioText(raw.content)
  const taskId = cleanStudioText(raw.taskId)
  const fileTaskId = cleanStudioText(raw.fileTaskId)
  const fileTaskDeleted = raw.fileTaskDeleted === true
  if (!content && !taskId && !fileTaskId && !fileTaskDeleted) return null
  const id = cleanStudioText(raw.id) || createStudioId('message')
  const mode = raw.mode === 'chat' || raw.mode === 'search' || raw.mode === 'file' ? raw.mode : 'image'
  const normalizedContent = mode === 'search' ? cleanStudioSearchAnswer(content) : content
  const migratedSearchResult = mode === 'search'
    ? splitStudioLegacySearchResult(normalizedContent)
    : { content: normalizedContent, sources: undefined }
  const searchSources = normalizeStudioSearchSources(raw.searchSources) || migratedSearchResult.sources
  const searchImageGroups = mode === 'search'
    ? normalizeStudioSearchImageGroups(raw.searchImageGroups) || extractStudioSearchImageGroupsFromText(content)
    : undefined

  return {
    id,
    role: raw.role === 'assistant' ? 'assistant' : 'user',
    mode,
    content: mode === 'search'
      ? linkStudioSearchCitations(migratedSearchResult.content, id, searchSources?.length || 0)
      : migratedSearchResult.content,
    createdAt: cleanStudioText(raw.createdAt) || new Date().toISOString(),
    status: normalizeStudioMessageStatus(raw.status),
    model: cleanStudioText(raw.model) || undefined,
    imageSize: cleanStudioText(raw.imageSize) || undefined,
    imageCount: Number.isFinite(Number(raw.imageCount)) ? normalizeImageCount(raw.imageCount) : undefined,
    taskId: taskId || undefined,
    fileTaskId: fileTaskId || undefined,
    fileTaskDeleted: mode === 'file' && fileTaskDeleted ? true : undefined,
    fileKind: mode === 'file' && raw.fileKind === 'psd' ? 'psd' : mode === 'file' ? 'ppt' : undefined,
    error: cleanStudioText(raw.error) || undefined,
    attachments: Array.isArray(raw.attachments) ? raw.attachments.map(cleanStudioText).filter(Boolean).slice(0, 8) : undefined,
    referenceImages: normalizeStudioReferenceImages(raw.referenceImages),
    inpaintSource: normalizeStudioImageCompareSource(raw.inpaintSource),
    searchSources,
    searchImageGroups,
  }
}

function normalizeStudioImageCompareSource(value: unknown): StudioImageCompareSource | undefined {
  if (!value || typeof value !== 'object') return undefined
  const raw = value as Partial<StudioImageCompareSource>
  const src = cleanStudioText(raw.src)
  if (!src) return undefined
  return {
    src,
    name: cleanStudioText(raw.name) || '原图',
    localPath: cleanStudioText(raw.localPath) || undefined,
  }
}

function normalizeStudioReferenceImages(value: unknown): StudioReferenceImage[] | undefined {
  if (!Array.isArray(value)) return undefined
  const images = value
    .map((item, index) => {
      if (!item || typeof item !== 'object') return null
      const raw = item as Partial<StudioReferenceImage>
      const dataUrl = cleanStudioText(raw.dataUrl)
      if (!dataUrl) return null
      return {
        id: cleanStudioText(raw.id) || createStudioId('source'),
        name: cleanStudioText(raw.name) || `参考图 ${index + 1}`,
        type: cleanStudioText(raw.type) || 'image/png',
        size: Number.isFinite(Number(raw.size)) ? Number(raw.size) : 0,
        dataUrl,
      }
    })
    .filter((item): item is StudioReferenceImage => Boolean(item))
    .slice(0, 8)
  return images.length ? images : undefined
}

function normalizeStudioMessageStatus(value: unknown): StudioMessageStatus | undefined {
  if (['sending', 'streaming', 'queued', 'running', 'done', 'error'].includes(String(value))) {
    return String(value) as StudioMessageStatus
  }
  return undefined
}
