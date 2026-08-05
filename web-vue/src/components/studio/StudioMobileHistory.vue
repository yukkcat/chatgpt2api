<template>
  <Teleport to="body">
    <div v-if="open" class="studio-mobile-history-backdrop" @click.self="$emit('close')">
      <div class="studio-mobile-history">
        <div class="studio-mobile-history-header">
          <p>历史记录</p>
          <CloseButton label="关闭历史记录" @click="$emit('close')" />
        </div>
        <div ref="historyListRef" class="studio-mobile-history-list custom-scrollbar" @scroll="handleWindowScroll">
          <div
            v-if="topSpacerHeight > 0"
            class="studio-mobile-history-window-spacer"
            :style="{ height: `${topSpacerHeight}px` }"
            aria-hidden="true"
          ></div>
          <div v-for="{ item: conversation } in visibleConversationEntries" :key="conversation.id" class="studio-mobile-history-window-row">
            <div
              class="studio-mobile-history-item"
              :class="{ 'is-active': conversation.id === activeConversationId }"
            >
              <button
                type="button"
                class="studio-mobile-history-main"
                @click="$emit('select', conversation.id); $emit('close')"
              >
                <span class="studio-mobile-history-title">{{ conversation.title || '未命名对话' }}</span>
                <span class="studio-mobile-history-meta">
                  {{ conversation.messages.length }} 条 · {{ formatTime(conversation.updatedAt) }}
                </span>
                <span
                  v-if="badges[conversation.id]"
                  class="studio-mobile-history-badge"
                  :class="`is-${badges[conversation.id].state}`"
                >
                  {{ badges[conversation.id].label }}
                </span>
              </button>
              <button
                type="button"
                class="studio-mobile-history-delete"
                title="删除对话"
                aria-label="删除对话"
                @click.stop="$emit('delete', conversation.id)"
              >
                <Icon icon="lucide:trash-2" class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          <div
            v-if="bottomSpacerHeight > 0"
            class="studio-mobile-history-window-spacer"
            :style="{ height: `${bottomSpacerHeight}px` }"
            aria-hidden="true"
          ></div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { CloseButton } from 'nanocat-ui'
import { useWindowedList } from '@/composables/useWindowedList'
import type { StudioConversation, StudioConversationBadge } from './types'

const props = defineProps<{
  open: boolean
  conversations: StudioConversation[]
  activeConversationId: string
  badges: Record<string, StudioConversationBadge>
}>()

defineEmits<{
  close: []
  select: [id: string]
  delete: [id: string]
}>()

const historyTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})
const historyListRef = ref<HTMLElement | null>(null)
const shouldWindowHistory = computed(() => props.open && props.conversations.length > 36)
const {
  visibleItems: visibleConversationEntries,
  topSpacerHeight,
  bottomSpacerHeight,
  handleScroll: handleWindowScroll,
  setScrollElement: setHistoryScrollElement,
  refreshWindow: refreshHistoryWindow,
} = useWindowedList({
  items: computed(() => props.conversations),
  itemHeight: 72,
  overscan: 8,
  disabled: computed(() => !shouldWindowHistory.value),
})

watch(historyListRef, (element) => setHistoryScrollElement(element), { flush: 'post' })
watch(() => props.open, () => {
  void nextTick(refreshHistoryWindow)
})

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return historyTimeFormatter.format(date)
}
</script>

<style scoped>
.studio-mobile-history-backdrop {
  position: fixed;
  inset: 0;
  z-index: 260;
  background: rgb(15 23 42 / 0.36);
  padding: 0.75rem;
}

.studio-mobile-history {
  display: flex;
  width: min(24rem, 92vw);
  max-height: calc(100dvh - 1.5rem);
  flex-direction: column;
  gap: 0.75rem;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 1rem;
  background: hsl(var(--card));
  padding: 0.75rem;
  box-shadow: var(--shadow-floating);
}

.studio-mobile-history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.25rem 0.25rem 0;
  color: hsl(var(--foreground));
  font-weight: 650;
}

.studio-mobile-history-delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  color: hsl(var(--muted-foreground));
}

.studio-mobile-history-list {
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow-y: auto;
}

.studio-mobile-history-window-spacer {
  flex: 0 0 auto;
  min-height: 0;
  pointer-events: none;
}

.studio-mobile-history-window-row {
  display: flex;
  min-height: 0;
  height: 4.5rem;
  flex: 0 0 4.5rem;
  padding-bottom: 0.375rem;
}

.studio-mobile-history-item {
  position: relative;
  width: 100%;
  border: 1px solid transparent;
  border-radius: 0.875rem;
  padding: 0.7rem 0.75rem;
}

.studio-mobile-history-item.is-active {
  border-color: hsl(var(--primary) / 0.28);
  background: hsl(var(--primary) / 0.08);
}

.studio-mobile-history-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.25rem;
  padding-right: 1.85rem;
  text-align: left;
}

.studio-mobile-history-delete {
  position: absolute;
  top: 0.5rem;
  right: 0.45rem;
  width: 1.75rem;
  height: 1.75rem;
}

.studio-mobile-history-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.875rem;
  font-weight: 650;
}

.studio-mobile-history-meta {
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.studio-mobile-history-badge {
  width: fit-content;
  border-radius: 999px;
  padding: 0.125rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 650;
}

.studio-mobile-history-badge.is-running {
  background: #eff6ff;
  color: #1d4ed8;
}

.studio-mobile-history-badge.is-done {
  background: #ecfdf5;
  color: #047857;
}

.studio-mobile-history-badge.is-error {
  background: #fef2f2;
  color: #dc2626;
}
</style>
