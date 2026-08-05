<template>
  <section class="studio-chat-panel" :class="{ 'is-fullscreen': fullscreen }">
    <div ref="scrollEl" class="studio-chat-scroll custom-scrollbar" @scroll="handleScroll">
      <div v-if="!displayedConversation || !displayedConversation.messages.length" class="studio-chat-empty">
        <h1>对话画图</h1>
        <p>输入文字可以直接对话；切到画图后，在同一个窗口里生成图片、上传参考图和继续编辑。</p>
      </div>

      <div v-else ref="turnsEl" class="studio-turns">
        <div v-if="hiddenMessageCount > 0" class="studio-load-earlier-row">
          <button type="button" class="studio-load-earlier-button" @click="showOlderMessages">
            显示更早消息（{{ hiddenMessageCount }} 条）
          </button>
        </div>

        <StudioMessageItem
          v-for="message in messageViews"
          :key="message.id"
          v-memo="[message.memoKey]"
          :message="message"
          @action="handleMessageAction"
          @toggle-expanded="toggleMessageExpanded"
          @open-search-sources="openSearchSourcePanel"
          @citation-click="scrollToCitationSource"
          @preview="forwardPreview"
          @reference-image="forwardReferenceImage"
          @inpaint-image="forwardInpaintImage"
          @compare-image="forwardCompareImage"
        />
      </div>
    </div>

    <button
      v-if="showScrollLatest"
      type="button"
      class="studio-scroll-latest"
      aria-label="滚动到最新消息"
      title="滚动到最新消息"
      @click="scrollToBottom"
    >
      <Icon icon="lucide:arrow-down" class="h-5 w-5" />
    </button>

    <Transition name="studio-search-drawer-fade">
      <div
        v-if="activeSearchSourceMessage"
        class="studio-search-drawer-backdrop"
        @click="closeSearchSourcePanel"
      ></div>
    </Transition>

    <Transition name="studio-search-drawer-slide">
      <aside
        v-if="activeSearchSourceMessage"
        class="studio-search-drawer"
        role="dialog"
        aria-label="参考来源"
      >
        <header class="studio-search-drawer-header">
          <div>
            <strong>参考来源</strong>
            <small>{{ activeSearchSourceMessage.searchSources?.length || 0 }} 条网页结果</small>
          </div>
          <CloseButton label="关闭参考来源" @click="closeSearchSourcePanel" />
        </header>

        <div class="studio-search-drawer-body custom-scrollbar">
          <a
            v-for="(source, sourceIndex) in activeSearchSourceMessage.searchSources"
            :key="`${activeSearchSourceMessage.id}-panel-source-${sourceIndex}`"
            :id="searchSourceDomId(activeSearchSourceMessage.id, sourceIndex)"
            class="studio-search-source-card"
            :class="{ 'is-static': !source.url, 'is-highlighted': highlightedSearchSourceId === searchSourceDomId(activeSearchSourceMessage.id, sourceIndex) }"
            :href="source.url || undefined"
            :target="source.url ? '_blank' : undefined"
            :rel="source.url ? 'noreferrer' : undefined"
            @click="!source.url && $event.preventDefault()"
          >
            <span class="studio-search-source-index">{{ sourceIndex + 1 }}</span>
            <span class="studio-search-source-body">
              <strong>{{ sourceTitle(source, sourceIndex) }}</strong>
              <small v-if="sourceHost(source.url)">{{ sourceHost(source.url) }}</small>
              <em v-if="source.snippet">{{ source.snippet }}</em>
            </span>
            <Icon v-if="source.url" icon="lucide:external-link" class="studio-search-source-open h-3.5 w-3.5" />
          </a>
        </div>
      </aside>
    </Transition>
  </section>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, ref, shallowRef, watch, type CSSProperties } from 'vue'
import {
  imageAssetUrl,
  parseImageSize,
  type ImageTask,
  type ImageTaskAsset,
} from '@/api/imageTasks'
import type { EditableFileTask } from '@/api/editableFileTasks'
import { splitStudioSearchCalls } from '@/lib/studioToolCalls'
import { CloseButton } from 'nanocat-ui'
import StudioMessageItem, {
  type StudioMessageActionKey,
  type StudioMessageView,
} from './StudioMessageItem.vue'
import type {
  StudioConversation,
  StudioImageAssetView,
  StudioImageCompareSource,
  StudioMessage,
  StudioReferenceImage,
  StudioSearchImageGroup,
  StudioSearchSource,
} from './types'

