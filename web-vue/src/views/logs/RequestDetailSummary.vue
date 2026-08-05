<template>
  <section class="request-detail-summary">
    <div class="min-w-0">
      <StateBadge :tone="statusTone" shape="rounded">
        {{ statusLabel }}
      </StateBadge>
      <p class="request-detail-summary__title">{{ title }}</p>
    </div>
    <div class="request-detail-summary__duration">
      <span>总耗时</span>
      <strong>{{ duration || '-' }}</strong>
      <small v-if="durationBreakdown">{{ durationBreakdown }}</small>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { PresentationTone } from '@/api/requestDetail'
import StateBadge from '@/components/ai/StateBadge.vue'

defineProps<{
  statusLabel: string
  statusTone: PresentationTone
  title: string
  duration: string
  durationBreakdown?: string
}>()
</script>

<style scoped>
.request-detail-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid hsl(var(--border));
  padding: 2px 0 16px;
}

.request-detail-summary__title {
  margin-top: 8px;
  overflow-wrap: anywhere;
  color: hsl(var(--foreground));
  font-size: 13px;
  font-weight: 600;
  line-height: 1.55;
}

.request-detail-summary__duration {
  display: flex;
  min-width: 5.5rem;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  text-align: right;
}

.request-detail-summary__duration span {
  color: hsl(var(--muted-foreground));
  font-size: 11px;
}

.request-detail-summary__duration strong {
  color: hsl(var(--foreground));
  font-size: 20px;
  font-weight: 650;
}

.request-detail-summary__duration small {
  max-width: 24rem;
  overflow-wrap: anywhere;
  color: hsl(var(--muted-foreground) / 0.78);
  font-size: 10px;
  line-height: 1.4;
}

@media (max-width: 640px) {
  .request-detail-summary {
    flex-direction: column;
  }

  .request-detail-summary__duration {
    align-items: flex-start;
    text-align: left;
  }
}
</style>
