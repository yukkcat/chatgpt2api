<template>
  <aside class="studio-history-panel">
    <div class="studio-history-header">
      <div class="studio-history-title-row">
        <span class="studio-history-heading">对话</span>
        <div class="studio-history-actions">
          <Button size="sm" variant="outline" icon-only root-class="rounded-xl" title="新对话" @click="$emit('create')">
            <Icon icon="lucide:plus" class="h-4 w-4" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon-only
            root-class="rounded-xl"
            :disabled="!conversations.length"
            title="清空历史记录"
            @click="$emit('clear')"
          >
            <Icon icon="lucide:trash-2" class="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>

    <label class="studio-history-search ui-input">
      <Icon icon="lucide:search" class="h-3.5 w-3.5 shrink-0" />
      <input v-model="query" placeholder="搜索对话" />
    </label>

    <div ref="historyListRef" class="studio-history-list custom-scrollbar" @scroll="handleWindowScroll">
      <div
        v-if="topSpacerHeight > 0"
        class="studio-history-window-spacer"
        :style="{ height: `${topSpacerHeight}px` }"
        aria-hidden="true"
      ></div>
      <div
        v-for="{ item: conversation } in visibleConversationEntries"
        :key="conversation.id"
        class="studio-history-window-row"
        :class="{ 'has-badge': badges[conversation.id] }"
      >
        <div
          v-memo="historyItemMemo(conversation)"
          class="studio-history-item"
          :class="{
            'is-active': conversation.id === activeConversationId,
            'is-draggable': canDrag,
            'is-dragging': draggedId === conversation.id,
            'is-drop-target': dropTargetId === conversation.id,
          }"
          :draggable="canDrag"
          @dragstart="handleDragStart($event, conversation.id)"
          @dragover="handleDragOver($event, conversation.id)"
          @dragleave="handleDragLeave(conversation.id)"
          @drop="handleDrop($event, conversation.id)"
          @dragend="handleDragEnd"
        >
          <form
            v-if="editingId === conversation.id"
            class="studio-history-edit"
            @submit.prevent="commitRename(conversation.id)"
            @click.stop
          >
            <input
              :ref="setEditInputRef"
              v-model="editingTitle"
              maxlength="80"
              aria-label="对话标题"
              @keydown.esc.prevent="cancelRename"
              @blur="commitRename(conversation.id)"
            />
          </form>
          <button
            v-else
            type="button"
            class="studio-history-main"
            :aria-current="conversation.id === activeConversationId ? 'true' : undefined"
            @click="handleSelect(conversation.id)"
            @dblclick.stop="beginRename(conversation)"
          >
            <span class="studio-history-title">{{ conversation.title || '未命名对话' }}</span>
            <span class="studio-history-meta">
              <span>{{ conversation.messages.length ? `${conversation.messages.length} 条` : '空对话' }}</span>
              <span aria-hidden="true">·</span>
              <span>{{ formatConversationTime(conversation) }}</span>
            </span>
            <span
              v-if="badges[conversation.id]"
              class="studio-history-badge"
              :class="`is-${badges[conversation.id].state}`"
            >
              {{ badges[conversation.id].label }}
            </span>
          </button>
          <div v-if="editingId !== conversation.id" class="studio-history-row-actions">
            <button
              type="button"
              class="studio-history-icon"
              title="重命名"
              aria-label="重命名对话"
              @click.stop="beginRename(conversation)"
            >
              <Icon icon="lucide:pencil" class="h-3 w-3" />
            </button>
            <button
              type="button"
              class="studio-history-icon is-danger"
              title="删除对话"
              aria-label="删除对话"
              @click.stop="$emit('delete', conversation.id)"
            >
              <Icon icon="lucide:trash-2" class="h-3 w-3" />
            </button>
          </div>
        </div>
      </div>

      <div
        v-if="bottomSpacerHeight > 0"
        class="studio-history-window-spacer"
        :style="{ height: `${bottomSpacerHeight}px` }"
        aria-hidden="true"
      ></div>

      <div v-if="!filteredConversations.length" class="studio-history-empty">
        {{ query.trim() ? '没有匹配的对话' : '输入提示词后会在这里显示对话历史。' }}
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { Button } from 'nanocat-ui'
import { computed, nextTick, ref, watch } from 'vue'
import { useWindowedList } from '@/composables/useWindowedList'
import type { StudioConversation, StudioConversationBadge } from './types'

const props = defineProps<{
  conversations: StudioConversation[]
  activeConversationId: string
  badges: Record<string, StudioConversationBadge>
}>()

const emit = defineEmits<{
  create: []
  select: [id: string]
  rename: [id: string, title: string]
  delete: [id: string]
  clear: []
  reorder: [sourceId: string, targetId: string]
}>()

const editingId = ref('')
const editingTitle = ref('')
const editInputRef = ref<HTMLInputElement | null>(null)
const historyListRef = ref<HTMLElement | null>(null)
const query = ref('')
const draggedId = ref('')
const dropTargetId = ref('')
const searchIndexCache = new Map<string, { signature: string; text: string }>()
const historyTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})
const emptyHistoryTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})
let suppressSelect = false

