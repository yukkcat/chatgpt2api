<template>
  <div class="timeline-summary">
    <MetaChip size="xs" tone="muted">
      {{ stepCount }} 步
    </MetaChip>
    <MetaChip size="xs" tone="muted">
      {{ durationMs > 0 ? formatRequestDuration(durationMs) : '-' }}
    </MetaChip>
    <StateBadge
      :tone="status.tone"
      size="xs"
      shape="rounded"
    >
      {{ status.label }}
    </StateBadge>
  </div>
</template>

<script setup lang="ts">
import MetaChip from '@/components/ai/MetaChip.vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import type { CallPresentationStatus } from '@/api/requestDetail'
import { formatRequestDuration } from '@/lib/requestDuration'

defineProps<{
  stepCount: number
  durationMs: number
  status: CallPresentationStatus
}>()
</script>

<style scoped>
.timeline-summary {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

@media (max-width: 640px) {
  .timeline-summary {
    justify-content: flex-start;
  }
}
</style>
