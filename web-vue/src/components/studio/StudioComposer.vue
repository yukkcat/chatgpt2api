<template>
  <footer ref="composerShellRef" class="studio-composer-shell">
    <input
      ref="fileInputRef"
      type="file"
      accept="image/*"
      multiple
      class="hidden"
      @change="handleFileChange"
    />

    <form
      class="chat-input-panel"
      :class="{ 'is-dragging': isDragging }"
      @submit.prevent="$emit('submit')"
      @dragenter.prevent="handleDragEnter"
      @dragover.prevent="handleDragOver"
      @dragleave="handleDragLeave"
      @drop.prevent="handleDrop"
      @click="textareaRef?.focus()"
    >
      <div class="chat-input-panel-shell">
        <div v-if="isEditing" class="chat-editing-bar" @click.stop>
          <div class="chat-editing-info">
            <Icon icon="lucide:pencil" class="h-3.5 w-3.5" />
            <span>正在编辑原消息，发送后会替换该消息并重新生成后续回复。</span>
          </div>
          <button type="button" class="chat-editing-cancel" @click="$emit('cancel-edit')">
            取消
          </button>
        </div>

        <div
          class="chat-input-panel-inner"
          :class="{ 'chat-input-panel-inner-attach': references.length }"
          @click="textareaRef?.focus()"
        >
          <div v-if="canAttachReferences && references.length" class="attach-images">
            <div v-for="(source, index) in references" :key="source.id" class="chat-attachment-preview">
              <button type="button" class="studio-reference-preview" :title="source.name" @click.stop="$emit('preview-reference', source)">
                <img v-if="source.dataUrl" :src="source.dataUrl" :alt="source.name" />
                <Icon v-else icon="lucide:image" class="h-5 w-5" />
              </button>
              <button type="button" class="chat-attachment-remove" :aria-label="`移除 ${source.name}`" @click.stop="$emit('remove-reference', index)">
                <Icon icon="lucide:x" class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <textarea
            ref="textareaRef"
            v-model="textValue"
            class="chat-input custom-scrollbar"
            rows="1"
            :placeholder="placeholderText"
            @input="resizeTextarea"
            @paste="handlePaste"
            @keydown.enter.exact.prevent="$emit('submit')"
          ></textarea>
        </div>

        <div class="chat-input-actions" @click.stop>
          <div class="chat-input-action-row">
            <div class="chat-menu-anchor">
              <Button
                icon-only
                size="sm"
                variant="outline"
                root-class="chat-vision-button"
                :disabled="isSending"
                aria-label="上传图片"
                title="上传图片"
                @click.stop="handleAttachReferenceClick"
              >
                <Icon icon="lucide:image-plus" class="h-3.5 w-3.5" />
              </Button>
            </div>

            <div class="chat-select-wrap chat-select-wrap--mode">
              <GroupedSelectMenu
                v-model="modeValue"
                :options="modeOptions"
                placement="top"
                selected-indicator="none"
                aria-label="切换模式"
              />
            </div>

            <StudioToolbarSelectButton
              v-if="mode === 'image'"
              class="chat-prompt-button"
              :disabled="isSending"
              @click.stop="handleOpenPrompts"
            >
              <Icon icon="lucide:book-open" class="h-3.5 w-3.5" />
              <span>提示词</span>
            </StudioToolbarSelectButton>

            <StudioToolbarSelectButton
              v-if="mode === 'search'"
              class="chat-search-skill-button"
              :disabled="isSending"
              title="搜索 Skill"
              @click.stop="handleOpenSearchSkill"
            >
              <Icon icon="lucide:package-plus" class="h-3.5 w-3.5" />
              <span>Skill</span>
            </StudioToolbarSelectButton>

            <template v-if="mode === 'chat'">
              <div class="chat-settings-anchor chat-settings-anchor--chat">
                <FloatingActionMenu
                  :label="chatSettingsLabel"
                  :items="chatSettingsMenuItems"
                  align="left"
                  placement="top"
                  trigger-variant="input"
                  trigger-class="shrink-0 whitespace-nowrap"
                  :menu-min-width="220"
                  @select="handleChatSettingsMenuSelect"
                />
              </div>
            </template>

            <template v-else-if="mode === 'image'">
              <div ref="settingsAnchorRef" class="chat-settings-anchor">
                <StudioToolbarSelectButton
                  class="chat-summary-button justify-between gap-1.5"
                  :expanded="settingsOpen"
                  @click.stop="toggleSettings"
                >
                  <Icon icon="lucide:sliders-horizontal" class="h-3.5 w-3.5" />
                  <span>{{ imageSummaryLabel }}</span>
                  <Icon
                    icon="lucide:chevron-down"
                    class="h-3.5 w-3.5 transition-transform"
                    :class="settingsOpen ? 'rotate-180' : ''"
                  />
                </StudioToolbarSelectButton>

                <div v-if="settingsOpen" class="studio-size-popover" @click.stop>
                  <div class="studio-size-section">
                    <div class="studio-size-label">模型</div>
                    <GroupedSelectMenu
                      v-model="imageModelValue"
                      :options="imageModelSelectOptions"
                      selected-indicator="none"
                      block
                    />
                  </div>
                  <div class="studio-size-section">
                    <div class="studio-size-label">质量</div>
                    <div class="studio-choice-grid is-quality">
                      <Button
                        v-for="option in IMAGE_QUALITY_OPTIONS"
                        :key="option.value"
                        size="sm"
                        :variant="imageForm.quality === option.value ? 'primary' : 'outline'"
                        block
                        root-class="studio-choice-button"
                        @click="$emit('update:imageQuality', option.value)"
                      >
                        {{ option.label }}
                      </Button>
                    </div>
                  </div>
                  <div class="studio-size-section">
                    <div class="studio-size-label">数量</div>
                    <div class="studio-choice-grid is-count">
                      <Button
                        v-for="option in IMAGE_COUNT_OPTIONS"
                        :key="option.value"
                        size="sm"
                        :variant="imageForm.n === option.value ? 'primary' : 'outline'"
                        block
                        root-class="studio-choice-button"
                        @click="$emit('update:imageCount', option.value)"
                      >
                        {{ option.label }}
                      </Button>
                    </div>
                  </div>
                  <div class="studio-size-section">
                    <div class="studio-size-label">比例</div>
                    <div class="studio-choice-grid is-ratio">
                      <Button
                        v-for="option in ratioOptions"
                        :key="option.value"
                        size="sm"
                        :variant="selectedRatio === option.value ? 'primary' : 'outline'"
                        block
                        root-class="studio-choice-button"
                        @click="selectRatio(option.value)"
                      >
                        {{ option.label }}
                      </Button>
                    </div>
                  </div>
                  <div class="studio-size-section">
                    <div class="studio-size-label">分辨率</div>
                    <div class="studio-choice-grid is-resolution">
                      <Button
                        v-for="option in resolutionOptions"
                        :key="option.value"
                        size="sm"
                        :variant="selectedResolution === option.value ? 'primary' : 'outline'"
                        block
                        root-class="studio-choice-button"
                        @click="selectResolution(option.value)"
                      >
                        {{ option.label }}
                      </Button>
                    </div>
                    <p class="studio-size-current">{{ selectedSizeDetailLabel }}</p>
                  </div>
                </div>
              </div>
            </template>

            <template v-else-if="mode === 'file'">
              <div class="chat-select-wrap chat-select-wrap--file">
                <GroupedSelectMenu
                  v-model="fileKindValue"
                  :options="fileKindOptions"
                  placement="top"
                  selected-indicator="none"
                  aria-label="选择文件类型"
                />
              </div>
              <StudioToolbarSelectButton
                class="chat-recent-file-tasks-button"
                :disabled="isSending"
                title="最近文件任务"
                @click.stop="handleOpenRecentFileTasks"
              >
                <Icon icon="lucide:history" class="h-3.5 w-3.5" />
                <span>最近</span>
              </StudioToolbarSelectButton>
            </template>
          </div>

          <div class="chat-input-submit-row">
            <button
              v-if="isStreaming"
              type="button"
              class="chat-input-send chat-input-send-danger"
              aria-label="停止输出"
              @click.stop="$emit('stop')"
            >
              <Icon icon="lucide:square" class="h-4 w-4" />
              <span class="chat-input-send-label">停止</span>
            </button>
            <button
              v-else
              type="submit"
              class="chat-input-send"
              :class="text.trim() && !isSending ? 'chat-input-send-ready' : 'chat-input-send-idle'"
              :disabled="isSending || !text.trim()"
              :aria-label="submitAriaLabel"
              @click.stop
            >
              <Icon :icon="isSending ? 'lucide:loader-circle' : 'lucide:send-horizontal'" class="h-4 w-4" :class="{ 'animate-spin': isSending }" />
              <span class="chat-input-send-label">{{ submitLabel }}</span>
            </button>
          </div>
        </div>
      </div>

      <div v-if="isDragging" class="studio-drop-overlay">
        <Icon icon="lucide:image-plus" class="h-5 w-5" />
        松开以添加参考图
      </div>
    </form>
  </footer>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Button } from 'nanocat-ui'