const props = defineProps<{
  conversation: StudioConversation | null
  conversationsCount: number
  taskById: Map<string, ImageTask>
  fileTaskById: Map<string, EditableFileTask>
  fullscreen: boolean
}>()

const emit = defineEmits<{
  create: []
  'open-history': []
  'toggle-fullscreen': []
  retry: [message: StudioMessage]
  edit: [message: StudioMessage]
  resend: [message: StudioMessage]
  'resume-image-task': [message: StudioMessage]
  'retry-assistant': [message: StudioMessage]
  'delete-message': [messageId: string]
  'copy-message': [content: string]
  preview: [src: string, name: string, localPath?: string]
  'reference-image': [asset: StudioImageAssetView, name: string, message: StudioMessage]
  'inpaint-image': [asset: StudioImageAssetView, name: string, message: StudioMessage]
  'compare-image': [source: StudioImageCompareSource, asset: StudioImageAssetView, name: string]
}>()

type MessageViewSignatureValue = string | number | boolean | null | undefined
type MessageViewSignature = MessageViewSignatureValue[]

const INITIAL_MESSAGE_LIMIT = 32
const MESSAGE_BATCH_SIZE = 24
const MAX_MESSAGE_VIEW_CACHE_SIZE = 480
const EMPTY_IMAGE_ASSETS: readonly ImageTaskAsset[] = []
const SINGLE_IMAGE_MAX_WIDTH_REM = 18
const SINGLE_IMAGE_MIN_WIDTH_REM = 11.5
const MULTI_IMAGE_MAX_WIDTH_REM = 26
const STICK_TO_BOTTOM_DISTANCE_PX = 160

const scrollEl = ref<HTMLElement | null>(null)
const turnsEl = ref<HTMLElement | null>(null)
const showScrollLatest = ref(false)
const visibleMessageLimit = ref(INITIAL_MESSAGE_LIMIT)
const expandedMessageIds = ref<Set<string>>(new Set())
const collapsedMessageIds = ref<Set<string>>(new Set())
const highlightedSearchSourceId = ref('')
const searchPanelMessageId = ref('')
const displayedConversation = shallowRef<StudioConversation | null>(props.conversation)
const messageViewCache = new Map<string, { signature: MessageViewSignature; revision: number; view: StudioMessageView }>()
let scrollLatestFrameId: number | null = null
let scrollLatestToken = 0
let searchSourceHighlightTimer: number | null = null
let turnsResizeObserver: ResizeObserver | null = null
let stickToBottom = true

const allMessages = computed(() => displayedConversation.value?.messages || [])
const visibleMessages = computed(() => {
  const messages = allMessages.value
  if (messages.length <= visibleMessageLimit.value) return messages
  const recentStart = Math.max(0, messages.length - visibleMessageLimit.value)
  return messages.filter((message, index) => index >= recentStart || isLiveMessage(message))
})
const hiddenMessageCount = computed(() => Math.max(0, allMessages.value.length - visibleMessages.value.length))
const messageViews = computed(() => {
  return visibleMessages.value.map((message) => buildMessageView(message))
})
const activeSearchSourceMessage = computed(() => {
  if (!searchPanelMessageId.value) return null
  return allMessages.value.find((message) => message.id === searchPanelMessageId.value && message.searchSources?.length) || null
})

