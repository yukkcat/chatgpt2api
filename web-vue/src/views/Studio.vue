<template>
  <div class="studio-workspace" :class="{ 'is-fullscreen': isFullscreen }" :style="workspaceStyle">
    <div class="studio-sidebar-wrap">
      <StudioHistoryPanel
        :conversations="conversations"
        :active-conversation-id="activeConversationId"
        :badges="conversationBadges"
        @create="createConversation"
        @select="selectConversation"
        @rename="renameConversation"
        @delete="deleteConversation"
        @clear="confirmClearHistory"
        @reorder="reorderConversation"
      />

      <div
        class="studio-history-resizer"
        role="separator"
        aria-orientation="vertical"
        title="拖动调整历史栏宽度"
        @pointerdown="startSidebarResize"
      ></div>
    </div>

    <main class="studio-main">
      <div class="chat-header-bar">
        <div class="chat-header-title">
          <Button
            size="sm"
            variant="ghost"
            icon-only
            root-class="chat-header-icon lg:hidden"
            title="打开会话列表"
            aria-label="打开会话列表"
            @click="openMobileHistory"
          >
            <Icon icon="lucide:panel-left-open" class="h-4 w-4" />
          </Button>
          <div class="min-w-0">
            <div class="chat-header-name">{{ activeConversation?.title || '新对话' }}</div>
            <div class="chat-header-subtitle">{{ activeHeaderSubtitle }}</div>
          </div>
        </div>

        <div class="chat-header-actions">
          <Button size="sm" variant="outline" root-class="chat-header-action-button" @click="createConversation()">
            <Icon icon="lucide:plus" class="h-3.5 w-3.5" />
            <span class="chat-header-action-label hidden sm:inline">新对话</span>
          </Button>
          <Button
            size="sm"
            variant="outline"
            root-class="chat-header-action-button"
            :disabled="!activeConversation?.messages.length"
            @click="clearCurrentConversation"
          >
            <Icon icon="lucide:trash-2" class="h-3.5 w-3.5" />
            <span class="chat-header-action-label hidden sm:inline">清空</span>
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon-only
            root-class="chat-header-action-button"
            :title="isFullscreen ? '退出全屏' : '全屏'"
            :aria-label="isFullscreen ? '退出全屏' : '全屏'"
            @click="toggleFullscreen"
          >
            <Icon :icon="isFullscreen ? 'lucide:minimize-2' : 'lucide:maximize-2'" class="h-4 w-4" />
          </Button>
        </div>
      </div>

      <StudioMessageList
        ref="messageListRef"
        :conversation="activeConversation"
        :conversations-count="conversations.length"
        :task-by-id="taskById"
        :file-task-by-id="fileTaskById"
        :fullscreen="isFullscreen"
        @create="createConversation"
        @open-history="openMobileHistory"
        @toggle-fullscreen="toggleFullscreen"
        @retry="retryMessage"
        @edit="editMessage"
        @resend="resendMessage"
        @resume-image-task="resumeImageTask"
        @retry-assistant="retryAssistantMessage"
        @delete-message="deleteMessage"
        @copy-message="copyText"
        @preview="openPreview"
        @reference-image="referenceGeneratedImage"
        @inpaint-image="openInpaintModal"
        @compare-image="openImageCompare"
      />

      <StudioComposer
        v-model:mode="composeMode"
        v-model:text="composerText"
        v-model:chat-model="chatModel"
        v-model:chat-reasoning-effort="chatReasoningEffort"
        v-model:file-kind="fileKind"
        :image-form="imageForm"
        :chat-model-options="chatModelOptions"
        :image-model-options="imageModelOptions"
        :image-high-resolution-enabled="imageHighResolutionEnabled"
        :references="referenceRuntime.references.value"
        :is-sending="isSending"
        :is-streaming="isStreaming"
        :is-editing="Boolean(editingMessageId)"
        @update:image-model="imageForm.model = $event"
        @update:image-size="imageForm.size = $event"
        @update:image-quality="imageForm.quality = $event"
        @update:image-count="imageForm.n = $event"
        @submit="sendMessage"
        @stop="stopStreaming"
        @cancel-edit="cancelMessageEdit"
        @add-files="appendFiles"
        @remove-reference="referenceRuntime.remove"
        @clear-references="referenceRuntime.clear"
        @preview-reference="referenceRuntime.open"
        @open-prompts="openPromptPicker"
        @open-search-skill="isSearchSkillOpen = true"
        @open-recent-file-tasks="isRecentFileTasksOpen = true"
      />
    </main>

    <StudioMobileHistory
      :open="isMobileHistoryOpen"
      :conversations="conversations"
      :active-conversation-id="activeConversationId"
      :badges="conversationBadges"
      @close="closeMobileHistory"
      @select="selectConversation"
      @delete="deleteConversation"
    />

    <StudioLightbox
      :preview="referenceRuntime.preview.value"
      @close="referenceRuntime.closePreview"
      @copy="copyText"
      @download="downloadPreviewImage"
    />
    <StudioInpaintModal
      :source="inpaintTarget?.source || null"
      @close="closeInpaintModal"
      @submit="submitInpaintEdit"
    />
    <StudioImageCompareModal
      :compare="comparePreview"
      @close="comparePreview = null"
    />
    <StudioPromptPicker
      v-if="isPromptPickerOpen"
      :open="isPromptPickerOpen"
      @close="isPromptPickerOpen = false"
      @select="applyPromptTemplate"
    />
    <StudioSearchSkillModal
      v-if="isSearchSkillOpen"
      :open="isSearchSkillOpen"
      @close="isSearchSkillOpen = false"
      @copy="copyText"
    />
    <StudioRecentFileTasksModal
      v-if="isRecentFileTasksOpen"
      :open="isRecentFileTasksOpen"
      @close="isRecentFileTasksOpen = false"
      @deleted="handleFileTaskDeleted"
    />
  </div>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { Button } from 'nanocat-ui'