const canDrag = computed(() => !query.value.trim() && !editingId.value && props.conversations.length > 1)

function setEditInputRef(element: Element | null) {
  editInputRef.value = element instanceof HTMLInputElement ? element : null
}

const filteredConversations = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return props.conversations
  return props.conversations.filter((conversation) => {
    return conversationSearchText(conversation).includes(keyword)
  })
})
const shouldWindowHistory = computed(() => {
  return !query.value.trim()
    && !editingId.value
    && !draggedId.value
    && filteredConversations.value.length > 36
})
const {
  visibleItems: visibleConversationEntries,
  topSpacerHeight,
  bottomSpacerHeight,
  handleScroll: handleWindowScroll,
  setScrollElement: setHistoryScrollElement,
  refreshWindow: refreshHistoryWindow,
} = useWindowedList({
  items: filteredConversations,
  itemHeight: 58,
  getItemHeight: (conversation) => props.badges[conversation.id] ? 76 : 58,
  overscan: 8,
  disabled: computed(() => !shouldWindowHistory.value),
})

watch(historyListRef, (element) => setHistoryScrollElement(element), { flush: 'post' })
watch(shouldWindowHistory, () => {
  void nextTick(refreshHistoryWindow)
})

function historyItemMemo(conversation: StudioConversation) {
  const badge = props.badges[conversation.id]
  return [
    conversation.id === props.activeConversationId,
    conversation.title,
    conversation.messages.length,
    conversation.updatedAt,
    badge?.state,
    badge?.label,
    editingId.value === conversation.id,
    draggedId.value === conversation.id,
    dropTargetId.value === conversation.id,
    canDrag.value,
  ]
}

function conversationSearchText(conversation: StudioConversation) {
  const lastMessage = conversation.messages[conversation.messages.length - 1]
  const signature = [
    conversation.title,
    conversation.updatedAt,
    conversation.messages.length,
    lastMessage?.id || '',
    lastMessage?.content || '',
  ].join('\u0000')
  const cached = searchIndexCache.get(conversation.id)
  if (cached?.signature === signature) return cached.text
  const text = `${conversation.title || ''}\n${conversation.messages.map((message) => message.content).join('\n')}`.toLowerCase()
  searchIndexCache.set(conversation.id, { signature, text })
  if (searchIndexCache.size > 120) {
    const validIds = new Set(props.conversations.map((item) => item.id))
    Array.from(searchIndexCache.keys()).forEach((id) => {
      if (!validIds.has(id)) searchIndexCache.delete(id)
    })
  }
  return text
}

function beginRename(conversation: StudioConversation) {
  editingId.value = conversation.id
  editingTitle.value = conversation.title || '未命名对话'
  void nextTick(() => {
    editInputRef.value?.focus()
    editInputRef.value?.select()
  })
}

function commitRename(id: string) {
  if (editingId.value !== id) return
  const title = editingTitle.value.trim()
  editingId.value = ''
  editingTitle.value = ''
  emit('rename', id, title)
}

function cancelRename() {
  editingId.value = ''
  editingTitle.value = ''
}

function handleSelect(id: string) {
  if (suppressSelect) {
    suppressSelect = false
    return
  }
  emit('select', id)
}

function handleDragStart(event: DragEvent, id: string) {
  if (!canDrag.value) {
    event.preventDefault()
    return
  }
  draggedId.value = id
  dropTargetId.value = ''
  suppressSelect = true
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', id)
  }
}