import type { ActionMenuItem } from 'nanocat-ui'
import FloatingActionMenu from '@/components/ai/FloatingActionMenu.vue'
import { GroupedSelectMenu } from 'nanocat-ui'
import StudioToolbarSelectButton from '@/components/studio/StudioToolbarSelectButton.vue'
import {
  DEFAULT_IMAGE_SIZE,
  IMAGE_COUNT_OPTIONS,
  IMAGE_QUALITY_OPTIONS,
  formatImageSizeLabel,
  resolveImageSizePresets,
  type ImageSizeResolution,
} from '@/api/imageTasks'
import type { StudioComposeMode, StudioFileKind, StudioImageForm, StudioReference } from './types'

type ComposerMenuItem = ActionMenuItem & {
  active?: boolean
  children?: ComposerMenuItem[]
}

const props = defineProps<{
  mode: StudioComposeMode
  fileKind: StudioFileKind
  text: string
  chatModel: string
  chatReasoningEffort: string
  imageForm: StudioImageForm
  chatModelOptions: string[]
  imageModelOptions: string[]
  imageHighResolutionEnabled: boolean
  references: StudioReference[]
  isSending: boolean
  isStreaming: boolean
  isEditing: boolean
}>()

const emit = defineEmits<{
  'update:mode': [mode: StudioComposeMode]
  'update:fileKind': [kind: StudioFileKind]
  'update:text': [text: string]
  'update:chatModel': [model: string]
  'update:chatReasoningEffort': [effort: string]
  'update:imageModel': [model: string]
  'update:imageSize': [size: string]
  'update:imageQuality': [quality: string]
  'update:imageCount': [count: number]
  submit: []
  stop: []
  'cancel-edit': []
  'add-files': [files: File[]]
  'remove-reference': [index: number]
  'clear-references': []
  'preview-reference': [reference: StudioReference]
  'open-prompts': []
  'open-search-skill': []
  'open-recent-file-tasks': []
}>()

const composerShellRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const settingsAnchorRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const settingsOpen = ref(false)
let textareaResizeFrame = 0
let composerResizeObserver: ResizeObserver | null = null

const modeOptions: Array<{ label: string; value: StudioComposeMode }> = [
  { label: '对话', value: 'chat' },
  { label: '画图', value: 'image' },
  { label: '搜索', value: 'search' },
  { label: '文件', value: 'file' },
]

const fileKindOptions: Array<{ label: string; value: StudioFileKind }> = [
  { label: 'PPT', value: 'ppt' },
  { label: 'PSD', value: 'psd' },
]

const textValue = computed({
  get: () => props.text,
  set: (value: string) => emit('update:text', value),
})

const chatModelValue = computed({
  get: () => props.chatModel,
  set: (value: string | string[]) => emit('update:chatModel', String(Array.isArray(value) ? value[0] : value || 'auto')),
})

const chatReasoningEffortValue = computed({
  get: () => props.chatReasoningEffort || 'default',
  set: (value: string | string[]) => {
    const next = String(Array.isArray(value) ? value[0] : value || 'default')
    emit('update:chatReasoningEffort', next === 'default' ? '' : next)
  },
})

const modeValue = computed({
  get: () => props.mode,
  set: (value: string | string[]) => {
    const next = String(Array.isArray(value) ? value[0] : value || props.mode)
    if (next === 'chat' || next === 'search' || next === 'image' || next === 'file') {
      closeFloatingMenus()
      emit('update:mode', next)
    }
  },
})