function buildMessageView(message: StudioMessage): StudioMessageView {
  const task = message.taskId ? props.taskById.get(message.taskId) : undefined
  const fileTask = message.fileTaskId ? props.fileTaskById.get(message.fileTaskId) : undefined
  const taskAssets = task?.results.length ? task.results : EMPTY_IMAGE_ASSETS
  const isImageMessage = message.role === 'assistant' && message.mode === 'image'
  const imageSlotCount = computeImageSlotCount(message, task)
  const isCollapsible = computeIsCollapsibleMessage(message)
  const isCollapsed = isCollapsible ? computeIsMessageCollapsed(message) : false
  const parsedContent = splitStudioSearchCalls(buildMarkdownDisplayContent(message))
  const markdownContent = parsedContent.content
  const searchQueries = parsedContent.queries
  const signature = messageViewSignature(message, task, fileTask, taskAssets, imageSlotCount, isCollapsed, isCollapsible, markdownContent, searchQueries)
  const cached = messageViewCache.get(message.id)
  if (cached && sameMessageViewSignature(cached.signature, signature)) {
    messageViewCache.delete(message.id)
    messageViewCache.set(message.id, cached)
    return cached.view
  }
  const assets = buildImageAssetViews(taskAssets)
  const isPendingImageMessage = isImageMessage && (task ? !task.terminal : isLocalImageMessagePending(message))
  const pendingSlotCount = isPendingImageMessage
    ? (task ? task.pending_count : imageSlotCount)
    : 0
  const pendingSlotStart = task ? task.succeeded_count : 0
  const failedSlotCount = task?.terminal ? task.failed_count : 0
  const failedSlotStart = task ? task.succeeded_count : 0
  const revision = (cached?.revision || 0) + 1
  const view: StudioMessageView = {
    ...message,
    memoKey: `${message.id}:${revision}`,
    task,
    fileTask,
    assets,
    isImageMessage,
    isPendingImageMessage,
    isSingleImageResult: isImageMessage && !isPendingImageMessage && imageSlotCount === 1 && assets.length === 1,
    imageSlotCount,
    pendingSlots: Array.from({ length: pendingSlotCount }, (_, index) => pendingSlotStart + index),
    failedSlots: Array.from({ length: failedSlotCount }, (_, index) => failedSlotStart + index),
    imagePendingStageText: task?.stage_label || '正在提交',
    primaryMessage: task?.public_error || '',
    imagePreviewStyle: isImageMessage ? buildImagePreviewStyle(message, task, imageSlotCount, assets) : undefined,
    isCollapsible,
    isCollapsed,
    markdownContent,
    searchQueries,
  }
  messageViewCache.set(message.id, { signature, revision, view })
  trimStringKeyCache(messageViewCache, MAX_MESSAGE_VIEW_CACHE_SIZE)
  return view
}

function messageViewSignature(
  message: StudioMessage,
  task: ImageTask | undefined,
  fileTask: EditableFileTask | undefined,
  taskAssets: readonly ImageTaskAsset[],
  imageSlotCount: number,
  isCollapsed: boolean,
  isCollapsible: boolean,
  markdownContent: string,
  searchQueries: string[],
): MessageViewSignature {
  return [
    message.id,
    message.role,
    message.mode,
    compactStringSignature(message.content),
    message.createdAt,
    message.status,
    message.model,
    message.imageSize,
    message.imageCount,
    message.taskId,
    message.fileTaskId,
    message.fileKind,
    compactStringSignature(message.error),
    arraySignature(message.attachments),
    referenceImagesSignature(message.referenceImages),
    imageCompareSourceSignature(message.inpaintSource),
    searchSourcesSignature(message.searchSources),
    searchImageGroupsSignature(message.searchImageGroups),
    imageSlotCount,
    isCollapsible,
    isCollapsed,
    compactStringSignature(markdownContent),
    arraySignature(searchQueries),
    task?.id,
    task?.status,
    task?.terminal,
    task?.mode,
    task?.model,
    task?.requested_count,
    task?.succeeded_count,
    task?.failed_count,
    task?.pending_count,
    task?.size,
    task?.quality,
    task?.stage_code,
    task?.stage_label,
    compactStringSignature(task?.public_error),
    task?.error_code,
    task?.actions.resume_poll,
    fileTask?.id,
    fileTask?.kind,
    fileTask?.status,
    fileTask?.updated_at,
    fileTask?.elapsed_seconds,
    compactStringSignature(fileTask?.status === 'error' ? fileTask.error : ''),
    compactStringSignature(fileTask?.status === 'success' ? fileTask.result.primary_url : ''),
    compactStringSignature(fileTask?.status === 'success' ? fileTask.result.zip_url : ''),
    taskAssets.length,
    ...taskAssets.map((asset) => assetSignature(asset)),
  ]
}

function sameMessageViewSignature(left: MessageViewSignature, right: MessageViewSignature) {
  if (left.length !== right.length) return false
  return left.every((value, index) => value === right[index])
}

