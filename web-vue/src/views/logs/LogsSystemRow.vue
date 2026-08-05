<template>
  <tr
    v-memo="[signature]"
    class="border-t border-border"
    :class="{ 'bg-primary/5': selected }"
    :aria-selected="selected || undefined"
  >
    <td class="py-4 pl-4 pr-2 align-middle">
      <Checkbox
        :model-value="selected"
        @update:model-value="handleSelect"
      >
        <span class="sr-only">选择日志 {{ item.time || item.id }}</span>
      </Checkbox>
    </td>
    <td class="py-4 pr-5 align-middle text-xs">
      <p class="whitespace-nowrap text-foreground">{{ timeDisplay.primary }}</p>
      <p v-if="timeDisplay.secondary" class="mt-1 whitespace-nowrap text-muted-foreground">
        {{ timeDisplay.secondary }}
      </p>
    </td>
    <td class="py-4 pr-5 align-middle">
      <p
        class="flex min-w-0 items-baseline gap-1.5 truncate text-xs text-foreground"
        :title="[request.kind, request.primary].filter(Boolean).join(' ')"
      >
        <span v-if="request.kind" class="shrink-0 text-muted-foreground">{{ request.kind }}</span>
        <span class="truncate font-medium">{{ request.primary || '-' }}</span>
      </p>
      <p
        v-if="request.secondary"
        class="mt-1 truncate text-[11px] text-muted-foreground"
        :title="request.secondary"
      >
        {{ request.secondary }}
      </p>
    </td>
    <td class="py-4 pr-5 align-middle">
      <p class="truncate text-xs text-foreground" :title="execution.primary">
        {{ execution.primary || '-' }}
      </p>
      <div
        v-if="execution.secondary || item.accountSwitchCount"
        class="mt-1 flex min-w-0 items-center gap-1.5"
      >
        <span
          v-if="execution.secondary"
          class="truncate text-[11px] text-muted-foreground"
          :title="execution.secondary"
        >
          {{ execution.secondary }}
        </span>
        <MetaChip
          v-if="item.accountSwitchCount"
          size="xs"
          tone="warning"
          chip-class="shrink-0"
        >
          切换 {{ item.accountSwitchCount }} 次
        </MetaChip>
      </div>
    </td>
    <td class="py-4 pr-5 align-middle text-xs text-muted-foreground">
      <div :title="[durationDisplay.total, durationDisplay.breakdown].filter(Boolean).join(' ')">
        <MetaChip
          v-if="durationDisplay.total"
          size="xs"
          :tone="durationTone"
          chip-class="font-mono tabular-nums"
        >
          <Icon icon="lucide:clock-3" class="mr-1 h-3 w-3" />
          {{ durationDisplay.total }}
        </MetaChip>
        <span v-else>-</span>
        <p
          v-if="durationDisplay.breakdown"
          class="mt-0.5 max-w-[14rem] truncate whitespace-nowrap text-[10px] text-muted-foreground/75"
        >
          {{ durationDisplay.breakdown }}
        </p>
      </div>
    </td>
    <td class="py-4 pr-5 align-middle">
      <LogImagePreviewCell
        :image-urls="item.imageUrls"
        :first-image-broken="firstImageBroken"
        :alt="item.preview || '日志结果图片'"
        @preview-click="handleOpenDetail"
        @image-error="handleImageError"
      />
    </td>
    <td class="py-4 pr-5 align-middle">
      <div class="min-w-0">
        <div class="flex min-w-0 items-center gap-2">
          <StateBadge :tone="statusTone(item)" shape="rounded">
            {{ statusLabel(item) }}
          </StateBadge>
          <p
            class="min-w-0 truncate text-xs font-medium text-foreground"
            :class="{ 'text-rose-600': failed }"
            :title="outcome"
          >
            {{ outcome }}
          </p>
        </div>
        <p
          v-if="diagnostics"
          class="mt-1.5 truncate text-[11px] text-muted-foreground"
          :title="diagnostics"
        >
          {{ diagnostics }}
        </p>
      </div>
    </td>
    <td class="py-4 pr-4 text-right align-middle">
      <div class="flex justify-end gap-1.5">
        <Button
          size="xs"
          variant="outline"
          @click="handleOpenDetail"
        >
          查看详情
        </Button>
        <Button
          size="xs"
          variant="ghost"
          root-class="text-rose-600 hover:text-rose-700"
          @click="handleRequestDelete"
        >
          删除
        </Button>
      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { Button, Checkbox } from 'nanocat-ui'
import LogImagePreviewCell from '@/components/ai/LogImagePreviewCell.vue'
import MetaChip from '@/components/ai/MetaChip.vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import { type SystemLogRow } from '@/api/logs'
import {
  executionDisplay,
  logDurationDisplay,
  logDurationTone,
  outcomeText,
  requestDisplay,
  resultDiagnostics,
  statusLabel,
  statusTone,
} from '@/views/logs/logsView'

const props = defineProps<{
  item: SystemLogRow
  signature: string
  selected: boolean
  firstImageBroken: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-selection', id: string, checked: boolean): void
  (e: 'open-detail', item: SystemLogRow): void
  (e: 'request-delete-log', item: SystemLogRow): void
  (e: 'image-error', url: string): void
}>()

const request = computed(() => requestDisplay(props.item))
const execution = computed(() => executionDisplay(props.item))
const outcome = computed(() => outcomeText(props.item))
const failed = computed(() => props.item.presentation.is_failure)
const durationDisplay = computed(() => logDurationDisplay(props.item))
const durationTone = computed(() => logDurationTone(props.item))
const diagnostics = computed(() => resultDiagnostics(props.item))
const timeDisplay = computed(() => {
  const value = props.item.time.trim()
  const match = value.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})/)
  if (!match) return { primary: value || '-', secondary: '' }
  return { primary: match[2], secondary: match[1] }
})

function handleSelect(checked: boolean | string | number) {
  emit('toggle-selection', props.item.id, Boolean(checked))
}

function handleOpenDetail() {
  emit('open-detail', props.item)
}

function handleRequestDelete() {
  emit('request-delete-log', props.item)
}

function handleImageError(url: string) {
  emit('image-error', url)
}
</script>