const fileKindValue = computed({
  get: () => props.fileKind,
  set: (value: string | string[]) => {
    const next = String(Array.isArray(value) ? value[0] : value || props.fileKind)
    if (next === 'ppt' || next === 'psd') emit('update:fileKind', next)
  },
})

const imageModelValue = computed({
  get: () => props.imageForm.model,
  set: (value: string | string[]) => emit('update:imageModel', String(Array.isArray(value) ? value[0] : value || '')),
})

const chatModelSelectOptions = computed(() => props.chatModelOptions.map((model) => ({
  label: model === 'auto' ? '自动模型' : model,
  value: model,
})))

const chatReasoningEffortOptions = [
  { label: '默认', value: 'default' },
  { label: '低', value: 'low' },
  { label: '中', value: 'medium' },
  { label: '高', value: 'high' },
  { label: '超高', value: 'extended' },
]

const imageModelSelectOptions = computed(() => props.imageModelOptions.map((model) => ({
  label: model,
  value: model,
})))

const sizePresets = computed(() => resolveImageSizePresets(props.imageHighResolutionEnabled))
const selectedPreset = computed(() => sizePresets.value.find((preset) => preset.value === props.imageForm.size))
const selectedRatio = computed(() => selectedPreset.value?.ratio || 'auto')
const selectedResolution = computed(() => selectedPreset.value?.resolution || 'auto')
const ratioOptions = computed(() => {
  const seen = new Set<string>()
  return sizePresets.value
    .filter((preset) => {
      if (seen.has(preset.ratio)) return false
      seen.add(preset.ratio)
      return true
    })
    .map((preset) => ({ label: preset.ratio === 'auto' ? '自动' : preset.ratio, value: preset.ratio }))
})
const resolutionOptions = computed(() => {
  const order: ImageSizeResolution[] = ['auto', '1K', '2K', '4K']
  const values = new Set(sizePresets.value.map((preset) => preset.resolution))
  return order.filter((value) => values.has(value)).map((value) => ({ label: value === 'auto' ? '自动' : value, value }))
})
const selectedSizeDetailLabel = computed(() => formatImageSizeLabel(props.imageForm.size))
const canAttachReferences = computed(() => props.mode === 'image' || props.mode === 'chat' || props.mode === 'file')
const selectedChatModelLabel = computed(() => chatModelSelectOptions.value.find((option) => option.value === props.chatModel)?.label || props.chatModel || '自动模型')
const selectedReasoningEffortLabel = computed(() => {
  const current = props.chatReasoningEffort || 'default'
  return chatReasoningEffortOptions.find((option) => option.value === current)?.label || current
})
const chatSettingsLabel = computed(() => {
  const model = compactModelLabel(props.chatModel)
  const reasoning = selectedReasoningEffortLabel.value
  return reasoning === '默认' ? model : `${model} ${reasoning}`
})
const chatSettingsMenuItems = computed<ComposerMenuItem[]>(() => [
  {
    key: 'reasoning-heading',
    label: '推理',
    heading: true,
  },
  ...chatReasoningEffortOptions
    .filter((option) => option.value !== 'default')
    .map((option) => ({
      key: `reasoning:${option.value}`,
      label: option.label,
      active: (props.chatReasoningEffort || 'default') === option.value,
    })),
  {
    key: 'model-menu',
    label: selectedChatModelLabel.value,
    dividerBefore: true,
    children: [
      { key: 'model-heading', label: '模型', heading: true },
      ...chatModelSelectOptions.value.map((option) => ({
        key: `model:${option.value}`,
        label: option.label,
        active: props.chatModel === option.value,
      })),
    ],
  },
])
const imageSummaryLabel = computed(() => {
  const count = props.imageForm.n > 1 ? ` · ${props.imageForm.n} 张` : ''
  return `${formatImageSizeLabel(props.imageForm.size)}${count}`
})
const imagePlaceholder = computed(() => props.references.length ? '描述你想如何修改参考图' : '输入你想生成的画面，也可以粘贴或拖入参考图')
const chatPlaceholder = computed(() => props.references.length ? '描述你想让模型识别或分析的图片' : '输入消息，Enter 发送，Shift+Enter 换行')
const filePlaceholder = computed(() => {
  const kind = props.fileKind === 'psd' ? 'PSD' : 'PPT'
  return props.references.length
    ? `描述你想根据参考图生成的 ${kind}`
    : `描述你想生成的 ${kind}，也可以粘贴或拖入参考图`
})
const placeholderText = computed(() => {
  if (props.mode === 'image') return imagePlaceholder.value
  if (props.mode === 'file') return filePlaceholder.value
  if (props.mode === 'search') return '输入搜索问题，Enter 搜索，Shift+Enter 换行'
  return chatPlaceholder.value
})
const submitAriaLabel = computed(() => {
  if (props.mode === 'image') return '提交图片任务'
  if (props.mode === 'file') return `生成 ${props.fileKind === 'psd' ? 'PSD' : 'PPT'}`
  return '发送消息'
})
const submitLabel = computed(() => {
  if (props.isEditing) return '保存'
  return props.mode === 'file' ? '生成' : '发送'
})