function arraySignature(values: string[] | undefined) {
  if (!values?.length) return ''
  return values.map((value) => compactStringSignature(value)).join('\u001f')
}

function referenceImagesSignature(images: StudioReferenceImage[] | undefined) {
  if (!images?.length) return ''
  return images
    .map((image, index) => [
      index,
      compactStringSignature(image.id),
      compactStringSignature(image.name),
      compactStringSignature(image.type),
      image.size || 0,
      compactStringSignature(image.dataUrl),
    ].join('\u001e'))
    .join('\u001f')
}

function imageCompareSourceSignature(source: StudioImageCompareSource | undefined) {
  if (!source) return ''
  return [
    compactStringSignature(source.src),
    compactStringSignature(source.name),
    compactStringSignature(source.localPath),
  ].join('\u001f')
}

function searchSourcesSignature(sources: StudioSearchSource[] | undefined) {
  if (!sources?.length) return ''
  return sources
    .map((source, index) => [
      index,
      compactStringSignature(source.title),
      compactStringSignature(source.url),
      compactStringSignature(source.snippet),
    ].join('\u001e'))
    .join('\u001f')
}

function searchImageGroupsSignature(groups: StudioSearchImageGroup[] | undefined) {
  if (!groups?.length) return ''
  return groups
    .map((group, index) => [
      index,
      compactStringSignature(group.aspectRatio),
      group.numPerQuery || '',
      arraySignature(group.queries),
    ].join('\u001e'))
    .join('\u001f')
}

function assetSignature(asset: ImageTaskAsset) {
  return [
    compactStringSignature(asset.url),
    compactStringSignature(asset.path),
    compactStringSignature(asset.b64_json),
    positiveDimension(asset.width) || '',
    positiveDimension(asset.height) || '',
  ].join('\u001f')
}

function compactStringSignature(value: unknown) {
  const text = String(value ?? '')
  if (!text) return ''
  if (text.length <= 192) return text
  return createLongStringSignature(text)
}

function createLongStringSignature(value: string) {
  const middle = Math.floor(value.length / 2)
  return [
    value.length,
    value.slice(0, 32),
    value.slice(Math.max(0, middle - 16), middle + 16),
    value.slice(-32),
  ].join(':')
}

watch(() => props.conversation, (conversation, previousConversation) => {
  if (conversation?.id === previousConversation?.id) {
    displayedConversation.value = conversation
    return
  }
  stickToBottom = true
  displayedConversation.value = conversation
})

watch(() => displayedConversation.value?.id, () => {
  visibleMessageLimit.value = INITIAL_MESSAGE_LIMIT
  showScrollLatest.value = false
  closeSearchSourcePanel()
  settleScrollToLatest()
})

watch(turnsEl, (element, previousElement) => {
  if (turnsResizeObserver && previousElement) {
    turnsResizeObserver.unobserve(previousElement)
  }
  if (!element) return
  if (typeof ResizeObserver === 'undefined') return
  if (!turnsResizeObserver) {
    turnsResizeObserver = new ResizeObserver(() => {
      keepLatestMessageAnchored()
    })
  }
  turnsResizeObserver.observe(element)
  if (stickToBottom) scrollToBottomNow()
})

function buildImageAssetViews(assets: readonly ImageTaskAsset[]): StudioImageAssetView[] {
  if (!assets.length) return []
  const views: StudioImageAssetView[] = []
  for (const asset of assets) {
    const url = imageAssetUrl(asset)
    if (!url) continue
    views.push({
      url,
      path: String(asset.path || ''),
      width: positiveDimension(asset.width),
      height: positiveDimension(asset.height),
    })
  }
  return views
}

function positiveDimension(value: unknown) {
  const dimension = Number(value)
  return Number.isFinite(dimension) && dimension > 0 ? Math.trunc(dimension) : undefined
}

function isLiveMessage(message: StudioMessage) {
  const task = message.taskId ? props.taskById.get(message.taskId) : undefined
  if (task) return !task.terminal
  const fileTask = message.fileTaskId ? props.fileTaskById.get(message.fileTaskId) : undefined
  if (fileTask) return fileTask.status === 'queued' || fileTask.status === 'running'
  return isLocalImageMessagePending(message)
    || message.status === 'sending'
    || message.status === 'streaming'
}

