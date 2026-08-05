<template>
  <div :class="['detail-field-card', `detail-field-card--${variant}`]">
    <div class="detail-field-card__header">
      <span class="detail-field-card__label">{{ label }}</span>
      <Button
        v-if="variant !== 'row' && copyable && value"
        size="xs"
        variant="ghost"
        @click="$emit('copy', value)"
      >
        复制
      </Button>
    </div>
    <p class="detail-field-card__value">{{ value || '-' }}</p>
  </div>
</template>

<script setup lang="ts">
import { Button } from 'nanocat-ui'

withDefaults(defineProps<{
  label: string
  value: string
  copyable?: boolean
  variant?: 'card' | 'row'
}>(), {
  variant: 'card',
})

defineEmits<{
  (e: 'copy', value: string): void
}>()
</script>

<style scoped>
.detail-field-card {
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
  padding: 8px 12px;
  font-size: 12px;
}

.detail-field-card--row {
  display: grid;
  grid-template-columns: minmax(4.8rem, 0.42fr) minmax(0, 1fr);
  align-items: start;
  gap: 8px;
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 4px 0;
}

.detail-field-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.detail-field-card--row .detail-field-card__header {
  justify-content: flex-start;
  min-width: 0;
}

.detail-field-card__label {
  color: hsl(var(--muted-foreground));
}

.detail-field-card__value {
  margin-top: 4px;
  overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  color: hsl(var(--foreground));
}

.detail-field-card--row .detail-field-card__value {
  margin-top: 0;
}

@media (max-width: 520px) {
  .detail-field-card--row {
    grid-template-columns: 1fr;
    gap: 3px;
  }
}
</style>