function toggleSettings() {
  const next = !settingsOpen.value
  closeFloatingMenus()
  settingsOpen.value = next
}

function closeFloatingMenus() {
  settingsOpen.value = false
}

function handleOpenPrompts() {
  closeFloatingMenus()
  emit('open-prompts')
}

function handleOpenSearchSkill() {
  closeFloatingMenus()
  emit('open-search-skill')
}

function handleOpenRecentFileTasks() {
  closeFloatingMenus()
  emit('open-recent-file-tasks')
}

function handleAttachReferenceClick() {
  closeFloatingMenus()
  if (props.mode === 'search') {
    emit('update:mode', 'chat')
    void nextTick(() => fileInputRef.value?.click())
    return
  }
  fileInputRef.value?.click()
}

function handleChatSettingsMenuSelect(key: string) {
  closeFloatingMenus()
  if (key.startsWith('reasoning:')) {
    chatReasoningEffortValue.value = key.slice('reasoning:'.length)
  } else if (key.startsWith('model:')) {
    chatModelValue.value = key.slice('model:'.length)
  }
}

function compactModelLabel(model: string) {
  const normalized = String(model || '').trim()
  if (!normalized || normalized === 'auto') return '自动'
  return normalized.replace(/^gpt-/i, '')
}

function resizeTextarea() {
  if (typeof window === 'undefined') return
  if (textareaResizeFrame) window.cancelAnimationFrame(textareaResizeFrame)
  textareaResizeFrame = window.requestAnimationFrame(() => {
    textareaResizeFrame = 0
    const element = textareaRef.value
    if (!element) return
    element.style.height = 'auto'
    const maxHeight = Number.parseFloat(window.getComputedStyle(element).maxHeight) || 192
    const nextHeight = Math.min(element.scrollHeight, maxHeight)
    element.style.height = `${nextHeight}px`
    element.style.overflowY = element.scrollHeight > maxHeight + 1 ? 'auto' : 'hidden'
  })
}

function scheduleTextareaResize() {
  void nextTick(resizeTextarea)
}

function syncComposerHeight() {
  const shell = composerShellRef.value
  const parent = shell?.parentElement
  if (!shell || !parent) return
  parent.style.setProperty('--studio-composer-height', `${Math.ceil(shell.offsetHeight)}px`)
}

function selectRatio(ratio: string) {
  const auto = sizePresets.value.find((preset) => preset.value === DEFAULT_IMAGE_SIZE)
  if (ratio === 'auto') {
    emit('update:imageSize', auto?.value || DEFAULT_IMAGE_SIZE)
    return
  }
  const exact = selectedResolution.value !== 'auto'
    ? sizePresets.value.find((preset) => preset.ratio === ratio && preset.resolution === selectedResolution.value)
    : undefined
  const next = exact || sizePresets.value.find((preset) => preset.ratio === ratio) || auto
  emit('update:imageSize', next?.value || DEFAULT_IMAGE_SIZE)
}