function isLocalImageMessagePending(message: StudioMessage) {
  return message.status === 'queued' || message.status === 'running'
}

function computeImageSlotCount(message: StudioMessage, task: ImageTask | undefined) {
  if (task) return task.requested_count
  const messageCount = Number(message.imageCount)
  const count = Math.max(1, Number.isFinite(messageCount) ? messageCount : 0)
  return Math.min(4, Math.max(1, Math.trunc(count)))
}

function buildImagePreviewStyle(
  message: StudioMessage,
  task: ImageTask | undefined,
  imageSlotCount: number,
  assets: readonly StudioImageAssetView[],
): CSSProperties {
  const aspect = imageAssetAspect(assets) || parseImageSize(task?.size || message.imageSize || '') || { width: 1, height: 1 }
  const aspectRatio = `${aspect.width} / ${aspect.height}`
  return {
    '--studio-image-aspect-ratio': aspectRatio,
    '--studio-image-grid-columns': String(Math.min(2, imageSlotCount)),
    '--studio-image-message-width': imageMessageWidth(aspect, imageSlotCount),
  } as CSSProperties
}

function imageAssetAspect(assets: readonly StudioImageAssetView[]) {
  const asset = assets.find((item) => item.width && item.height)
  return asset?.width && asset.height ? { width: asset.width, height: asset.height } : null
}

function imageMessageWidth(aspect: { width: number; height: number }, imageSlotCount: number) {
  if (imageSlotCount > 1) return `${MULTI_IMAGE_MAX_WIDTH_REM}rem`
  if (aspect.width >= aspect.height) return `${SINGLE_IMAGE_MAX_WIDTH_REM}rem`
  return `clamp(${SINGLE_IMAGE_MIN_WIDTH_REM}rem, calc(${SINGLE_IMAGE_MAX_WIDTH_REM}rem * ${aspect.width} / ${aspect.height}), ${SINGLE_IMAGE_MAX_WIDTH_REM}rem)`
}

function sourceTitle(source: StudioSearchSource, index: number) {
  return source.title?.trim() || source.url?.trim() || `来源 ${index + 1}`
}

function sourceHost(url: string | undefined) {
  const value = String(url || '').trim()
  if (!value) return ''
  try {
    return new URL(value).host.replace(/^www\./, '')
  } catch {
    return ''
  }
}

function searchSourceDomId(messageId: string, sourceIndex: number) {
  return `studio-search-source-${messageId.replace(/[^a-zA-Z0-9_-]/g, '-')}-${sourceIndex + 1}`
}

function openSearchSourcePanel(message: StudioMessage, sourceIndex?: number) {
  openSearchSourcePanelById(message.id, sourceIndex)
}

function closeSearchSourcePanel() {
  searchPanelMessageId.value = ''
  highlightedSearchSourceId.value = ''
  if (searchSourceHighlightTimer !== null) {
    window.clearTimeout(searchSourceHighlightTimer)
    searchSourceHighlightTimer = null
  }
}

function openSearchSourcePanelById(messageId: string, sourceIndex?: number) {
  searchPanelMessageId.value = messageId
  if (sourceIndex === undefined) {
    highlightedSearchSourceId.value = ''
    return
  }
  highlightSearchSource(messageId, sourceIndex)
}

function scrollToCitationSource(href: string) {
  const match = String(href || '').match(/^studio-citation:([^:]+):(\d+)$/)
  if (!match) return
  const messageId = decodeURIComponent(match[1] || '')
  const sourceIndex = Number(match[2]) - 1
  if (!messageId || !Number.isInteger(sourceIndex) || sourceIndex < 0) return
  openSearchSourcePanelById(messageId, sourceIndex)
}