import { computed, defineAsyncComponent, onBeforeUnmount, ref } from 'vue'
import { useToast } from '@/composables/useToast'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { usePageRuntime } from '@/composables/usePageRuntime'
import { preloadPromptLibrary } from '@/composables/usePromptLibraryRuntime'
import StudioPromptPicker from '@/components/studio/StudioPromptPicker.vue'
import { writeClipboardText } from '@/lib/clipboard'
import { downloadUrlAsFile } from '@/lib/downloads'
import {
  buildStudioConversationLookup,
  buildStudioConversationRuntimeIndex,
  type StudioConversationLookup,
  type StudioConversationRuntimeIndex,
} from '@/views/studio/studioConversationState'
import { studioErrorMessage } from '@/views/studio/studioRequestView'
import { useStudioChatStreamRuntime } from '@/views/studio/studioChatStreamRuntime'
import { useStudioComposerRuntime } from '@/views/studio/studioComposerRuntime'
import { useStudioConversationActionsRuntime } from '@/views/studio/studioConversationActionsRuntime'
import {
  loadStudioConversationPersistenceState,
  useStudioConversationPersistenceRuntime,
} from '@/views/studio/studioConversationPersistenceRuntime'
import { useStudioConversationSelectionRuntime } from '@/views/studio/studioConversationSelectionRuntime'
import { useStudioFileTaskRuntime } from '@/views/studio/studioFileTaskRuntime'
import { useStudioImageTaskRuntime } from '@/views/studio/studioImageTaskRuntime'
import { useStudioLayoutRuntime } from '@/views/studio/studioLayoutRuntime'
import { useStudioMessageRuntime } from '@/views/studio/studioMessageRuntime'
import { useStudioModelFormRuntime } from '@/views/studio/studioModelFormRuntime'
import {
  createStudioReferenceFromFile,
  toStudioMessageReferenceImage,
  useStudioReferenceRuntime,
} from '@/views/studio/studioReferenceRuntime'
import { useStudioScrollRuntime, type StudioMessageListScroller } from '@/views/studio/studioScrollRuntime'
import { useStudioSendRuntime } from '@/views/studio/studioSendRuntime'
import StudioComposer from '@/components/studio/StudioComposer.vue'
import StudioHistoryPanel from '@/components/studio/StudioHistoryPanel.vue'
import StudioMessageList from '@/components/studio/StudioMessageList.vue'
import type {
  StudioConversation,
  StudioConversationBadgeState,
  StudioImageAssetView,
  StudioImageComparePreview,
  StudioImageCompareSource,
  StudioMessage,
  StudioReferenceImage,
} from '@/components/studio/types'
import type { PromptLibraryItem } from '@/api/prompts'