function selectResolution(resolution: ImageSizeResolution) {
  const auto = sizePresets.value.find((preset) => preset.value === DEFAULT_IMAGE_SIZE)
  if (resolution === 'auto') {
    emit('update:imageSize', auto?.value || DEFAULT_IMAGE_SIZE)
    return
  }
  const exact = selectedRatio.value !== 'auto'
    ? sizePresets.value.find((preset) => preset.ratio === selectedRatio.value && preset.resolution === resolution)
    : undefined
  const next = exact || sizePresets.value.find((preset) => preset.resolution === resolution) || auto
  emit('update:imageSize', next?.value || DEFAULT_IMAGE_SIZE)
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  emit('add-files', Array.from(input.files || []))
  input.value = ''
}

function handlePaste(event: ClipboardEvent) {
  if (!canAttachReferences.value) return
  const files = Array.from(event.clipboardData?.files || []).filter(isImageFile)
  if (!files.length) return
  event.preventDefault()
  emit('add-files', files)
}

function handleDragEnter() {
  if (canAttachReferences.value) isDragging.value = true
}

function handleDragOver() {
  if (canAttachReferences.value) isDragging.value = true
}

function handleDrop(event: DragEvent) {
  isDragging.value = false
  if (!canAttachReferences.value) return
  emit('add-files', Array.from(event.dataTransfer?.files || []))
}

function handleDragLeave(event: DragEvent) {
  const current = event.currentTarget as HTMLElement
  if (event.relatedTarget instanceof Node && current.contains(event.relatedTarget)) return
  isDragging.value = false
}

function isImageFile(file: File) {
  return file.type.startsWith('image/') || /\.(avif|bmp|gif|heic|heif|ico|jpe?g|png|svg|tiff?|webp)$/i.test(file.name)
}

function handleOutsideClick(event: MouseEvent) {
  if (!settingsOpen.value) return
  const target = event.target as Node
  if (settingsAnchorRef.value?.contains(target)) return
  closeFloatingMenus()
}

if (typeof window !== 'undefined') {
  window.addEventListener('click', handleOutsideClick)
}

onMounted(() => {
  scheduleTextareaResize()
  syncComposerHeight()
  if (typeof ResizeObserver !== 'undefined' && composerShellRef.value) {
    composerResizeObserver = new ResizeObserver(syncComposerHeight)
    composerResizeObserver.observe(composerShellRef.value)
  }
})

watch(
  () => [props.text, props.mode, props.references.length, props.isEditing],
  scheduleTextareaResize,
  { flush: 'post' },
)

watch(
  () => props.mode,
  () => closeFloatingMenus(),
)

onBeforeUnmount(() => {
  if (typeof window === 'undefined') return
  if (textareaResizeFrame) window.cancelAnimationFrame(textareaResizeFrame)
  composerResizeObserver?.disconnect()
  composerResizeObserver = null
  composerShellRef.value?.parentElement?.style.removeProperty('--studio-composer-height')
  window.removeEventListener('click', handleOutsideClick)
})
</script>

<style scoped>
.studio-composer-shell {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 20;
  width: 100%;
  background: transparent;
  flex: 0 0 auto;
  pointer-events: none;
}

.studio-composer-shell::before {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3.65rem;
  pointer-events: none;
  background: hsl(var(--card));
  content: '';
}

.chat-input-panel {
  position: relative;
  z-index: 1;
  width: 100%;
  box-sizing: border-box;
  background: transparent;
  padding: 0.35rem 1rem 0.55rem;
  pointer-events: none;
  transition: border-color 0.15s, background 0.15s;
}

.chat-input-panel.is-dragging {
  pointer-events: auto;
  background: hsl(var(--secondary) / 0.72);
}

.chat-input-panel-shell {
  position: relative;
  z-index: 1;
  display: flex;
  width: min(100%, 48rem);
  margin: 0 auto;
  flex-direction: column;
  gap: 0.6rem;
  border: 1px solid hsl(var(--border) / 0.82);
  border-radius: 1.4rem;
  background: hsl(var(--background));
  padding: 0.55rem;
  pointer-events: auto;
  box-shadow: var(--shadow-elevated);
}

.chat-editing-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  border: 1px solid hsl(var(--primary) / 0.18);
  border-radius: 1rem;
  background: hsl(var(--primary) / 0.07);
  padding: 0.45rem 0.65rem;
  color: hsl(var(--foreground));
  font-size: 0.78rem;
}

