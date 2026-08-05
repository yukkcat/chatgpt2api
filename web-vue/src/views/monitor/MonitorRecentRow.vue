<template>
  <tr
    v-memo="[signature]"
    class="cursor-pointer"
    tabindex="0"
    @click="emit('open-detail', row)"
    @keydown.enter.prevent="emit('open-detail', row)"
    @keydown.space.prevent="emit('open-detail', row)"
  >
    <td>
      <p class="font-mono text-xs text-foreground">{{ shortCallId(row.call_id) }}</p>
      <p class="mt-1 text-[11px] text-muted-foreground">{{ row.ended_at || row.updated_at || '-' }}</p>
    </td>
    <td>
      <StateBadge :tone="row.presentation.status_tone" shape="rounded">
        {{ row.presentation.status_label }}
      </StateBadge>
    </td>
    <td class="max-w-[12rem] truncate">{{ row.model || '-' }}</td>
    <td>{{ row.presentation.duration_text }}</td>
    <td>{{ row.presentation.metric_digest }}</td>
    <td>{{ row.presentation.account_egress_text }}</td>
  </tr>
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