defineOptions({ name: 'Studio' })

const StudioLightbox = defineAsyncComponent(() => import('@/components/studio/StudioLightbox.vue'))
const StudioMobileHistory = defineAsyncComponent(() => import('@/components/studio/StudioMobileHistory.vue'))
const StudioInpaintModal = defineAsyncComponent(() => import('@/components/studio/StudioInpaintModal.vue'))
const StudioImageCompareModal = defineAsyncComponent(() => import('@/components/studio/StudioImageCompareModal.vue'))
const StudioSearchSkillModal = defineAsyncComponent(() => import('@/components/studio/StudioSearchSkillModal.vue'))
const StudioRecentFileTasksModal = defineAsyncComponent(() => import('@/components/studio/StudioRecentFileTasksModal.vue'))

const toast = useToast()
const confirmDialog = useConfirmDialog()
const pageRuntime = usePageRuntime('studio')
const composerRuntime = useStudioComposerRuntime()
const referenceRuntime = useStudioReferenceRuntime()
const persistedConversationState = loadStudioConversationPersistenceState()
const modelFormRuntime = useStudioModelFormRuntime()

const composeMode = composerRuntime.composeMode
const composerText = composerRuntime.composerText
const fileKind = composerRuntime.fileKind
const editingMessageId = composerRuntime.editingMessageId
const isSending = composerRuntime.isSending
const isPromptPickerOpen = ref(false)
const isSearchSkillOpen = ref(false)
const isRecentFileTasksOpen = ref(false)
const comparePreview = ref<StudioImageComparePreview | null>(null)
const inpaintTarget = ref<{
  asset: StudioImageAssetView
  name: string
  source: StudioImageCompareSource
} | null>(null)
const messageListRef = ref<StudioMessageListScroller | null>(null)
const scrollRuntime = useStudioScrollRuntime({
  pageRuntime,
  messageListRef,
})
const layoutRuntime = useStudioLayoutRuntime({ scrollRuntime })
const isFullscreen = layoutRuntime.isFullscreen
const isMobileHistoryOpen = layoutRuntime.isMobileHistoryOpen
const workspaceStyle = layoutRuntime.workspaceStyle
const closeMobileHistory = layoutRuntime.closeMobileHistory
const openMobileHistory = layoutRuntime.openMobileHistory
const startSidebarResize = layoutRuntime.startSidebarResize
const toggleFullscreen = layoutRuntime.toggleFullscreen

const chatModel = modelFormRuntime.chatModel
const chatReasoningEffort = modelFormRuntime.chatReasoningEffort
const imageForm = modelFormRuntime.imageForm
const imageHighResolutionEnabled = modelFormRuntime.imageHighResolutionEnabled

const conversations = ref<StudioConversation[]>(persistedConversationState.conversations)
const activeConversationId = ref(persistedConversationState.activeConversationId)
const conversationNotices = ref<Record<string, StudioConversationBadgeState>>(persistedConversationState.conversationNotices)
const conversationLookup = computed<StudioConversationLookup>(() => buildStudioConversationLookup(conversations.value))
const conversationRuntimeIndex = computed<StudioConversationRuntimeIndex>(() => buildStudioConversationRuntimeIndex(conversations.value))
const validConversationIds = computed(() => conversationLookup.value.validIds)
const conversationPersistenceRuntime = useStudioConversationPersistenceRuntime({
  conversations,
  conversationNotices,
  activeConversationId,
  validConversationIds,
})
const activeConversation = computed(() => {
  return conversationLookup.value.byId.get(activeConversationId.value)
    || conversations.value[0]
    || null
})
const imageTaskRuntime = useStudioImageTaskRuntime({
  pageRuntime,
  activeConversation,
  conversationNotices,
  conversationLookup,
  conversationRuntimeIndex,
  hooks: {
    markConversationNotice,
    touchConversation,
    formatError: studioErrorMessage,
    onRefreshError: (message) => {
      toast.error(message)
    },
  },
})
const fileTaskRuntime = useStudioFileTaskRuntime({
  pageRuntime,
  activeConversation,
  conversationRuntimeIndex,
  hooks: {
    markConversationNotice,
    touchConversation,
    formatError: studioErrorMessage,
    onRefreshError: (message) => {
      toast.error(message)
    },
  },
})
const taskById = imageTaskRuntime.taskById
const fileTaskById = fileTaskRuntime.taskById

