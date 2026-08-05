<template>
  <div class="request-detail-fields">
    <section v-if="primaryFields.length" class="request-detail-fields__section">
      <div class="request-detail-fields__header">请求身份</div>
      <div class="request-detail-fields__grid">
        <DetailFieldCard
          v-for="field in primaryFields"
          :key="field.label"
          :class="{ 'request-detail-fields__item--wide': field.wide }"
          :label="field.label"
          :value="field.value"
          :copyable="field.copyable"
          variant="row"
          @copy="emit('copy', $event)"
        />
      </div>
    </section>

    <section v-if="diagnosticFields.length" class="request-detail-fields__section">
      <div class="request-detail-fields__header request-detail-fields__header--muted">诊断字段</div>
      <div class="request-detail-fields__grid request-detail-fields__grid--diagnostic">
        <DetailFieldCard
          v-for="field in diagnosticFields"
          :key="field.label"
          :label="field.label"
          :value="field.value"
          :copyable="field.copyable"
          variant="row"
          @copy="emit('copy', $event)"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { CallDetailField } from '@/api/requestDetail'
import DetailFieldCard from '@/components/ai/DetailFieldCard.vue'

defineProps<{
  primaryFields: CallDetailField[]
  diagnosticFields: CallDetailField[]
}>()

const emit = defineEmits<{
  (e: 'copy', value: string): void
}>()
</script>

<style scoped>
.request-detail-fields {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.request-detail-fields__section {
  border-bottom: 1px solid hsl(var(--border));
  padding-bottom: 16px;
}

.request-detail-fields__header {
  margin-bottom: 10px;
  color: hsl(var(--foreground));
  font-size: 12px;
  font-weight: 600;
}

.request-detail-fields__header--muted {
  color: hsl(var(--muted-foreground));
}

.request-detail-fields__grid {
  display: grid;
  grid-template-columns: minmax(4.8rem, 0.42fr) minmax(0, 1fr);
  gap: 8px;
}

.request-detail-fields__grid > :deep(.detail-field-card--row) {
  grid-column: 1 / -1;
  grid-template-columns: subgrid;
}

.request-detail-fields__grid--diagnostic {
  gap: 6px;
}

.request-detail-fields__item--wide {
  grid-column: 1 / -1;
}

.request-detail-fields__item--wide :deep(.detail-field-card__value) {
  grid-column: 2 / -1;
}

@media (min-width: 640px) {
  .request-detail-fields__grid {
    grid-template-columns:
      minmax(4.8rem, 0.42fr) minmax(0, 1fr)
      minmax(4.8rem, 0.42fr) minmax(0, 1fr);
  }

  .request-detail-fields__grid > :deep(.detail-field-card--row) {
    grid-column: span 2;
  }

  .request-detail-fields__grid > :deep(.request-detail-fields__item--wide.detail-field-card--row) {
    grid-column: 1 / -1;
  }
}
</style>
