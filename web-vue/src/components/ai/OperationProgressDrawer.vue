<template>
  <DrawerShell
    :open="open && !minimized"
    :title="title"
    max-width="clamp(22rem, 30vw, 32rem)"
    :z-index="zIndex"
    bare
    :show-backdrop="false"
    :show-close="false"
    :close-on-overlay="false"
    :close-on-escape="false"
    @close="emit('close')"
  >
    <div class="operation-progress-layout" role="region" :aria-label="title">
      <header class="operation-progress-header">
        <div class="min-w-0">
          <div class="flex min-w-0 items-center gap-2">
            <p class="truncate text-sm font-semibold text-foreground">{{ title }}</p>
            <StateBadge :tone="resolvedTone" size="xs" shape="rounded">
              {{ statusLabel }}
            </StateBadge>
          </div>
          <p v-if="subtitle" class="mt-1 truncate text-xs text-muted-foreground">
            {{ subtitle }}
          </p>
        </div>

        <div class="flex shrink-0 items-center gap-2">
          <Button
            v-if="canCancel"
            size="xs"
            variant="outline"
            root-class="min-w-14 justify-center text-amber-600 dark:text-amber-400"
            :disabled="cancelDisabled"
            @click="emit('cancel')"
          >
            {{ cancelLabel }}
          </Button>
          <CloseButton
            icon="lucide:minus"
            label="收起任务面板"
            @click="minimized = true"
          />
          <CloseButton
            :disabled="resolvedCloseDisabled"
            :label="resolvedCloseDisabled ? '任务运行中，暂时无法关闭' : '关闭任务记录'"
            @click="emit('close')"
          />
        </div>
      </header>

      <section class="operation-progress-summary" aria-label="任务进度">
        <ProgressBar :value="progressValue" :aria-label="`${title}进度`" />
        <div v-if="resolvedSummaryItems.length" class="operation-progress-metrics">
          <div
            v-for="item in resolvedSummaryItems"
            :key="item.key"
            class="operation-progress-metric"
          >
            <span>{{ item.label }}</span>
            <strong :class="summaryValueClass(item.tone)">{{ item.value }}</strong>
          </div>
        </div>
      </section>

      <section class="operation-progress-events" aria-label="任务记录">
        <div class="operation-progress-events__header">
          <p class="text-xs font-semibold text-foreground">任务记录</p>
          <span class="text-[11px] text-muted-foreground">{{ events.length }} 条</span>
        </div>

        <ol
          ref="eventListRef"
          class="scrollbar-slim operation-progress-events__list"
          aria-live="polite"
          @scroll.passive="handleEventListScroll"
        >
          <li v-if="events.length === 0" class="operation-progress-events__empty">
            {{ busy ? '等待任务记录...' : '暂无任务记录' }}
          </li>
          <template v-else>
            <li
              v-for="event in events"
              :key="event.key"
              class="operation-progress-event"
            >
              <span
                class="operation-progress-event__marker"
                :class="`operation-progress-event__marker--${event.tone}`"
              >
                <Icon :icon="eventIcon(event.tone)" class="h-3.5 w-3.5" />
              </span>
              <div class="min-w-0 flex-1">
                <div class="flex min-w-0 items-baseline justify-between gap-3">
                  <p class="truncate text-xs font-medium text-foreground">{{ event.label }}</p>
                  <time
                    class="shrink-0 text-[10px] tabular-nums text-muted-foreground"
                    :datetime="event.timestamp"
                  >
                    {{ formatEventTime(event.timestamp) }}
                  </time>
                </div>
                <p
                  class="mt-0.5 break-words text-xs leading-5"
                  :class="eventMessageClass(event.tone)"
                >
                  {{ event.message }}
                </p>
              </div>
            </li>
          </template>
        </ol>
      </section>
    </div>
  </DrawerShell>

  <SideDock
    :open="open && minimized"
    aria-label="展开任务面板"
    :aria-describedby="dockStatusId"
    :z-index="zIndex"
    @click="minimized = false"
  >
    <span class="operation-progress-dock__heading">
      <span class="operation-progress-dock__title">{{ title }}</span>
      <strong>{{ progressValue }}%</strong>
    </span>
    <span :id="dockStatusId" class="operation-progress-dock__status">
      {{ statusLabel }}<template v-if="subtitle"> · {{ subtitle }}</template>
    </span>
    <span class="operation-progress-dock__track" aria-hidden="true">
      <span :style="{ width: `${progressValue}%` }" />
    </span>
  </SideDock>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import { Icon } from '@iconify/vue'
import { Button, CloseButton, DrawerShell, OVERLAY_LAYER, SideDock } from 'nanocat-ui'
import type {
  OperationProgressTone,
  OperationSummaryItem,
  OperationTimelineEvent,
} from '@/composables/useOperationProgressRuntime'
import ProgressBar from './ProgressBar.vue'
import StateBadge from './StateBadge.vue'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  subtitle?: string
  total?: number
  current?: number
  percent?: number
  statusLabel?: string
  error?: string
  busy?: boolean
  canCancel?: boolean
  cancelDisabled?: boolean
  cancelLabel?: string
  closeDisabled?: boolean
  zIndex?: number
  tone?: OperationProgressTone
  events?: OperationTimelineEvent[]
  summaryItems?: OperationSummaryItem[]
}>(), {
  subtitle: '',
  total: 0,
  current: 0,
  percent: undefined,
  statusLabel: '已处理',
  error: '',
  busy: false,
  canCancel: false,
  cancelDisabled: false,
  cancelLabel: '停止',
  closeDisabled: undefined,
  zIndex: () => OVERLAY_LAYER.confirm - 1,
  tone: 'success',
  events: () => [],
  summaryItems: () => [],
})