function handleFileTaskDeleted(taskId: string) {
  fileTaskRuntime.markDeleted([taskId])
}
const activeRunningTaskCount = computed(() => {
  if (!activeConversationId.value) return 0
  return conversationRuntimeIndex.value.runningCounts[activeConversationId.value] || 0
})
const conversationBadges = imageTaskRuntime.conversationBadges
const chatStreamRuntime = useStudioChatStreamRuntime({
  markConversationNotice,
  touchConversation,
  scheduleScrollToBottom,
})
const isStreaming = chatStreamRuntime.isStreaming
const activeHeaderSubtitle = computed(() => {
  if (isStreaming.value) return '正在回复'
  if (isSending.value) {
    if (composeMode.value === 'search') return '正在搜索'
    if (composeMode.value === 'image') return '正在提交图片'
    if (composeMode.value === 'file') return '正在提交文件任务'
    return '正在请求'
  }
  if (activeRunningTaskCount.value > 0) return `处理中 ${activeRunningTaskCount.value}`
  const count = activeConversation.value?.messages.length || 0
  return count ? `${count} 条消息` : '准备就绪'
})
const messageRuntime = useStudioMessageRuntime({
  conversations,
  activeConversation,
  hooks: {
    touchConversation,
    scheduleScrollToBottom,
  },
})
const conversationSelectionRuntime = useStudioConversationSelectionRuntime({
  activeConversationId,
  validConversationIds,
  hooks: {
    cancelMessageEdit: () => cancelMessageEdit(false),
    clearConversationNotice,
  },
})
const conversationActionsRuntime = useStudioConversationActionsRuntime({
  conversations,
  activeConversationId,
  activeConversation,
  conversationNotices,
  conversationLookup,
  persistenceRuntime: conversationPersistenceRuntime,
  selectionRuntime: conversationSelectionRuntime,
  hooks: {
    cancelMessageEdit,
    resetTasks: () => {
      imageTaskRuntime.reset()
      fileTaskRuntime.reset()
    },
    scheduleScrollToBottom,
  },
})
const sendRuntime = useStudioSendRuntime({
  composerRuntime,
  referenceRuntime,
  messageRuntime,
  chatStreamRuntime,
  imageTaskRuntime,
  fileTaskRuntime,
  chatModel,
  chatReasoningEffort,
  imageForm,
  toast,
  hooks: {
    activeConversationId,
    ensureConversation: conversationActionsRuntime.ensureConversation,
    markConversationNotice: conversationActionsRuntime.markConversationNotice,
    clearConversationNotice: conversationActionsRuntime.clearConversationNotice,
    touchConversation: conversationActionsRuntime.touchConversation,
    scheduleScrollToBottom,
  },
})
const retryMessage = sendRuntime.fillComposerFromMessage
const editMessage = sendRuntime.editMessage
const resendMessage = sendRuntime.resendMessage
const retryAssistantMessage = sendRuntime.retryAssistantMessage
const sendImageEditRequest = sendRuntime.sendImageEditRequest
const sendMessage = sendRuntime.sendMessage
const chatModelOptions = modelFormRuntime.chatModelOptions
const imageModelOptions = modelFormRuntime.imageModelOptions

function ensureConversation(content = '') {
  return conversationActionsRuntime.ensureConversation(content)
}