function highlightSearchSource(messageId: string, sourceIndex: number) {
  const targetId = searchSourceDomId(messageId, sourceIndex)
  highlightedSearchSourceId.value = targetId
  void nextTick(() => {
    const target = document.getElementById(targetId)
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
  if (searchSourceHighlightTimer !== null) window.clearTimeout(searchSourceHighlightTimer)
  searchSourceHighlightTimer = window.setTimeout(() => {
    if (highlightedSearchSourceId.value === targetId) highlightedSearchSourceId.value = ''
    searchSourceHighlightTimer = null
  }, 1600)
}

function trimStringKeyCache<T>(cache: Map<string, T>, maxSize: number) {
  while (cache.size > maxSize) {
    const firstKey = cache.keys().next().value
    if (!firstKey) break
    cache.delete(firstKey)
  }
}

function scheduleScrollToLatest() {
  const token = ++scrollLatestToken
  cancelScheduledScrollToLatest()
  scrollLatestFrameId = window.requestAnimationFrame(() => {
    scrollLatestFrameId = null
    if (token !== scrollLatestToken) return
    scrollToBottomNow()
    window.requestAnimationFrame(() => {
      if (token === scrollLatestToken) scrollToBottomNow()
    })
  })
}

function cancelScheduledScrollToLatest() {
  if (scrollLatestFrameId !== null) {
    window.cancelAnimationFrame(scrollLatestFrameId)
    scrollLatestFrameId = null
  }
}

function settleScrollToLatest() {
  stickToBottom = true
  scrollToBottomNow()
  void nextTick(() => {
    scrollToBottomNow()
    scheduleScrollToLatest()
  })
}

function keepLatestMessageAnchored() {
  if (!stickToBottom) return
  scrollToBottomNow()
  scheduleScrollToLatest()
}

onMounted(() => {
  settleScrollToLatest()
})

onActivated(() => {
  settleScrollToLatest()
})

onBeforeUnmount(() => {
  cancelScheduledScrollToLatest()
  if (searchSourceHighlightTimer !== null) {
    window.clearTimeout(searchSourceHighlightTimer)
    searchSourceHighlightTimer = null
  }
  turnsResizeObserver?.disconnect()
  turnsResizeObserver = null
})

function isTextLikeMessage(message: StudioMessage) {
  return message.role === 'user'
    || (message.mode !== 'file' && (message.mode !== 'image' || message.status === 'error'))
}

function computeIsCollapsibleMessage(message: StudioMessage) {
  if (isLiveMessage(message)) return false
  if (!isTextLikeMessage(message)) return false
  const content = String(message.content || message.error || '')
  if (!content.trim()) return false
  return content.length > 420 || content.split(/\r?\n/).length > 8
}

function computeIsMessageCollapsed(message: StudioMessage) {
  if (message.role === 'assistant') return collapsedMessageIds.value.has(message.id)
  return !expandedMessageIds.value.has(message.id)
}

function computeShouldRenderMarkdown(message: StudioMessage) {
  return message.role === 'assistant'
    && message.mode !== 'image'
    && message.mode !== 'file'
    && Boolean(message.content || message.status === 'streaming')
}

function buildMarkdownDisplayContent(message: StudioMessage) {
  if (!computeShouldRenderMarkdown(message)) return ''
  return String(message.content || '')
}

function toggleMessageExpanded(message: StudioMessage) {
  if (message.role === 'assistant') {
    const next = new Set(collapsedMessageIds.value)
    if (next.has(message.id)) next.delete(message.id)
    else next.add(message.id)
    collapsedMessageIds.value = next
    return
  }
  const next = new Set(expandedMessageIds.value)
  if (next.has(message.id)) next.delete(message.id)
  else next.add(message.id)
  expandedMessageIds.value = next
}

async function showOlderMessages() {
  const el = scrollEl.value
  const previousHeight = el?.scrollHeight || 0
  const previousTop = el?.scrollTop || 0
  visibleMessageLimit.value = Math.min(allMessages.value.length, visibleMessageLimit.value + MESSAGE_BATCH_SIZE)
  await nextTick()
  if (!el) return
  el.scrollTop = previousTop + Math.max(0, el.scrollHeight - previousHeight)
}

function handleMessageAction(action: StudioMessageActionKey, message: StudioMessage) {
  if (action === 'copy') emit('copy-message', message.content)
  else if (action === 'edit') emit('edit', message)
  else if (action === 'resend') emit('resend', message)
  else if (action === 'fill') emit('retry', message)
  else if (action === 'resume-poll') emit('resume-image-task', message)
  else if (action === 'retry') emit('retry-assistant', message)
  else if (action === 'delete') emit('delete-message', message.id)
}

function forwardPreview(src: string, name: string, localPath = '') {
  emit('preview', src, name, localPath)
}

function forwardReferenceImage(asset: StudioImageAssetView, name: string, message: StudioMessage) {
  emit('reference-image', asset, name, message)
}

function forwardInpaintImage(asset: StudioImageAssetView, name: string, message: StudioMessage) {
  emit('inpaint-image', asset, name, message)
}

function forwardCompareImage(source: StudioImageCompareSource, asset: StudioImageAssetView, name: string) {
  emit('compare-image', source, asset, name)
}

function handleScroll() {
  const el = scrollEl.value
  if (!el) return
  const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  stickToBottom = distanceToBottom <= STICK_TO_BOTTOM_DISTANCE_PX
  showScrollLatest.value = !stickToBottom
}

function scrollToBottom() {
  scrollToBottomNow()
}

function scrollToBottomNow() {
  const el = scrollEl.value
  if (!el) return false
  stickToBottom = true
  el.scrollTop = el.scrollHeight
  showScrollLatest.value = false
  return true
}

defineExpose({
  scrollToBottom: async () => {
    stickToBottom = true
    await nextTick()
    scrollToBottomNow()
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()))
    scrollToBottomNow()
  },
})
</script>

