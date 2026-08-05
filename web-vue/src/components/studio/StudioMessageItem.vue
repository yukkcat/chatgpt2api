<template>
  <article
    class="chat-message-row"
    :class="message.role === 'user' ? 'is-user' : 'is-assistant'"
  >
    <div
      class="chat-message-container"
      :class="[
        message.role === 'user' ? 'is-user' : 'is-assistant',
        message.isImageMessage ? 'is-image-message' : '',
        message.isPendingImageMessage ? 'is-pending-image-message' : '',
        message.isSingleImageResult ? 'is-single-image-result' : '',
        message.role === 'assistant' && message.mode === 'file' ? 'is-file-message' : '',
        isCodeMessage(message) ? 'is-code-message' : '',
      ]"
      :style="message.imagePreviewStyle"
    >
      <div class="chat-message-header" :class="{ 'is-user': message.role === 'user' }">
        <div
          class="chat-message-avatar"
          :class="{ 'chat-message-avatar-user': message.role === 'user' }"
          aria-hidden="true"
        >
          <Icon :icon="message.role === 'user' ? 'lucide:user' : 'lucide:bot'" class="h-4 w-4" />
        </div>

        <div class="chat-message-actions">
          <Button
            v-for="action in actionsForMessage(message)"
            :key="action.key"
            icon-only
            size="xs"
            :variant="action.danger ? 'danger' : 'outline'"
            root-class="chat-message-action"
            :title="action.label"
            :aria-label="action.label"
            @click="$emit('action', action.key, message)"
          >
            <Icon :icon="action.icon" class="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div class="chat-message-bubble-wrap">
        <div
          v-if="isStandaloneErrorMessage(message)"
          class="chat-message-error-card"
          role="alert"
        >
          <Icon icon="lucide:circle-alert" class="chat-message-error-icon h-4 w-4" />
          <p>{{ standaloneErrorText(message) }}</p>
        </div>
        <div
          v-else
          class="chat-message-bubble"
          :class="[
            message.role === 'user' ? 'chat-message-bubble-user' : 'chat-message-bubble-assistant',
            message.isImageMessage ? 'chat-message-bubble-image' : '',
            message.isPendingImageMessage ? 'chat-message-bubble-image-pending' : '',
            (message.fileTask ? message.fileTask.status === 'error' : message.status === 'error') ? 'chat-message-bubble-error' : '',
          ]"
        >
          <div
            class="chat-message-content"
            :class="{
              'is-collapsible': message.isCollapsible,
              'is-collapsed': message.isCollapsed,
              'is-markdown': message.role !== 'user' && message.mode !== 'image' && message.mode !== 'file',
            }"
          >
            <template v-if="message.role === 'user'">
              <p v-if="message.content" class="studio-user-prompt">{{ message.content }}</p>
              <div v-if="message.attachments?.length && !message.referenceImages?.length" class="studio-attachment-line">
                <Icon icon="lucide:paperclip" class="h-3.5 w-3.5" />
                {{ message.attachments.join('、') }}
              </div>
            </template>

            <template v-else-if="message.mode === 'file'">
              <div class="studio-file-task" :class="`is-${fileTaskStatus(message)}`">
                <div class="studio-file-task-icon" aria-hidden="true">
                  <Icon
                    :icon="message.fileTaskDeleted
                      ? 'lucide:file-x-2'
                      : fileTaskStatus(message) === 'error'
                      ? 'lucide:circle-alert'
                      : fileTaskStatus(message) === 'success'
                        ? 'lucide:file-check-2'
                        : 'lucide:loader-circle'"
                    :class="['h-4 w-4', { 'animate-spin': isFileTaskPending(message) }]"
                  />
                </div>
                <div class="studio-file-task-body">
                  <strong>{{ fileTaskTitle(message) }}</strong>
                  <span v-if="message.fileTaskDeleted">任务记录和本地文件已删除。</span>
                  <p v-else-if="fileTaskStatus(message) === 'error'">
                    {{ fileTaskError(message) }}
                  </p>
                  <span v-else-if="isFileTaskPending(message)">{{ fileTaskStatusText(message) }}</span>
                  <span v-else-if="!message.fileTask">正在读取下载地址</span>
                  <span v-else>可下载源文件或完整压缩包。</span>

                  <div v-if="message.fileTask?.status === 'success'" class="studio-file-task-actions">
                    <button
                      type="button"
                      class="studio-file-task-action"
                      :disabled="isDownloadingFileTask"
                      @click="handleFileTaskDownload(message, message.fileTask.result.primary_url, 'file')"
                    >
                      <Icon icon="lucide:download" class="h-3.5 w-3.5" />
                      下载 {{ fileKindLabel(message) }}
                    </button>
                    <button
                      type="button"
                      class="studio-file-task-action"
                      :disabled="isDownloadingFileTask"
                      @click="handleFileTaskDownload(message, message.fileTask.result.zip_url, 'zip')"
                    >
                      <Icon icon="lucide:archive" class="h-3.5 w-3.5" />
                      下载 ZIP
                    </button>
                  </div>
                </div>
              </div>
            </template>

            <template v-else-if="message.mode !== 'image'">
              <div v-if="message.searchQueries.length" class="studio-search-call-list">
                <div
                  v-for="query in message.searchQueries"
                  :key="query"
                  class="studio-search-call"
                  :title="query"
                >
                  <Icon icon="lucide:search" class="studio-search-call-icon h-3.5 w-3.5" />
                  <span class="studio-search-call-label">search</span>
                  <span class="studio-search-call-query">{{ query }}</span>
                </div>
              </div>
              <StudioMarkdownContent
                v-if="message.content || message.status === 'streaming'"
                :content="message.markdownContent || ' '"
                :status="message.status"
                @citation-click="$emit('citation-click', $event)"
              />
              <span v-if="message.status === 'streaming'" class="studio-cursor"></span>
              <p v-if="message.error && !message.content.includes(message.error)" class="studio-error-text">
                {{ message.error }}
              </p>
              <button
                v-if="message.mode === 'search' && message.searchSources?.length"
                type="button"
                class="studio-search-source-chip"
                @click="$emit('open-search-sources', message)"
              >
                <Icon icon="lucide:external-link" class="studio-search-source-chip-icon" />
                <span class="studio-search-source-chip-label">参考来源</span>
                <strong>{{ message.searchSources.length }}</strong>
                <small>查看</small>
              </button>
              <div v-if="message.mode === 'search' && message.searchImageGroups?.length" class="studio-search-image-groups">
                <div
                  v-for="(group, groupIndex) in message.searchImageGroups"
                  :key="`${message.id}-image-group-${groupIndex}`"
                  class="studio-search-image-group"
                >
                  <span class="studio-search-image-group-title">
                    <Icon icon="lucide:image" class="h-3.5 w-3.5" />
                    图片参考<span v-if="group.aspectRatio"> {{ group.aspectRatio }}</span>
                  </span>
                  <span class="studio-search-image-group-queries">
                    <span v-for="query in group.queries" :key="query" class="studio-search-image-query">{{ query }}</span>
                  </span>
                </div>
              </div>
            </template>

            <template v-else>
              <div
                v-if="isImageMessageWithoutResult(message)"
                class="studio-image-status"
                :class="{ 'is-error': message.task?.status === 'failed' }"
              >
                <Icon :icon="message.task?.status === 'text_review' ? 'lucide:message-square-text' : 'lucide:circle-alert'" class="h-4 w-4" />
                <span>{{ message.primaryMessage || message.error || '上游没有返回可用图片。' }}</span>
              </div>

              <div
                v-else
                class="studio-result-block"
                :class="{ 'studio-result-block-pending': message.pendingSlots.length > 0 }"
              >
                <div class="studio-result-grid" :class="{ 'is-single': message.imageSlotCount <= 1 }">
                  <div
                    v-for="(asset, assetIndex) in message.assets"
                    :key="`${message.id}-${assetIndex}`"
                    class="studio-result-item"
                  >
                    <button
                      type="button"
                      class="studio-result-media"
                      :class="{ 'has-image': Boolean(asset.url) }"
                      @click="$emit('preview', asset.url, `结果 ${assetIndex + 1}`, asset.path)"
                    >
                      <img
                        v-if="asset.url"
                        :src="asset.url"
                        :alt="`结果 ${assetIndex + 1}`"
                        :width="asset.width || undefined"
                        :height="asset.height || undefined"
                        loading="lazy"
                      />
                      <span v-else>无图片 URL</span>
                    </button>
                    <div v-if="asset.url" class="studio-result-caption">
                      <span v-if="message.imageSlotCount > 1" class="studio-result-caption-label">结果 {{ assetIndex + 1 }}</span>
                      <div class="studio-result-actions">
                        <Button
                          size="xs"
                          variant="outline"
                          root-class="studio-result-action"
                          title="引用到输入框"
                          aria-label="引用到输入框"
                          @click="$emit('reference-image', asset, `结果 ${assetIndex + 1}`, message)"
                        >
                          <Icon icon="lucide:image-plus" class="h-3.5 w-3.5" />
                          <span>引用</span>
                        </Button>
                        <Button
                          size="xs"
                          variant="outline"
                          root-class="studio-result-action"
                          title="局部修改"
                          aria-label="局部修改"
                          @click="$emit('inpaint-image', asset, `结果 ${assetIndex + 1}`, message)"
                        >
                          <Icon icon="lucide:scan-line" class="h-3.5 w-3.5" />
                          <span>局部</span>
                        </Button>
                        <Button
                          v-if="message.inpaintSource"
                          size="xs"
                          variant="outline"
                          root-class="studio-result-action"
                          title="对比原图"
                          aria-label="对比原图"
                          @click="$emit('compare-image', message.inpaintSource, asset, `结果 ${assetIndex + 1}`)"
                        >
                          <Icon icon="lucide:columns-2" class="h-3.5 w-3.5" />
                          <span>对比</span>
                        </Button>
                      </div>
                    </div>
                  </div>

                  <div
                    v-for="slot in message.pendingSlots"
                    :key="`${message.id}-pending-${slot}`"
                    class="studio-result-item"
                  >
                    <div class="studio-result-media studio-result-placeholder">
                      <Icon icon="lucide:loader-circle" class="h-5 w-5 animate-spin" />
                      <span>正在处理图片</span>
                      <small>{{ message.imagePendingStageText }}</small>
                    </div>
                    <div v-if="message.imageSlotCount > 1" class="studio-result-caption">
                      <span>图片 {{ slot + 1 }}</span>
                    </div>
                  </div>

                  <div
                    v-for="slot in message.failedSlots"
                    :key="`${message.id}-failed-${slot}`"
                    class="studio-result-item"
                  >
                    <div class="studio-result-media studio-result-placeholder studio-result-placeholder-failed">
                      <Icon icon="lucide:circle-x" class="h-5 w-5" />
                      <span>未生成</span>
                    </div>
                    <div v-if="message.imageSlotCount > 1" class="studio-result-caption">
                      <span>图片 {{ slot + 1 }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>

          <button
            v-if="message.isCollapsible"
            type="button"
            class="chat-message-expand"
            @click.stop="$emit('toggle-expanded', message)"
          >
            {{ message.isCollapsed ? '展开全部' : '收起' }}
            <Icon :icon="message.isCollapsed ? 'lucide:chevron-down' : 'lucide:chevron-up'" class="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div
        v-if="message.role === 'user' && message.referenceImages?.length"
        class="studio-message-reference-strip"
      >
        <button
          v-for="(reference, referenceIndex) in message.referenceImages"
          :key="reference.id || `${message.id}-reference-${referenceIndex}`"
          type="button"
          class="studio-message-reference-thumb"
          :title="reference.name"
          @click="$emit('preview', reference.dataUrl, reference.name || `参考图 ${referenceIndex + 1}`)"
        >
          <img :src="reference.dataUrl" :alt="reference.name || `参考图 ${referenceIndex + 1}`" loading="lazy" />
        </button>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { Button } from 'nanocat-ui'
import type { CSSProperties } from 'vue'
import type { EditableFileTask } from '@/api/editableFileTasks'
import type { ImageTask } from '@/api/imageTasks'
import { useToast } from '@/composables/useToast'
import { hasStudioCodeContent } from '@/lib/studioMarkdownRenderer'
import {
  useEditableFileTaskDownload,
  type EditableFileTaskDownloadType,
} from './editableFileTaskView'
import StudioMarkdownContent from './StudioMarkdownContent.vue'
import type { StudioImageAssetView, StudioImageCompareSource, StudioMessage } from './types'

export type StudioMessageActionKey = 'copy' | 'edit' | 'resend' | 'fill' | 'resume-poll' | 'retry' | 'delete'

export interface StudioMessageAction {
  key: StudioMessageActionKey
  label: string
  icon: string
  danger?: boolean
}

export type StudioMessageView = StudioMessage & {
  memoKey: string
  task?: ImageTask
  fileTask?: EditableFileTask
  assets: StudioImageAssetView[]
  isImageMessage: boolean
  isPendingImageMessage: boolean
  isSingleImageResult: boolean
  imageSlotCount: number
  pendingSlots: number[]
  failedSlots: number[]
  imagePendingStageText: string
  primaryMessage: string
  imagePreviewStyle?: CSSProperties
  isCollapsible: boolean
  isCollapsed: boolean
  markdownContent: string
  searchQueries: string[]
}

defineProps<{
  message: StudioMessageView
}>()

defineEmits<{
  action: [key: StudioMessageActionKey, message: StudioMessage]
  'toggle-expanded': [message: StudioMessage]
  'open-search-sources': [message: StudioMessage]
  'citation-click': [href: string]
  preview: [src: string, name: string, localPath?: string]
  'reference-image': [asset: StudioImageAssetView, name: string, message: StudioMessage]
  'inpaint-image': [asset: StudioImageAssetView, name: string, message: StudioMessage]
  'compare-image': [source: StudioImageCompareSource, asset: StudioImageAssetView, name: string]
}>()

const toast = useToast()
const {
  isDownloading: isDownloadingFileTask,
  download: downloadFileTask,
} = useEditableFileTaskDownload({
  onError: (message) => toast.error(message),
})

function actionsForMessage(message: StudioMessageView): StudioMessageAction[] {
  const actions: StudioMessageAction[] = []
  if (message.content) actions.push({ key: 'copy', label: '复制', icon: 'lucide:copy' })
  if (message.role === 'user') {
    if (message.content) actions.push({ key: 'edit', label: '编辑', icon: 'lucide:pencil' })
    actions.push({ key: 'resend', label: '重发', icon: 'lucide:refresh-cw' })
    if (message.content) actions.push({ key: 'fill', label: '填入', icon: 'lucide:clipboard-paste' })
  } else if (
    message.mode === 'image'
    && isImageMessageWithoutResult(message)
    && message.task?.actions.resume_poll
  ) {
    actions.push({ key: 'resume-poll', label: '继续任务', icon: 'lucide:refresh-cw' })
  } else if (message.mode === 'file' ? fileTaskStatus(message) === 'error' : message.mode !== 'image' || isImageMessageWithoutResult(message)) {
    actions.push({ key: 'retry', label: '重试并重新提交', icon: 'lucide:refresh-cw' })
  }
  actions.push({ key: 'delete', label: '删除', icon: 'lucide:trash-2', danger: true })
  return actions
}

function isImageTaskWithoutResult(task: ImageTask | undefined) {
  return task?.status === 'failed' || task?.status === 'text_review'
}

function isImageMessageWithoutResult(message: StudioMessageView) {
  return isImageTaskWithoutResult(message.task) || (!message.task && message.status === 'error')
}

function textValue(value: string | null | undefined) {
  return String(value || '').trim()
}

function isStandaloneErrorMessage(message: StudioMessageView) {
  if (message.role !== 'assistant' || message.mode === 'image' || message.mode === 'file' || message.status !== 'error') return false
  const content = textValue(message.content)
  const error = textValue(message.error)
  return !content || content === error
}

function standaloneErrorText(message: StudioMessageView) {
  return textValue(message.error) || textValue(message.content) || '请求失败，请稍后重试。'
}

function isCodeMessage(message: StudioMessageView) {
  if (message.mode === 'image' || message.mode === 'file') return false
  return hasStudioCodeContent(textValue(message.markdownContent || message.content))
}

function fileTaskStatus(message: StudioMessageView): EditableFileTask['status'] {
  if (message.fileTask) return message.fileTask.status
  if (message.status === 'error') return 'error'
  if (message.status === 'done') return 'success'
  return message.status === 'running' ? 'running' : 'queued'
}

function isFileTaskPending(message: StudioMessageView) {
  const status = fileTaskStatus(message)
  return status === 'queued' || status === 'running'
}

function fileKindLabel(message: StudioMessageView) {
  return String(message.fileTask?.kind || message.fileKind || 'ppt').toUpperCase()
}

function fileTaskTitle(message: StudioMessageView) {
  const kind = fileKindLabel(message)
  if (message.fileTaskDeleted) return `${kind} 文件已删除`
  const status = fileTaskStatus(message)
  if (status === 'success') return `${kind} 文件已生成`
  if (status === 'error') return `${kind} 生成失败`
  return `${kind} 文件`
}

function fileTaskStatusText(message: StudioMessageView) {
  return fileTaskStatus(message) === 'running' ? '正在生成可编辑文件' : '等待开始生成'
}

function fileTaskError(message: StudioMessageView) {
  if (message.fileTask?.status === 'error') return message.fileTask.error
  return textValue(message.error) || textValue(message.content) || '文件生成失败，请稍后重试。'
}

async function handleFileTaskDownload(
  message: StudioMessageView,
  url: string,
  type: EditableFileTaskDownloadType,
) {
  if (!message.fileTask) return
  await downloadFileTask(message.fileTask, url, type)
}
</script>

<style scoped>
.chat-message-row {
  display: flex;
  min-width: 0;
  max-width: 100%;
}

.chat-message-row.is-user {
  justify-content: flex-end;
}

.chat-message-row.is-assistant {
  justify-content: flex-start;
}

.chat-message-container {
  display: flex;
  min-width: 0;
  max-width: var(--studio-message-width, min(100%, 44rem));
  width: fit-content;
  flex-direction: column;
}

.chat-message-container.is-code-message {
  width: min(100%, var(--studio-message-width, 44rem));
}

.chat-message-container.is-pending-image-message {
  inline-size: min(100%, var(--studio-image-message-width, 18rem));
  min-width: 0;
  max-width: 100%;
}

.chat-message-container.is-image-message {
  inline-size: min(100%, var(--studio-image-message-width, 18rem));
  min-width: 0;
  max-width: 100%;
}

.chat-message-container.is-file-message {
  inline-size: min(100%, 24rem);
  min-width: 0;
  max-width: 100%;
}

.chat-message-container.is-file-message .chat-message-bubble-wrap,
.chat-message-container.is-file-message .chat-message-bubble {
  width: 100%;
}

.chat-message-container.is-single-image-result {
  inline-size: fit-content;
  width: fit-content;
  max-inline-size: min(100%, var(--studio-image-message-width, 18rem));
}

.chat-message-container.is-user {
  align-items: flex-end;
}

.chat-message-container.is-assistant {
  align-items: flex-start;
}

.chat-message-header {
  display: flex;
  min-height: 1.75rem;
  align-items: center;
  gap: 0.375rem;
  margin-bottom: 0.25rem;
}

.chat-message-header.is-user {
  flex-direction: row-reverse;
}

.chat-message-avatar {
  display: flex;
  width: 1.75rem;
  height: 1.75rem;
  flex: 0 0 1.75rem;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ui-control-border, hsl(var(--border)));
  border-radius: 999px;
  background: var(--ui-control-bg, hsl(var(--background)));
  color: var(--ui-fg-muted, hsl(var(--muted-foreground)));
  font-size: 0.6875rem;
  font-weight: 600;
}