function handleDragOver(event: DragEvent, id: string) {
  if (!draggedId.value || draggedId.value === id) return
  event.preventDefault()
  dropTargetId.value = id
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function handleDragLeave(id: string) {
  if (dropTargetId.value === id) dropTargetId.value = ''
}

function handleDrop(event: DragEvent, id: string) {
  const sourceId = event.dataTransfer?.getData('text/plain') || draggedId.value
  handleDragEnd()
  if (!sourceId || sourceId === id) return
  emit('reorder', sourceId, id)
}

function handleDragEnd() {
  draggedId.value = ''
  dropTargetId.value = ''
  window.setTimeout(() => {
    suppressSelect = false
  }, 0)
}

function formatConversationTime(conversation: StudioConversation) {
  const date = new Date(conversation.updatedAt)
  if (Number.isNaN(date.getTime())) return ''
  return (conversation.messages.length ? historyTimeFormatter : emptyHistoryTimeFormatter).format(date)
}
</script>

<style scoped>
.studio-history-panel {
  position: relative;
  display: none;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  gap: 0.625rem;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 1.25rem;
  background: hsl(var(--card) / 0.88);
  padding: 0.75rem;
  box-shadow: 0 16px 44px -36px rgba(15, 23, 42, 0.45);
}

@media (min-width: 1024px) {
  .studio-history-panel {
    display: flex;
  }
}

.studio-history-header {
  flex: 0 0 auto;
}

.studio-history-title-row {
  display: flex;
  min-height: 2.25rem;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.studio-history-heading {
  min-width: 0;
  color: hsl(var(--foreground));
  font-size: 0.9375rem;
  font-weight: 750;
}

.studio-history-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 0.375rem;
}

.studio-history-search {
  display: flex;
  height: 2.25rem;
  flex: 0 0 auto;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid hsl(var(--border));
  border-radius: 0.75rem;
  background: hsl(var(--background));
  padding: 0 0.75rem;
  color: hsl(var(--muted-foreground));
}

.studio-history-search input {
  min-width: 0;
  flex: 1 1 auto;
  border: 0;
  background: transparent;
  color: hsl(var(--foreground));
  font-size: 0.8125rem;
  outline: none;
}

.studio-history-search input::placeholder {
  color: hsl(var(--muted-foreground) / 0.62);
  font-family: inherit;
  font-weight: 400;
  letter-spacing: 0;
  opacity: 1;
}

.studio-history-list {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  overflow-y: auto;
}

.studio-history-window-spacer {
  flex: 0 0 auto;
  min-height: 0;
  pointer-events: none;
}

.studio-history-window-row {
  display: flex;
  min-height: 0;
  height: 3.625rem;
  flex: 0 0 3.625rem;
  padding-bottom: 0.25rem;
}

.studio-history-window-row.has-badge {
  height: 4.75rem;
  flex-basis: 4.75rem;
}

.studio-history-item {
  position: relative;
  display: flex;
  width: 100%;
  min-height: 3.125rem;
  cursor: pointer;
  align-items: center;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 0.75rem;
  padding: 0.5rem 0.625rem;
  color: hsl(var(--foreground));
  transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
}

.studio-history-window-row.has-badge .studio-history-item {
  min-height: 4.25rem;
}

.studio-history-item.is-draggable {
  cursor: grab;
}

.studio-history-item.is-dragging {
  opacity: 0.48;
}

.studio-history-item.is-drop-target {
  border-color: hsl(var(--foreground) / 0.28);
  background: hsl(var(--secondary));
  box-shadow: inset 3px 0 0 hsl(var(--foreground) / 0.48);
}

.studio-history-item:hover {
  border-color: hsl(var(--border));
  background: hsl(var(--secondary) / 0.55);
}

.studio-history-item.is-active {
  border-color: hsl(var(--foreground) / 0.22);
  background: hsl(var(--secondary));
  box-shadow: inset 0 0 0 1px hsl(var(--foreground) / 0.06);
}

.studio-history-main {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  min-height: 0;
  flex-direction: column;
  justify-content: center;
  gap: 0.1875rem;
  padding-right: 3.25rem;
  text-align: left;
}

.studio-history-edit {
  width: 100%;
  padding-right: 0.125rem;
}

.studio-history-edit input {
  width: 100%;
  min-height: 2rem;
  border: 1px solid hsl(var(--foreground) / 0.24);
  border-radius: 0.625rem;
  background: hsl(var(--background));
  padding: 0 0.625rem;
  color: hsl(var(--foreground));
  font-size: 0.8125rem;
  font-weight: 650;
  outline: none;
  box-shadow: 0 0 0 3px hsl(var(--foreground) / 0.06);
}

.studio-history-title {
  display: block;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.8125rem;
  font-weight: 650;
  line-height: 1.25rem;
}

.studio-history-meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.375rem;
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-size: 0.6875rem;
  line-height: 1rem;
}

.studio-history-meta span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.studio-history-row-actions {
  position: absolute;
  top: 50%;
  right: 0.5rem;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.0625rem;
  transform: translateY(-50%);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s;
}

.studio-history-item:hover .studio-history-row-actions,
.studio-history-row-actions:focus-within {
  opacity: 1;
  pointer-events: auto;
}

.studio-history-icon {
  display: inline-flex;
  width: 1.5rem;
  height: 1.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.45rem;
  color: hsl(var(--muted-foreground));
  transition: background 0.15s, color 0.15s;
}

.studio-history-icon:hover {
  background: hsl(var(--background));
  color: hsl(var(--foreground));
}

.studio-history-icon.is-danger:hover {
  background: rgb(254 242 242);
  color: rgb(225 29 72);
}

.studio-history-badge {
  width: fit-content;
  max-width: 100%;
  border-radius: 999px;
  padding: 0.125rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 650;
  line-height: 1rem;
  white-space: nowrap;
}

.studio-history-badge.is-running {
  background: #eff6ff;
  color: #1d4ed8;
}

.studio-history-badge.is-done {
  background: #ecfdf5;
  color: #047857;
}

.studio-history-badge.is-error {
  background: #fef2f2;
  color: #dc2626;
}

.studio-history-empty {
  padding: 0.875rem;
  color: hsl(var(--muted-foreground));
  text-align: center;
  font-size: 0.75rem;
  line-height: 1.6;
}
</style>
