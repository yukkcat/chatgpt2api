<template>
  <button
    type="button"
    v-memo="[signature]"
    class="w-full rounded-2xl border border-border bg-background px-3 py-3 text-left transition-colors hover:border-primary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
    @click="emit('open-detail', row)"
  >
    <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
      <div class="min-w-0">
        <p class="truncate text-sm font-medium text-foreground">
          {{ row.model || '-' }}
          <span class="font-mono text-xs text-muted-foreground">{{ shortCallId(row.call_id) }}</span>
        </p>
        <p class="mt-1 text-xs text-muted-foreground">{{ row.endpoint || '-' }}</p>
      </div>
      <StateBadge class="self-start sm:self-auto" :tone="row.presentation.status_tone" size="xs" shape="rounded">
        {{ row.presentation.duration_text }}
      </StateBadge>
    </div>
    <div class="mt-3 grid auto-rows-fr grid-cols-2 gap-2 text-xs">
      <span
        v-for="item in row.presentation.slow_metrics"
        :key="`${row.call_id}-${item.key}`"
        class="flex min-h-9 min-w-0 items-center break-words rounded-xl px-2 py-1 leading-5"
        :class="item.important ? 'bg-primary/10 text-primary' : 'bg-muted/60'"
      >
        {{ item.label }} {{ item.value_text }}
      </span>
    </div>
    <p v-if="row.presentation.slow_reason" class="mt-2 break-words text-xs leading-5 text-muted-foreground">
      {{ row.presentation.slow_reason }}
    </p>
    <p v-if="row.presentation.error_text" class="mt-2 line-clamp-2 break-words text-xs leading-5 text-muted-foreground">
      {{ row.presentation.error_text }}
    </p>
  </button>
</template>

<script setup lang="ts">
import type { RealtimeMonitorRecord } from '@/api/monitor'
import StateBadge from '@/components/ai/StateBadge.vue'
import { shortCallId } from '@/views/monitor/monitorView'

defineProps<{
  row: RealtimeMonitorRecord
  signature: string
}>()

const emit = defineEmits<{
  (e: 'open-detail', row: RealtimeMonitorRecord): void
}>()
</script>
