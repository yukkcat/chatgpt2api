<template>
  <HoverCard card-class="w-72" focusable>
    <span
      class="inline-flex items-center gap-1.5 whitespace-nowrap"
      :aria-label="`记忆状态：${item.memory_label}${item.memory_operation_label ? `，${item.memory_operation_label}` : ''}，清空记录：${item.memory_clear_label}`"
    >
      <StatusPill :label="item.memory_label" :tone="item.memory_tone" />
      <Icon
        v-if="item.memory_operation_label"
        :icon="item.memory_operation_tone === 'error' ? 'lucide:circle-alert' : 'lucide:clock-3'"
        class="h-3 w-3 shrink-0"
        :class="toneTextClasses[item.memory_operation_tone]"
        aria-hidden="true"
      />
    </span>

    <template #content>
      <div class="space-y-2 text-xs leading-5">
        <div class="ui-status-title">记忆状态</div>
        <dl class="space-y-1">
          <div class="flex items-start justify-between gap-4">
            <dt class="text-muted-foreground">最近确认</dt>
            <dd class="text-right font-medium text-foreground">{{ item.memory_label }}</dd>
          </div>
          <div class="flex items-start justify-between gap-4">
            <dt class="text-muted-foreground">确认时间</dt>
            <dd class="text-right tabular-nums text-foreground">{{ formatAccountDate(item.memory_checked_at) }}</dd>
          </div>
          <div v-if="item.memory_operation_label" class="flex items-start justify-between gap-4">
            <dt class="text-muted-foreground">最近操作</dt>
            <dd class="text-right text-foreground">{{ item.memory_operation_label }}</dd>
          </div>
          <div v-if="item.memory_operation_label && item.memory_operation_at" class="flex items-start justify-between gap-4">
            <dt class="text-muted-foreground">操作时间</dt>
            <dd class="text-right tabular-nums text-foreground">{{ formatAccountDate(item.memory_operation_at) }}</dd>
          </div>
          <div v-if="item.memory_operation_error" class="flex items-start justify-between gap-4">
            <dt class="shrink-0 text-muted-foreground">详情</dt>
            <dd class="break-words text-right text-foreground">{{ item.memory_operation_error }}</dd>
          </div>
        </dl>
        <dl class="space-y-1 border-t border-border/70 pt-2">
          <div class="flex items-start justify-between gap-4">
            <dt class="text-muted-foreground">清空记录</dt>
            <dd class="text-right font-medium" :class="toneTextClasses[item.memory_clear_tone]">{{ item.memory_clear_label }}</dd>
          </div>
          <div v-if="item.memory_clear_at" class="flex items-start justify-between gap-4">
            <dt class="text-muted-foreground">操作时间</dt>
            <dd class="text-right tabular-nums text-foreground">{{ formatAccountDate(item.memory_clear_at) }}</dd>
          </div>
          <div v-if="item.memory_cleared_at" class="flex items-start justify-between gap-4">
            <dt class="text-muted-foreground">最近成功</dt>
            <dd class="text-right tabular-nums text-foreground">{{ formatAccountDate(item.memory_cleared_at) }}</dd>
          </div>
          <div v-if="item.memory_clear_error" class="flex items-start justify-between gap-4">
            <dt class="shrink-0 text-muted-foreground">详情</dt>
            <dd class="break-words text-right text-foreground">{{ item.memory_clear_error }}</dd>
          </div>
        </dl>
        <p class="border-t border-border/70 pt-2 text-muted-foreground">关闭记忆不会删除已有记忆。清空记录仅表示历史操作，之后可能产生新记忆。</p>
      </div>
    </template>
  </HoverCard>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { HoverCard, StatusPill } from 'nanocat-ui'

import type { Account, AccountPresentationTone } from '@/api/accounts'
import { formatAccountDate } from './viewUtils'

defineProps<{ item: Account }>()

const toneTextClasses: Record<AccountPresentationTone, string> = {
  neutral: 'text-muted-foreground',
  success: 'text-emerald-600 dark:text-emerald-400',
  warning: 'text-amber-600 dark:text-amber-400',
  error: 'text-rose-600 dark:text-rose-400',
  info: 'text-sky-600 dark:text-sky-400',
}
</script>