function createConversation(seed = '') {
  const conversation = conversationActionsRuntime.createConversation(seed)
  isMobileHistoryOpen.value = false
  return conversation
}

function selectConversation(id: string) {
  conversationActionsRuntime.selectConversation(id)
}

function renameConversation(id: string, title: string) {
  conversationActionsRuntime.renameConversation(id, title)
}

function reorderConversation(sourceId: string, targetId: string) {
  conversationActionsRuntime.reorderConversation(sourceId, targetId)
}

async function deleteConversation(id: string) {
  const conversation = conversationActionsRuntime.prepareDeleteConversation(id)
  if (!conversation) return
  const ok = await confirmDialog.ask({
    title: '删除对话',
    message: `确定删除“${conversation.title || '未命名对话'}”吗？本地历史会被移除。`,
    confirmText: '删除',
    cancelText: '取消',
  })
  if (!ok) return
  conversationActionsRuntime.deleteConversation(id)
}

async function confirmClearHistory() {
  if (!conversationActionsRuntime.prepareClearHistory()) return
  const ok = await confirmDialog.ask({
    title: '清空历史',
    message: '确定清空本地对话画图历史吗？已生成的图片文件不会删除。',
    confirmText: '清空',
    cancelText: '取消',
  })
  if (!ok) return
  conversationActionsRuntime.clearHistory()
  isMobileHistoryOpen.value = false
}

async function clearCurrentConversation() {
  const conversation = activeConversation.value
  if (!conversation?.messages.length) return
  const ok = await confirmDialog.ask({
    title: '清空当前对话',
    message: `确定清空“${conversation.title || '未命名对话'}”中的消息吗？`,
    confirmText: '清空',
    cancelText: '取消',
  })
  if (!ok) return
  conversationActionsRuntime.clearCurrentConversation(conversation.id)
}

function deleteMessage(messageId: string) {
  if (editingMessageId.value === messageId) cancelMessageEdit()
  messageRuntime.deleteActiveMessage(messageId)
}

function cancelMessageEdit(clearComposer = true) {
  composerRuntime.cancelMessageEdit(clearComposer)
}

function touchConversation(conversation: StudioConversation) {
  conversationActionsRuntime.touchConversation(conversation)
}

function markConversationNotice(conversationId: string, state: StudioConversationBadgeState) {
  conversationActionsRuntime.markConversationNotice(conversationId, state)
}

function clearConversationNotice(conversationId: string) {
  conversationActionsRuntime.clearConversationNotice(conversationId)
}

function stopStreaming() {
  chatStreamRuntime.stop()
}

async function appendFiles(files: File[]) {
  const added = await referenceRuntime.append(files)
  if (added && composeMode.value !== 'chat' && composeMode.value !== 'file') composerRuntime.activateImageMode()
}

function cleanAssetText(value: unknown) {
  return String(value ?? '').trim()
}