.chat-message-avatar-user {
  border-color: var(--ui-accent-border, hsl(var(--foreground) / 0.18));
  background: var(--ui-accent-soft, hsl(var(--secondary)));
  color: var(--ui-accent-strong, hsl(var(--foreground)));
}

.chat-message-actions {
  display: flex;
  min-width: 0;
  max-width: min(26rem, calc(100vw - 8rem));
  flex-wrap: wrap;
  align-items: center;
  gap: 0.375rem;
  opacity: 1;
  transition: opacity var(--ui-duration-normal, 180ms) var(--ui-ease-out, ease);
}

@media (min-width: 640px) {
  .chat-message-actions {
    pointer-events: none;
    opacity: 0;
  }

  .chat-message-container:hover .chat-message-actions,
  .chat-message-container:focus-within .chat-message-actions {
    pointer-events: auto;
    opacity: 1;
  }
}

.chat-message-action {
  flex: 0 0 auto;
  width: 1.75rem;
  height: 1.75rem;
}

.chat-message-bubble {
  box-sizing: border-box;
  min-width: 0;
  max-width: 100%;
  border: 1px solid var(--ui-panel-border, hsl(var(--border)));
  border-radius: 18px;
  background: var(--ui-panel-bg, hsl(var(--card)));
  box-shadow: var(--ui-panel-shadow, 0 8px 24px rgb(15 23 42 / 0.045));
  color: var(--ui-fg-strong, hsl(var(--foreground)));
  padding: 0.625rem 0.875rem;
  font-size: 0.875rem;
  line-height: 1.75;
}

