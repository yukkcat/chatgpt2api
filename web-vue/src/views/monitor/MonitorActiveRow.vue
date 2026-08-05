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
      <p class="mt-1 text-[11px] text-muted-foreground">{{ row.endpoint || '-' }}</p>
    </td>
    <td>
      <MetaChip size="xs" tone="muted">{{ row.model || '-' }}</MetaChip>
    </td>
    <td>
      <StateBadge tone="info" shape="rounded">
        {{ row.presentation.stage_text }}
      </StateBadge>
    </td>
    <td>{{ row.presentation.duration_text }}</td>
    <td>{{ row.presentation.metric_digest }}</td>
    <td>
      <MetaChip size="xs" tone="muted">{{ row.presentation.egress_text }}</MetaChip>
    </td>
    <td class="max-w-[14rem]">
      <p
        class="truncate"
        :title="row.previous_account_email ? `上一账号：${row.previous_account_email}` : row.account_email"
      >
        {{ row.account_email || '-' }}
      </p>
      <p v-if="row.presentation.account_attempt_text" class="mt-1 text-[11px] text-muted-foreground">
        {{ row.presentation.account_attempt_text }}
      </p>
    </td>
  </tr>
</template>

<script setup lang="ts">
import type { RealtimeMonitorRecord } from '@/api/monitor'
import MetaChip from '@/components/ai/MetaChip.vue'
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