.chat-editing-info {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 0.45rem;
}

.chat-editing-info span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-editing-cancel {
  flex: 0 0 auto;
  border: 0;
  background: transparent;
  color: hsl(var(--primary));
  font-size: 0.76rem;
  font-weight: 700;
  cursor: pointer;
}

.chat-input-actions {
  display: flex;
  min-height: 2.25rem;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.75rem;
  border-top: 1px solid hsl(var(--border) / 0.52);
  padding-top: 0.55rem;
}

.chat-input-action-row {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.375rem;
}

.chat-menu-anchor {
  position: relative;
  display: inline-flex;
  flex: 0 0 auto;
}

.chat-settings-anchor {
  position: relative;
  display: inline-flex;
  flex: 0 0 auto;
}

.chat-summary-button,
:deep(.chat-summary-button) {
  max-width: min(14rem, 32vw);
}

.chat-summary-button span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-prompt-button {
  flex: 0 0 auto;
}

.chat-vision-button {
  flex: 0 0 auto;
}

.chat-select-wrap {
  display: inline-flex;
  min-width: 0;
  max-width: min(18rem, 45vw);
}

.chat-select-wrap--mode {
  flex: 0 0 auto;
}

.chat-select-wrap.chat-select-wrap--file {
  min-width: 4.75rem;
  max-width: 5.5rem;
  flex: 0 0 auto;
}

.chat-input-submit-row {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.chat-input-panel-inner {
  position: relative;
  display: block;
  min-height: 2.7rem;
  cursor: text;
  border: 0;
  border-radius: 1rem;
  background: transparent;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}

.chat-input-panel-inner:focus-within {
  background: transparent;
  box-shadow: none;
}

.chat-input-panel-inner-attach {
  min-height: 7.5rem;
}

.chat-input {
  width: 100%;
  height: 2.7rem;
  min-height: 2.7rem;
  max-height: 8.5rem;
  resize: none;
  overflow-y: hidden;
  border: 0;
  border-radius: 1rem;
  background: transparent;
  padding: 0.15rem 0.25rem 0.15rem 0.25rem;
  color: hsl(var(--foreground));
  font-family: inherit;
  font-size: 0.9375rem;
  line-height: 1.45;
  outline: none;
}

.chat-input-panel-inner-attach .chat-input {
  min-height: 2.7rem;
  padding-top: 0.15rem;
  padding-bottom: 0.2rem;
}

.chat-input::placeholder {
  color: hsl(var(--muted-foreground) / 0.62);
  font-family: inherit;
  font-weight: 400;
  letter-spacing: 0;
  opacity: 1;
}

.attach-images {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  overflow-x: auto;
  overflow-y: hidden;
  margin-bottom: 0.45rem;
  padding: 0.1rem 0 0.15rem;
}

.chat-attachment-preview {
  position: relative;
  width: 4rem;
  height: 4rem;
  flex: 0 0 auto;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 1rem;
  background: hsl(var(--card));
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
}

.studio-reference-preview {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: hsl(var(--secondary) / 0.65);
  color: hsl(var(--muted-foreground));
}

.studio-reference-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.chat-attachment-remove {
  position: absolute;
  top: 0.25rem;
  right: 0.25rem;
  display: inline-flex;
  width: 1.5rem;
  height: 1.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgb(15 23 42 / 0.72);
  color: white;
  opacity: 0;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.12);
  transition: opacity 0.15s, background 0.15s;
}

.chat-attachment-preview:hover .chat-attachment-remove,
.chat-attachment-remove:focus-visible {
  opacity: 1;
}

.chat-attachment-remove:hover {
  background: rgb(220 38 38);
}

.chat-input-send {
  display: inline-flex;
  width: 2.35rem;
  height: 2.35rem;
  flex: 0 0 2.35rem;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 0;
  font: inherit;
  font-size: 0.75rem;
  font-weight: 650;
  line-height: 1;
  outline: none;
  box-shadow: 0 10px 24px -18px rgb(15 23 42 / 0.84);
  transition: transform 0.15s, border-color 0.15s, background 0.15s, color 0.15s, opacity 0.15s, box-shadow 0.15s;
}

.chat-input-send:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.chat-input-send-ready {
  background: hsl(var(--foreground));
  color: hsl(var(--background));
}