<style scoped>
.studio-chat-panel {
  position: relative;
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  --studio-message-width: min(100%, 52rem);
  --studio-image-message-width: 18rem;
  --studio-image-aspect-ratio: 1 / 1;
  --studio-image-grid-columns: 1;
}

.studio-chat-scroll {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overflow-anchor: none;
  scroll-behavior: auto;
  overscroll-behavior: contain;
  padding: 1rem clamp(0.75rem, 2.4vw, 1.75rem) calc(var(--studio-composer-height, 10rem) + 0.5rem);
}

.studio-chat-empty {
  display: flex;
  min-height: calc(100% - 1rem);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: clamp(2rem, 7vh, 5rem) 1rem 1rem;
  text-align: center;
}

.studio-chat-panel.is-fullscreen .studio-chat-empty {
  padding-top: clamp(3rem, 10vh, 7rem);
}

.studio-chat-empty h1 {
  color: hsl(var(--foreground));
  font-size: clamp(1.8rem, 5vw, 3.2rem);
  font-weight: 700;
  letter-spacing: 0;
}

.studio-chat-empty p {
  margin-top: 0.875rem;
  width: max-content;
  max-width: 100%;
  color: hsl(var(--muted-foreground));
  font-size: 0.875rem;
  line-height: 1.8;
}

.studio-turns {
  margin: 0 auto;
  display: flex;
  width: var(--studio-content-width);
  flex-direction: column;
  gap: 1.25rem;
  padding-bottom: 0.5rem;
}

.studio-load-earlier-row {
  display: flex;
  justify-content: center;
}

.studio-load-earlier-button {
  display: inline-flex;
  min-height: 2rem;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ui-control-border, hsl(var(--border)));
  border-radius: 999px;
  background: var(--ui-control-bg, hsl(var(--background)));
  color: var(--ui-fg-muted, hsl(var(--muted-foreground)));
  padding: 0.35rem 0.875rem;
  font-size: 0.75rem;
  font-weight: 650;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.studio-load-earlier-button:hover,
.studio-load-earlier-button:focus-visible {
  border-color: var(--ui-control-hover-border, hsl(var(--foreground) / 0.18));
  background: var(--ui-control-hover-bg, hsl(var(--secondary)));
  color: var(--ui-fg-strong, hsl(var(--foreground)));
}

.studio-search-drawer-backdrop {
  position: absolute;
  inset: 0;
  z-index: 30;
  background: hsl(var(--background) / 0.42);
  backdrop-filter: blur(1px);
}

.studio-search-drawer {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  bottom: 0.75rem;
  z-index: 31;
  display: flex;
  width: min(25rem, calc(100% - 1.5rem));
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 0.82);
  border-radius: 1.1rem;
  background: hsl(var(--card));
  box-shadow: 0 24px 70px hsl(var(--foreground) / 0.18);
}

.studio-search-drawer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid hsl(var(--border) / 0.72);
  padding: 0.9rem 0.95rem 0.75rem;
}