.chat-message-bubble-wrap {
  position: relative;
  min-width: 0;
  max-width: 100%;
}

.chat-message-container.is-code-message .chat-message-bubble-wrap,
.chat-message-container.is-code-message .chat-message-bubble,
.chat-message-container.is-code-message .chat-message-content {
  width: 100%;
}

.chat-message-error-card {
  display: flex;
  max-width: var(--studio-message-width, min(100%, 44rem));
  align-items: flex-start;
  gap: 0.55rem;
  border: 1px solid rgb(254 202 202);
  border-radius: 14px;
  background: rgb(254 242 242);
  color: rgb(190 18 60);
  padding: 0.62rem 0.78rem;
  font-size: 0.835rem;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.chat-message-error-card p {
  margin: 0;
}

.chat-message-error-icon {
  flex: 0 0 auto;
  margin-top: 0.15rem;
}

.chat-message-container.is-image-message .chat-message-bubble-wrap {
  width: 100%;
}

.chat-message-content {
  position: relative;
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
}

.chat-message-content.is-markdown {
  overflow-wrap: normal;
}

.chat-message-container.is-image-message .chat-message-content {
  width: 100%;
}

.chat-message-container.is-single-image-result .chat-message-bubble-wrap,
.chat-message-container.is-single-image-result .chat-message-bubble,
.chat-message-container.is-single-image-result .chat-message-content,
.chat-message-container.is-single-image-result .studio-result-block,
.chat-message-container.is-single-image-result .studio-result-grid,
.chat-message-container.is-single-image-result .studio-result-item,
.chat-message-container.is-single-image-result .studio-result-media.has-image {
  inline-size: fit-content;
  width: fit-content;
  max-width: 100%;
}

.chat-message-container.is-single-image-result .studio-result-grid.is-single {
  grid-template-columns: minmax(0, auto);
}

.chat-message-content.is-collapsible {
  overflow: hidden;
  transition: max-height 0.18s ease;
}

.chat-message-content.is-collapsed {
  max-height: 12rem;
}

.chat-message-content.is-collapsed::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3.25rem;
  pointer-events: none;
  background: linear-gradient(180deg, transparent, var(--studio-bubble-fade-bg, hsl(var(--card))));
  content: '';
}