.chat-input-send-idle {
  border-color: hsl(var(--border) / 0.72);
  background: hsl(var(--secondary) / 0.78);
  color: hsl(var(--muted-foreground));
  box-shadow: none;
}

.chat-input-send-ready:hover,
.chat-input-send-ready:focus-visible {
  background: hsl(var(--foreground) / 0.88);
  box-shadow: 0 14px 28px -18px rgb(15 23 42 / 0.96);
  transform: translateY(-1px);
}

.chat-input-send-danger {
  border-color: rgb(248 113 113 / 0.32);
  background: rgb(254 242 242);
  color: rgb(220 38 38);
}

.chat-input-send-label {
  display: none;
}

.studio-size-popover {
  position: absolute;
  z-index: 260;
  bottom: calc(100% + 0.5rem);
  left: 0;
  width: min(28rem, calc(100vw - 3rem));
  max-height: min(34rem, calc(100dvh - 8rem));
  overflow-y: auto;
  border: 1px solid hsl(var(--border));
  border-radius: 1rem;
  background: hsl(var(--card));
  padding: 0.9rem;
  box-shadow: var(--shadow-floating);
}

.studio-size-section + .studio-size-section {
  margin-top: 0.85rem;
}

.studio-size-label {
  margin-bottom: 0.45rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
  font-weight: 700;
}

.studio-choice-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.45rem;
}

.studio-choice-grid.is-ratio {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.studio-choice-button {
  min-width: 0;
}

.studio-size-current {
  margin-top: 0.5rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
}

.studio-drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  background: hsl(var(--card) / 0.92);
  color: hsl(var(--foreground));
  font-size: 0.875rem;
  font-weight: 700;
  backdrop-filter: blur(8px);
}

@media (max-width: 720px) {
  .chat-input-panel {
    padding: 0.35rem 0.625rem 0.5rem;
  }

  .chat-input-panel-shell {
    border-radius: 1.2rem;
    padding: 0.5rem;
  }

  .chat-input-actions {
    align-items: center;
    flex-direction: row;
    gap: 0.55rem;
  }

  .chat-input-action-row {
    width: auto;
    flex: 1 1 auto;
    flex-wrap: nowrap;
    overflow-x: auto;
    padding-bottom: 0.125rem;
  }

  .chat-input-submit-row {
    width: auto;
    justify-content: flex-end;
  }

  .chat-select-wrap {
    min-width: 8rem;
    max-width: 12rem;
  }

  .chat-summary-button,
  :deep(.chat-summary-button) {
    max-width: 11.5rem;
  }

  .studio-size-popover {
    position: fixed;
    right: 1rem;
    bottom: 5.75rem;
    left: 1rem;
    width: auto;
    max-height: min(30rem, calc(100dvh - 7rem));
  }

  .studio-choice-grid,
  .studio-choice-grid.is-ratio {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chat-input {
    height: 3rem;
    min-height: 3rem;
    max-height: 7.5rem;
    padding-right: 0.25rem;
    font-size: 1rem;
  }

  .chat-input-panel-inner {
    min-height: 3rem;
  }

  .chat-input-panel-inner-attach {
    min-height: 8.5rem;
  }

  .attach-images {
    width: 100%;
  }
}

@media (max-width: 420px) {
  .chat-input-actions {
    gap: 0.375rem;
  }

  .chat-input-action-row {
    gap: 0.25rem;
  }

  .chat-select-wrap {
    min-width: 4.75rem;
    max-width: 4.75rem;
  }

  .chat-summary-button,
  :deep(.chat-summary-button) {
    max-width: clamp(5.5rem, 25vw, 7rem);
  }

  :deep(.chat-prompt-button > span) {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  :deep(.chat-prompt-button) {
    width: 1.75rem;
    justify-content: center;
    padding-inline: 0;
  }
}

@media (max-width: 360px) {
  .chat-settings-anchor--chat {
    min-width: 0;
    flex: 1 1 auto;
  }

  :deep(.chat-settings-anchor--chat > div),
  :deep(.chat-settings-anchor--chat button) {
    width: 100%;
    min-width: 0;
    max-width: 100%;
  }
}
</style>