.studio-search-drawer-header div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.2rem;
}

.studio-search-drawer-header strong {
  color: hsl(var(--foreground));
  font-size: 0.95rem;
  font-weight: 800;
}

.studio-search-drawer-header small {
  color: hsl(var(--muted-foreground));
  font-size: 0.72rem;
  font-weight: 650;
}

.studio-search-drawer-body {
  display: grid;
  min-height: 0;
  flex: 1;
  align-content: start;
  gap: 0.55rem;
  overflow-y: auto;
  padding: 0.75rem;
}

.studio-search-source-card {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 0.45rem;
  border: 1px solid hsl(var(--border) / 0.62);
  border-radius: 0.78rem;
  background: hsl(var(--background) / 0.72);
  padding: 0.5rem 0.6rem;
  color: hsl(var(--foreground));
  text-decoration: none;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
}

.studio-search-source-card:hover,
.studio-search-source-card:focus-visible {
  border-color: hsl(var(--foreground) / 0.2);
  background: hsl(var(--background));
  transform: translateY(-1px);
}

.studio-search-source-card.is-static {
  cursor: default;
}

.studio-search-source-card.is-highlighted {
  border-color: var(--ui-accent-border, hsl(var(--primary) / 0.35));
  background: var(--ui-accent-soft, hsl(var(--primary) / 0.08));
  box-shadow: 0 0 0 3px hsl(var(--primary) / 0.08);
}

.studio-search-source-index {
  display: inline-flex;
  width: 1.35rem;
  height: 1.35rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: hsl(var(--secondary));
  color: hsl(var(--muted-foreground));
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1;
}

.studio-search-source-body {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.14rem;
}

.studio-search-source-body strong,
.studio-search-source-body small,
.studio-search-source-body em {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.studio-search-source-body strong {
  font-size: 0.78rem;
  font-style: normal;
  font-weight: 750;
  line-height: 1.25;
}

.studio-search-source-body small {
  color: hsl(var(--muted-foreground));
  font-size: 0.68rem;
  font-weight: 650;
}

.studio-search-source-body em {
  color: hsl(var(--muted-foreground));
  font-size: 0.7rem;
  font-style: normal;
  line-height: 1.25;
}

.studio-search-drawer .studio-search-source-body strong,
.studio-search-drawer .studio-search-source-body em {
  white-space: normal;
}

.studio-search-drawer .studio-search-source-body strong {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.studio-search-drawer .studio-search-source-body em {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.studio-search-source-open {
  margin-top: 0.1rem;
  color: hsl(var(--muted-foreground));
}

.studio-search-drawer-fade-enter-active,
.studio-search-drawer-fade-leave-active,
.studio-search-drawer-slide-enter-active,
.studio-search-drawer-slide-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.studio-search-drawer-fade-enter-from,
.studio-search-drawer-fade-leave-to {
  opacity: 0;
}

.studio-search-drawer-slide-enter-from,
.studio-search-drawer-slide-leave-to {
  opacity: 0;
  transform: translateX(1rem);
}

@media (max-width: 720px) {
  .studio-search-drawer {
    right: 0.5rem;
    left: 0.5rem;
    width: auto;
  }
}

.studio-scroll-latest {
  position: absolute;
  left: 50%;
  bottom: calc(var(--studio-composer-height, 10rem) + 0.75rem);
  z-index: 30;
  display: inline-flex;
  width: 2.75rem;
  height: 2.75rem;
  transform: translateX(-50%);
  align-items: center;
  justify-content: center;
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
  background: hsl(var(--card) / 0.95);
  color: hsl(var(--foreground));
  box-shadow: 0 18px 42px -24px rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(10px);
}

@media (max-width: 720px) {
  .studio-chat-scroll {
    padding: 0.75rem 0.75rem calc(var(--studio-composer-height, 9rem) + 0.5rem);
  }

  .studio-scroll-latest {
    bottom: calc(var(--studio-composer-height, 9rem) + 0.5rem);
  }

  .studio-turns {
    gap: 1rem;
  }

  .studio-chat-panel {
    --studio-message-width: min(100%, 38rem);
    --studio-image-message-width: min(18rem, calc(100vw - 5.5rem));
  }
}
</style>