const emit = defineEmits<{
  close: []
  cancel: []
}>()

const eventListRef = ref<HTMLElement | null>(null)
const minimized = ref(false)
const dockStatusId = `operation-progress-dock-${useId()}`
let stickToLatest = true

const progressValue = computed(() => {
  if (Number.isFinite(props.percent)) {
    return Math.min(100, Math.max(0, Math.round(Number(props.percent))))
  }
  if (!props.total) return props.busy ? 0 : 100
  return Math.min(100, Math.max(0, Math.round((props.current / props.total) * 100)))
})

const resolvedTone = computed<OperationProgressTone>(() => (props.error ? 'danger' : props.tone))
const resolvedCloseDisabled = computed(() => props.closeDisabled ?? props.busy)
const resolvedSummaryItems = computed<OperationSummaryItem[]>(() => {
  if (props.summaryItems.length) return props.summaryItems
  return [
    { key: 'processed', label: '已处理', value: props.current },
    { key: 'remaining', label: '待处理', value: Math.max(0, props.total - props.current) },
    { key: 'total', label: '总数', value: props.total },
  ]
})

function summaryValueClass(tone: OperationSummaryItem['tone']) {
  if (tone === 'danger') return 'text-red-600 dark:text-red-400'
  if (tone === 'warning') return 'text-amber-600 dark:text-amber-400'
  if (tone === 'success') return 'text-emerald-600 dark:text-emerald-400'
  return ''
}

function eventIcon(tone: OperationProgressTone) {
  if (tone === 'success') return 'lucide:circle-check'
  if (tone === 'danger') return 'lucide:circle-x'
  if (tone === 'warning') return 'lucide:circle-minus'
  return 'lucide:clock-3'
}

function eventMessageClass(tone: OperationProgressTone) {
  if (tone === 'danger') return 'text-red-600 dark:text-red-400'
  if (tone === 'warning') return 'text-amber-600 dark:text-amber-400'
  return 'text-muted-foreground'
}

function formatEventTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--:--:--'
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

function handleEventListScroll() {
  const element = eventListRef.value
  if (!element) return
  stickToLatest = element.scrollHeight - element.scrollTop - element.clientHeight < 48
}

watch(
  () => [props.events.length, props.events.at(-1)?.key, props.busy, props.error].join('|'),
  async () => {
    if (!stickToLatest) return
    await nextTick()
    const element = eventListRef.value
    if (element) element.scrollTop = element.scrollHeight
  },
)

watch(
  () => props.open,
  async (open) => {
    if (!open) {
      minimized.value = false
      return
    }
    stickToLatest = true
    await nextTick()
    const element = eventListRef.value
    if (element) element.scrollTop = element.scrollHeight
  },
)

watch(minimized, async (value) => {
  if (value || !props.open) return
  stickToLatest = true
  await nextTick()
  const element = eventListRef.value
  if (element) element.scrollTop = element.scrollHeight
})
</script>

<style scoped>
.operation-progress-layout {
  --operation-progress-content-radius: calc(var(--radius, 16px) - 2px);

  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
}

.operation-progress-header {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid hsl(var(--border));
  padding: 14px 16px;
}

.operation-progress-summary {
  max-height: min(42%, 13rem);
  flex: 0 1 auto;
  overflow-y: auto;
  border-bottom: 1px solid hsl(var(--border));
  padding: 14px 16px;
}

.operation-progress-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(4.5rem, 1fr));
  margin-top: 14px;
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 0.72);
  border-radius: var(--operation-progress-content-radius);
  background: hsl(var(--muted) / 0.14);
}

.operation-progress-metric {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
  padding: 9px 10px;
}

.operation-progress-metric + .operation-progress-metric {
  border-left: 1px solid hsl(var(--border) / 0.72);
}

.operation-progress-metric span {
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.operation-progress-metric strong {
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 650;
  line-height: 1.2;
}

.operation-progress-events {
  display: flex;
  min-height: 7rem;
  flex: 1 1 8rem;
  flex-direction: column;
}

.operation-progress-events__header {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 16px 8px;
}

.operation-progress-events__list {
  min-height: 0;
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 2px 16px 16px;
}

.operation-progress-events__empty {
  padding: 28px 0;
  text-align: center;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

.operation-progress-event {
  position: relative;
  display: flex;
  gap: 10px;
  padding: 8px 0;
}

.operation-progress-event:not(:last-child)::after {
  position: absolute;
  top: 27px;
  bottom: -7px;
  left: 8px;
  width: 1px;
  background: hsl(var(--border));
  content: '';
}

.operation-progress-event__marker {
  position: relative;
  z-index: 1;
  display: inline-flex;
  width: 17px;
  height: 17px;
  flex: 0 0 17px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: hsl(var(--card));
  color: hsl(var(--muted-foreground));
}

.operation-progress-event__marker--success {
  color: rgb(22 163 74);
}

.operation-progress-event__marker--danger {
  color: rgb(220 38 38);
}

.operation-progress-event__marker--warning {
  color: rgb(217 119 6);
}

.operation-progress-dock__heading {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.operation-progress-dock__title {
  overflow: hidden;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.operation-progress-dock__heading strong {
  flex: 0 0 auto;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.operation-progress-dock__status {
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.operation-progress-dock__track {
  height: 3px;
  overflow: hidden;
  border-radius: 999px;
  background: hsl(var(--muted));
}

.operation-progress-dock__track > span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: hsl(var(--primary));
  transition: width 180ms ease;
}

@media (max-width: 640px) {
  .operation-progress-header,
  .operation-progress-summary,
  .operation-progress-events__header,
  .operation-progress-events__list {
    padding-inline: 14px;
  }

}
</style>