.chat-message-expand {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-top: 0.5rem;
  border-radius: 999px;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
  font-weight: 650;
  line-height: 1;
  transition: color 0.15s, background 0.15s;
}

.chat-message-expand:hover,
.chat-message-expand:focus-visible {
  color: hsl(var(--foreground));
}

.chat-message-bubble-user {
  --studio-bubble-fade-bg: hsl(var(--secondary));
  border-color: var(--ui-accent-border, hsl(var(--foreground) / 0.16));
  background: var(--ui-accent-soft, hsl(var(--secondary)));
}

.chat-message-bubble-assistant {
  --studio-bubble-fade-bg: hsl(var(--card));
  border-color: var(--ui-panel-border, hsl(var(--border)));
}

.chat-message-bubble-image {
  box-sizing: border-box;
  inline-size: 100%;
  min-width: 0;
  padding: 0.55rem;
}

.chat-message-bubble-image-pending {
  box-sizing: border-box;
  inline-size: 100%;
  padding: 0.55rem;
}

.chat-message-bubble-error {
  --studio-bubble-fade-bg: rgb(254 242 242);
  border-color: rgb(254 202 202);
  background: rgb(254 242 242);
}

.studio-user-prompt {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.studio-assistant-plain {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.studio-search-call-list {
  display: grid;
  gap: 0.4rem;
  margin-bottom: 0.75rem;
}

.studio-search-call {
  display: flex;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  min-height: 1.8rem;
  align-items: center;
  gap: 0.45rem;
  border-left: 2px solid hsl(var(--foreground) / 0.28);
  background: hsl(var(--muted) / 0.24);
  padding: 0.28rem 0.62rem;
  font-size: 0.75rem;
  line-height: 1.35;
}

.studio-search-call-icon {
  flex: 0 0 auto;
  color: hsl(var(--foreground) / 0.84);
}

.studio-search-call-label {
  flex: 0 0 auto;
  color: hsl(var(--foreground));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-weight: 700;
}

.studio-search-call-query {
  min-width: 0;
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.studio-attachment-line {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-top: 0.45rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
}

.studio-file-task {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 0.65rem;
}

.studio-file-task-icon {
  display: inline-flex;
  width: 1.75rem;
  height: 1.75rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.45rem;
  background: hsl(var(--muted) / 0.72);
  color: hsl(var(--muted-foreground));
}

.studio-file-task.is-success .studio-file-task-icon {
  background: hsl(var(--tone-success-bg, 142 76% 95%));
  color: hsl(var(--tone-success-strong, 142 71% 35%));
}

.studio-file-task.is-error .studio-file-task-icon {
  background: hsl(var(--tone-error-bg, 0 86% 97%));
  color: hsl(var(--tone-error-strong, 0 72% 51%));
}

.studio-file-task-body {
  display: grid;
  min-width: 0;
  gap: 0.18rem;
}

.studio-file-task-body strong {
  color: hsl(var(--foreground));
  font-size: 0.82rem;
  font-weight: 750;
  line-height: 1.35;
}

.studio-file-task-body > span,
.studio-file-task-body > p {
  margin: 0;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.studio-file-task.is-error .studio-file-task-body > p {
  color: hsl(var(--tone-error-foreground, 0 72% 42%));
}

.studio-file-task-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.45rem;
}

.studio-file-task-action {
  display: inline-flex;
  min-height: 1.85rem;
  align-items: center;
  justify-content: center;
  gap: 0.32rem;
  border: 1px solid var(--ui-control-border, hsl(var(--border)));
  border-radius: 0.4rem;
  background: var(--ui-control-bg, hsl(var(--background)));
  color: hsl(var(--foreground));
  padding: 0.3rem 0.55rem;
  font-size: 0.72rem;
  font-weight: 700;
  font-family: inherit;
  line-height: 1;
  text-decoration: none;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.studio-file-task-action:disabled {
  cursor: wait;
  opacity: 0.56;
}

.studio-file-task-action:hover,
.studio-file-task-action:focus-visible {
  border-color: var(--ui-control-hover-border, hsl(var(--foreground) / 0.2));
  background: var(--ui-control-hover-bg, hsl(var(--secondary)));
}

.studio-message-reference-strip {
  --studio-message-reference-thumb-size: 5.75rem;
  display: flex;
  width: fit-content;
  max-width: min(100%, 20rem);
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.45rem;
  margin-top: 0.45rem;
  margin-left: auto;
}

.studio-message-reference-thumb {
  display: flex;
  width: var(--studio-message-reference-thumb-size);
  height: var(--studio-message-reference-thumb-size);
  flex: 0 0 var(--studio-message-reference-thumb-size);
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 0.75rem;
  background: hsl(var(--card));
  padding: 0;
  cursor: zoom-in;
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.06);
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}

.studio-message-reference-thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.studio-message-reference-thumb:hover,
.studio-message-reference-thumb:focus-visible {
  border-color: hsl(var(--foreground) / 0.28);
  box-shadow: 0 8px 18px -16px rgb(15 23 42 / 0.72);
  outline: none;
  transform: translateY(-1px);
}

.studio-search-source-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.42rem;
  margin-top: 0.65rem;
  border: 1px solid hsl(var(--primary) / 0.18);
  border-radius: 999px;
  background:
    linear-gradient(135deg, hsl(var(--primary) / 0.1), hsl(var(--muted) / 0.42));
  color: hsl(var(--foreground));
  padding: 0.34rem 0.68rem 0.34rem 0.5rem;
  font-size: 0.72rem;
  font-weight: 720;
  line-height: 1;
  box-shadow: 0 8px 22px hsl(var(--primary) / 0.08);
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s, transform 0.15s;
}

.studio-search-source-chip-icon {
  display: inline-flex;
  width: 0.9rem;
  height: 0.9rem;
  flex: 0 0 0.9rem;
  color: hsl(var(--primary));
}

.studio-search-source-chip-label {
  color: hsl(var(--foreground));
}

.studio-search-source-chip strong {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.15rem;
  height: 1.15rem;
  border-radius: 999px;
  background: hsl(var(--primary) / 0.13);
  color: hsl(var(--primary));
  font-size: 0.68rem;
  font-weight: 820;
}

.studio-search-source-chip small {
  border-left: 1px solid hsl(var(--primary) / 0.16);
  padding-left: 0.42rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.68rem;
  font-weight: 780;
}

.studio-search-source-chip:hover,
.studio-search-source-chip:focus-visible {
  border-color: hsl(var(--primary) / 0.34);
  background:
    linear-gradient(135deg, hsl(var(--primary) / 0.14), hsl(var(--secondary) / 0.72));
  box-shadow: 0 10px 26px hsl(var(--primary) / 0.12);
  transform: translateY(-1px);
}

.studio-search-image-groups {
  display: grid;
  gap: 0.45rem;
  margin-top: 0.65rem;
}

.studio-search-image-group {
  display: grid;
  gap: 0.42rem;
  border: 1px solid hsl(var(--border) / 0.68);
  border-radius: 0.78rem;
  background: hsl(var(--muted) / 0.32);
  padding: 0.56rem 0.62rem;
}

.studio-search-image-group-title {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: hsl(var(--foreground));
  font-size: 0.72rem;
  font-weight: 780;
  line-height: 1;
}

.studio-search-image-group-title svg {
  color: hsl(var(--primary));
}

.studio-search-image-group-queries {
  display: flex;
  flex-wrap: wrap;
  gap: 0.32rem;
}

.studio-search-image-query {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 1px solid hsl(var(--border) / 0.62);
  border-radius: 999px;
  background: hsl(var(--background) / 0.72);
  padding: 0.24rem 0.48rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.68rem;
  font-weight: 650;
}

.chat-message-bubble :deep(a[href^='studio-citation:']) {
  display: inline-flex;
  min-width: 1.12rem;
  height: 1.12rem;
  align-items: center;
  justify-content: center;
  margin: 0 0.08rem;
  border: 1px solid var(--ui-accent-border, hsl(var(--primary) / 0.28));
  border-radius: 999px;
  background: var(--ui-accent-soft, hsl(var(--primary) / 0.08));
  color: var(--ui-accent-strong, hsl(var(--primary)));
  font-size: 0.68em;
  font-weight: 800;
  line-height: 1;
  text-decoration: none;
  vertical-align: super;
}

.chat-message-bubble :deep(a[href^='studio-citation:']:hover),
.chat-message-bubble :deep(a[href^='studio-citation:']:focus-visible) {
  border-color: var(--ui-accent-border, hsl(var(--primary) / 0.5));
  background: hsl(var(--primary) / 0.12);
}

.chat-message-bubble :deep(.chat-markdown) {
  min-width: 0;
  color: inherit;
  line-height: 1.5;
  overflow-wrap: anywhere;
  word-wrap: break-word;
  word-break: normal;
}

.chat-message-bubble :deep(.chat-markdown > :first-child) {
  margin-top: 0;
}

.chat-message-bubble :deep(.chat-markdown > :last-child) {
  margin-bottom: 0;
}

.chat-message-bubble :deep(.chat-markdown p) {
  margin: 0 0 10px;
}

.chat-message-bubble :deep(.chat-markdown ul),
.chat-message-bubble :deep(.chat-markdown ol) {
  margin: 0.55rem 0;
  padding-left: 1.25rem;
}

.chat-message-bubble :deep(.chat-markdown ul) {
  list-style: disc;
}

.chat-message-bubble :deep(.chat-markdown ol) {
  list-style: decimal;
}

.chat-message-bubble :deep(.chat-markdown li) {
  margin: 0.25rem 0;
}

.chat-message-bubble :deep(.chat-markdown blockquote) {
  margin: 0.75rem 0;
  border-left: 3px solid rgb(113 113 122 / 0.32);
  padding-left: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.chat-message-bubble :deep(.chat-markdown pre) {
  box-sizing: border-box;
  max-width: 100%;
  max-height: min(60vh, 28rem);
  margin: 0 0 16px;
  overflow: auto;
  overflow-wrap: normal;
  word-break: normal;
  border: 0;
  border-radius: 6px;
  background: hsl(var(--muted) / 0.48);
  padding: 16px 16px 8px;
  color: hsl(var(--foreground));
  direction: ltr;
  font-family: var(--font-ui-mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace);
  font-size: 85%;
  line-height: 1.45;
  tab-size: 2;
  text-align: left;
}

.chat-message-bubble :deep(.chat-markdown code) {
  border-radius: 0.35rem;
  background: hsl(var(--muted) / 0.55);
  padding: 0.1rem 0.25rem;
  font-size: 0.84em;
}

.chat-message-bubble :deep(.chat-markdown pre code) {
  display: block;
  width: 100%;
  min-width: 100%;
  max-width: none;
  overflow-wrap: normal;
  word-break: normal;
  white-space: pre;
  background: transparent;
  border: 0;
  padding: 0;
  color: inherit;
  font-size: inherit;
  line-height: inherit;
}

.chat-message-bubble :deep(.chat-markdown .studio-code-shell) {
  position: relative;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  margin: 0 0 16px;
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 0.72);
  border-radius: 8px;
  background: hsl(var(--muted) / 0.48);
}

.chat-message-bubble :deep(.chat-markdown .studio-code-header) {
  display: flex;
  min-height: 2rem;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  border-bottom: 1px solid hsl(var(--border) / 0.58);
  background: hsl(var(--muted) / 0.32);
  padding: 0.35rem 0.55rem 0.35rem 0.7rem;
}

.chat-message-bubble :deep(.chat-markdown .studio-code-language) {
  min-width: 0;
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-family: var(--font-ui-mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace);
  font-size: 0.68rem;
  font-weight: 650;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-message-bubble :deep(.chat-markdown .studio-code-pre) {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  max-height: min(60vh, 28rem);
  margin: 0;
  overflow: auto;
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0.85rem 1rem;
}

.chat-message-bubble :deep(.chat-markdown .studio-code-copy) {
  display: inline-flex;
  height: 1.45rem;
  min-width: 2.75rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
  background: hsl(var(--background) / 0.94);
  padding: 0 0.45rem;
  color: hsl(var(--foreground));
  cursor: pointer;
  font-size: 0.68rem;
  font-weight: 650;
  line-height: 1;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.chat-message-bubble :deep(.chat-markdown .studio-code-copy:hover),
.chat-message-bubble :deep(.chat-markdown .studio-code-copy:focus-visible) {
  border-color: hsl(var(--foreground) / 0.14);
  background: hsl(var(--background));
  color: hsl(var(--foreground));
}

.chat-message-bubble :deep(.hljs-comment),
.chat-message-bubble :deep(.hljs-quote) {
  color: #6b7280;
}

.chat-message-bubble :deep(.hljs-keyword),
.chat-message-bubble :deep(.hljs-selector-tag),
.chat-message-bubble :deep(.hljs-subst) {
  color: #7c3aed;
}

.chat-message-bubble :deep(.hljs-string),
.chat-message-bubble :deep(.hljs-doctag) {
  color: #047857;
}

.chat-message-bubble :deep(.hljs-number),
.chat-message-bubble :deep(.hljs-literal),
.chat-message-bubble :deep(.hljs-variable),
.chat-message-bubble :deep(.hljs-template-variable),
.chat-message-bubble :deep(.hljs-tag .hljs-attr) {
  color: #b45309;
}

.chat-message-bubble :deep(.hljs-title),
.chat-message-bubble :deep(.hljs-section),
.chat-message-bubble :deep(.hljs-selector-id) {
  color: #2563eb;
}

.chat-message-bubble :deep(.hljs-type),
.chat-message-bubble :deep(.hljs-class .hljs-title) {
  color: #0f766e;
}

.chat-message-bubble :deep(.hljs-tag),
.chat-message-bubble :deep(.hljs-name),
.chat-message-bubble :deep(.hljs-attribute) {
  color: #be123c;
}

.studio-error-text {
  margin-top: 0.45rem;
  color: rgb(190 18 60);
  font-size: 0.8125rem;
  line-height: 1.6;
}

.studio-cursor {
  display: inline-block;
  width: 0.45rem;
  height: 1rem;
  border-radius: 999px;
  background: hsl(var(--primary));
  animation: studio-cursor 1s ease-in-out infinite;
}

@keyframes studio-cursor {
  0%, 100% { opacity: 0.2; }
  50% { opacity: 1; }
}

.studio-image-status {
  display: flex;
  min-width: 0;
  width: 100%;
  min-height: 3.25rem;
  align-items: center;
  gap: 0.5rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.8125rem;
  line-height: 1.6;
}

.studio-image-status.is-error {
  align-items: flex-start;
  color: rgb(185 28 28);
}

.studio-result-block {
  display: block;
  width: 100%;
  max-width: 100%;
}

.studio-result-block-pending {
  width: 100%;
}

.studio-result-grid {
  display: grid;
  width: 100%;
  max-width: 100%;
  grid-template-columns: repeat(var(--studio-image-grid-columns), minmax(0, 1fr));
  gap: 0.625rem;
}

.studio-result-grid.is-single {
  grid-template-columns: minmax(0, 1fr);
}

.studio-result-item {
  width: 100%;
  min-width: 0;
}

.studio-result-grid.is-single .studio-result-item {
  width: 100%;
}

.studio-result-media {
  display: flex;
  box-sizing: border-box;
  width: 100%;
  min-width: 100%;
  min-height: 0;
  aspect-ratio: var(--studio-image-aspect-ratio);
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 0.72);
  border-radius: 0.75rem;
  background: hsl(var(--secondary) / 0.35);
  color: inherit;
  cursor: zoom-in;
}

.studio-result-media.has-image {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  aspect-ratio: auto;
  background: hsl(var(--secondary) / 0.18);
  padding: 0;
}

.studio-result-media img {
  display: block;
  width: 100%;
  height: auto;
  max-width: 100%;
  border-radius: 0.75rem;
  object-fit: contain;
}

.chat-message-container.is-single-image-result .studio-result-media img {
  width: auto;
  max-width: min(100%, var(--studio-image-message-width, 18rem));
  max-height: min(56vh, 24rem);
}

.studio-result-media span {
  color: hsl(var(--muted-foreground));
  font-size: 0.8125rem;
}

.studio-result-placeholder {
  cursor: default;
  flex-direction: column;
  gap: 0.625rem;
  text-align: center;
}

.studio-result-placeholder svg {
  color: hsl(var(--muted-foreground));
}

.studio-result-placeholder-failed {
  border-style: dashed;
  background: hsl(var(--destructive) / 0.04);
}

.studio-result-placeholder-failed svg,
.studio-result-placeholder-failed span {
  color: hsl(var(--destructive) / 0.82);
}

.studio-result-placeholder span,
.studio-result-placeholder small {
  display: block;
  max-width: calc(100% - 1rem);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.studio-result-placeholder small {
  color: hsl(var(--muted-foreground) / 0.78);
  font-size: 0.75rem;
}

.studio-result-caption {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
  padding: 0.35rem 0.125rem 0;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
}

.studio-result-caption-label {
  flex: 0 0 auto;
}

.studio-result-actions {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}

.studio-result-action {
  white-space: nowrap;
}

@media (max-width: 720px) {
  .chat-message-container {
    max-width: min(100%, 38rem);
  }

  .chat-message-container.is-pending-image-message {
    width: min(100%, var(--studio-image-message-width, 16.5rem));
    min-width: 0;
    max-width: 100%;
  }

  .chat-message-container.is-image-message {
    width: min(100%, var(--studio-image-message-width, 16.5rem));
    min-width: 0;
    max-width: 100%;
  }

  .chat-message-container.is-single-image-result {
    width: fit-content;
    max-width: min(100%, var(--studio-image-message-width, 16.5rem));
  }

  .studio-result-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .chat-message-actions {
    max-width: calc(100vw - 5.5rem);
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 1px;
  }

  .studio-message-reference-strip {
    --studio-message-reference-thumb-size: 5rem;
    max-width: min(100%, 16rem);
  }
}
</style>