function safeImageFilename(value: string, fallback = 'generated-image.png') {
  const cleaned = cleanAssetText(value)
    .replace(/[\\/:*?"<>|]+/g, '_')
    .replace(/\s+/g, '_')
    .replace(/^_+|_+$/g, '')
  return cleaned || fallback
}

function imageAssetFilename(asset: StudioImageAssetView, fallback: string) {
  const pathName = cleanAssetText(asset.path).split('/').filter(Boolean).pop()
  const baseName = pathName || fallback || 'generated-image'
  const filename = /\.[a-z0-9]{2,5}$/i.test(baseName) ? baseName : `${baseName}.png`
  return safeImageFilename(filename)
}

function localImageUrl(path: string) {
  const cleaned = cleanAssetText(path).replace(/^\/+/, '')
  if (!cleaned) return ''
  return `/images/${cleaned.split('/').filter(Boolean).map((part) => encodeURIComponent(part)).join('/')}`
}

function imageAssetSource(asset: StudioImageAssetView) {
  return localImageUrl(asset.path) || cleanAssetText(asset.url)
}

function imageCompareSource(asset: StudioImageAssetView, name: string): StudioImageCompareSource | null {
  const src = imageAssetSource(asset)
  if (!src) return null
  const localPath = cleanAssetText(asset.path)
  return {
    src,
    name: cleanAssetText(name) || imageAssetFilename(asset, '生成图片.png'),
    localPath: localPath || undefined,
  }
}

async function imageAssetToFile(asset: StudioImageAssetView, name: string) {
  const filename = imageAssetFilename(asset, name)
  const source = imageAssetSource(asset)
  if (!source) throw new Error('图片没有可读取的地址')

  const response = /^data:/i.test(source)
    ? await fetch(source)
    : await fetch(source, { credentials: 'same-origin' })
  if (!response.ok) throw new Error(`读取图片失败：HTTP ${response.status}`)

  const blob = await response.blob()
  if (!blob.size) throw new Error('读取到的图片为空')
  if (blob.type && !blob.type.startsWith('image/')) throw new Error('读取到的内容不是图片')
  return new File([blob], filename, { type: blob.type || 'image/png' })
}

async function messageReferenceImageFromFile(file: File): Promise<StudioReferenceImage> {
  const reference = await createStudioReferenceFromFile(file)
  return toStudioMessageReferenceImage(reference)
}

async function referenceGeneratedImage(asset: StudioImageAssetView, name: string) {
  let file: File
  try {
    file = await imageAssetToFile(asset, name)
  } catch (error) {
    toast.error(studioErrorMessage(error, '引用图片读取失败'))
    return
  }

  const added = await referenceRuntime.append([file])
  if (!added) {
    toast.error('最多只能添加 8 张参考图')
    return
  }
  composerRuntime.activateImageMode()
  toast.success('已引用到输入框')
  scheduleScrollToBottom()
}

function openInpaintModal(asset: StudioImageAssetView, name: string, _message: StudioMessage) {
  const source = imageCompareSource(asset, name)
  if (!source) {
    toast.error('图片没有可用于局部修改的地址')
    return
  }
  inpaintTarget.value = { asset, name, source }
}

function closeInpaintModal() {
  inpaintTarget.value = null
}

function openImageCompare(source: StudioImageCompareSource, asset: StudioImageAssetView, name: string) {
  const after = imageCompareSource(asset, name)
  if (!after) {
    toast.error('新图没有可用于对比的地址')
    return
  }
  comparePreview.value = { before: source, after }
}

async function submitInpaintEdit(payload: { prompt: string; markedImage: File }) {
  const target = inpaintTarget.value
  const prompt = cleanAssetText(payload.prompt)
  if (!target || !prompt) return

  let sourceFile: File
  let referenceImage: StudioReferenceImage
  try {
    sourceFile = await imageAssetToFile(target.asset, target.name)
    referenceImage = await messageReferenceImageFromFile(payload.markedImage)
  } catch (error) {
    toast.error(studioErrorMessage(error, '局部修改图片读取失败'))
    return
  }

  const requestPrompt = [
    '你会收到两张参考图：第一张是原图，第二张是带蓝色标记的原图。',
    '只修改蓝色标记覆盖的局部区域，蓝色标记只是区域说明，不要出现在最终图片里。',
    '未标记区域尽量保持与第一张原图一致。',
    `局部修改要求：${prompt}`,
  ].join('\n')
  const ok = await sendImageEditRequest({
    prompt: requestPrompt,
    files: [sourceFile, payload.markedImage],
    userContent: `局部修改：${prompt}`,
    referenceImages: [referenceImage],
    assistantContent: '局部修改任务已提交',
    inpaintSource: target.source,
    imageCount: 1,
  })
  if (ok) closeInpaintModal()
}

function openPromptPicker() {
  isPromptPickerOpen.value = true
}

function applyPromptTemplate(prompt: PromptLibraryItem) {
  composerText.value = prompt.prompt
  if (composeMode.value === 'image') {
    if (prompt.image_model) imageForm.model = prompt.image_model
    if (prompt.image_size) imageForm.size = prompt.image_size
    if (prompt.image_count && prompt.image_count > 0) imageForm.n = prompt.image_count
  }
  isPromptPickerOpen.value = false
}

function openPreview(src: string, name: string, localPath = '') {
  referenceRuntime.openPreview(src, name, localPath)
}

async function copyText(value: string) {
  if (!value) return
  try {
    await writeClipboardText(value)
    toast.success('已复制')
  } catch {
    toast.error('复制失败')
  }
}

async function downloadPreviewImage() {
  const previewImage = referenceRuntime.preview.value
  if (!previewImage) return
  try {
    await downloadUrlAsFile(previewImage.src, previewImage.name || 'image.png', { localPath: previewImage.localPath })
    toast.success('已开始下载')
  } catch (error: any) {
    toast.error(`下载失败：${error.message || '无法读取图片文件'}`)
  }
}

function scrollToBottom() {
  scrollRuntime.scrollToBottom()
}

function scheduleScrollToBottom() {
  scrollRuntime.scheduleScrollToBottom()
}

function cancelScheduledScroll() {
  scrollRuntime.cancel()
}

function stopTransientStudioUi() {
  layoutRuntime.stopSidebarResize()
  conversationSelectionRuntime.cancel()
  isSearchSkillOpen.value = false
  isRecentFileTasksOpen.value = false
  cancelScheduledScroll()
}

async function resumeImageTask(message: StudioMessage) {
  if (!message.taskId) return
  await imageTaskRuntime.resumePoll(message.taskId)
}

function ensureActiveConversation() {
  if (!conversations.value.length) {
    createConversation()
  } else if (!activeConversationId.value || !conversationLookup.value.validIds.has(activeConversationId.value)) {
    activeConversationId.value = conversations.value[0]?.id || ''
  }
}

function initializeStudio() {
  ensureActiveConversation()
  void modelFormRuntime.loadModelCatalog(true)
  scheduleModelCatalogRefresh()
  void preloadPromptLibrary()
  void imageTaskRuntime.refresh()
  imageTaskRuntime.schedulePoll()
  void fileTaskRuntime.refresh()
  fileTaskRuntime.schedulePoll()
}

function activateStudio() {
  void modelFormRuntime.loadModelCatalog(true)
  scheduleModelCatalogRefresh()
  void imageTaskRuntime.refresh()
  imageTaskRuntime.schedulePoll()
  void fileTaskRuntime.refresh()
  fileTaskRuntime.schedulePoll()
}

function deactivateStudio() {
  cancelModelCatalogRefresh()
  imageTaskRuntime.deactivate()
  fileTaskRuntime.deactivate()
  stopTransientStudioUi()
  conversationPersistenceRuntime.flush()
}

function disposeStudio() {
  cancelModelCatalogRefresh()
  stopTransientStudioUi()
  imageTaskRuntime.dispose()
  fileTaskRuntime.dispose()
  chatStreamRuntime.dispose()
  conversationPersistenceRuntime.flush()
  conversationPersistenceRuntime.dispose()
  conversationSelectionRuntime.dispose()
  layoutRuntime.dispose()
  scrollRuntime.dispose()
}

let modelCatalogRefreshTimer: number | null = null

function cancelModelCatalogRefresh() {
  if (modelCatalogRefreshTimer == null) return
  window.clearInterval(modelCatalogRefreshTimer)
  modelCatalogRefreshTimer = null
}

function scheduleModelCatalogRefresh() {
  cancelModelCatalogRefresh()
  modelCatalogRefreshTimer = window.setInterval(() => {
    void modelFormRuntime.loadModelCatalog()
  }, 30_000)
}

pageRuntime.onActivate(({ initial }) => {
  if (initial) {
    initializeStudio()
    return
  }
  activateStudio()
})

pageRuntime.onDeactivate(() => {
  deactivateStudio()
})

pageRuntime.onHide(() => {
  deactivateStudio()
})

pageRuntime.onShow(() => {
  activateStudio()
})

onBeforeUnmount(() => {
  disposeStudio()
})
</script>

<style scoped>
.studio-workspace {
  --studio-content-width: min(100%, clamp(48rem, 68vw, 78rem));
  --ui-card-border: hsl(var(--border));
  --ui-card-bg: hsl(var(--card));
  --ui-panel-border: hsl(var(--border));
  --ui-panel-bg: hsl(var(--card));
  --ui-control-border: hsl(var(--border));
  --ui-control-bg: hsl(var(--background));
  --ui-control-hover-bg: hsl(var(--secondary));
  --ui-control-hover-border: hsl(var(--foreground) / 0.16);
  --ui-fg-strong: hsl(var(--foreground));
  --ui-fg-muted: hsl(var(--muted-foreground));
  --ui-fg-subtle: hsl(var(--muted-foreground));
  --ui-accent: hsl(var(--foreground));
  --ui-accent-soft: hsl(var(--secondary));
  --ui-accent-strong: hsl(var(--foreground));
  --ui-accent-border: hsl(var(--border));
  --ui-accent-border-strong: hsl(var(--foreground) / 0.22);
  --ui-accent-ring: hsl(var(--foreground) / 0.10);
  --ui-active-border: hsl(var(--foreground) / 0.22);
  --ui-active-bg: hsl(var(--secondary));
  --ui-active-fg: hsl(var(--foreground));
  --ui-divider: hsl(var(--border));
  --ui-danger-fg: rgb(220 38 38);
  --ui-danger-bg: rgb(254 242 242 / 0.88);
  --ui-danger-border: rgb(248 113 113 / 0.35);
  --ui-duration-fast: 150ms;
  --ui-duration-normal: 220ms;
  --ui-ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  display: grid;
  box-sizing: border-box;
  height: auto;
  min-height: 0;
  flex: 1 1 0%;
  grid-template-columns: var(--studio-history-width) minmax(0, 1fr);
  gap: 0.75rem;
  overflow: hidden;
}

.studio-workspace.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 180;
  height: 100dvh;
  min-height: 0;
  background: hsl(var(--background));
  padding: 1rem 1.25rem 1.25rem;
}

.studio-sidebar-wrap {
  position: relative;
  min-width: 0;
  min-height: 0;
}

.studio-history-resizer {
  display: none;
  position: absolute;
  top: 0;
  right: -0.5rem;
  bottom: 0;
  z-index: 10;
  width: 0.75rem;
  cursor: col-resize;
  border-radius: 999px;
  touch-action: none;
  transition: background 0.15s;
}

.studio-history-resizer::before {
  position: absolute;
  top: 0.75rem;
  bottom: 0.75rem;
  left: 50%;
  width: 2px;
  transform: translateX(-50%);
  border-radius: 999px;
  background: hsl(var(--foreground) / 0.42);
  content: '';
  opacity: 0;
  transition: opacity 0.15s, background 0.15s;
}

.studio-history-resizer:hover {
  background: transparent;
}

.studio-history-resizer:hover::before,
:global(.studio-resizing) .studio-history-resizer::before {
  background: hsl(var(--primary) / 0.58);
  opacity: 1;
}

.studio-main {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 1.25rem;
  background: hsl(var(--card) / 0.88);
  box-shadow: 0 16px 44px -36px rgba(15, 23, 42, 0.45);
}

.chat-header-bar {
  display: flex;
  min-height: 3.5rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--card) / 0.84);
  padding: 0.625rem 0.875rem;
}

.chat-header-title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.5rem;
}

.chat-header-name {
  min-width: 0;
  max-width: min(32rem, 48vw);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: hsl(var(--foreground));
  font-size: 0.875rem;
  font-weight: 700;
}

.chat-header-subtitle {
  margin-top: 0.125rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
  line-height: 1rem;
}

.chat-header-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 0.375rem;
}

.chat-header-action-button,
.chat-header-icon {
  border-radius: 0.75rem;
}

:global(.studio-resizing) {
  cursor: col-resize;
  user-select: none;
}

@media (min-width: 1024px) {
  .studio-history-resizer {
    display: block;
  }
}

@media (max-width: 1023px) {
  .studio-workspace {
    grid-template-columns: minmax(0, 1fr);
  }

  .studio-sidebar-wrap {
    display: none;
  }

  .studio-workspace.is-fullscreen {
    height: 100dvh;
  }

  .chat-header-name {
    max-width: 42vw;
  }

}

</style>
