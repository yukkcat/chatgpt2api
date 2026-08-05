<template>
  <div class="date-range-inputs">
    <Input
      :model-value="start"
      type="date"
      :root-class="['date-range-input', inputRootClass].filter(Boolean).join(' ')"
      @update:model-value="emit('update:start', String($event || ''))"
    />
    <span class="date-range-separator">{{ separator }}</span>
    <Input
      :model-value="end"
      type="date"
      :root-class="['date-range-input', inputRootClass].filter(Boolean).join(' ')"
      @update:model-value="emit('update:end', String($event || ''))"
    />
  </div>
</template>

<script setup lang="ts">
import { Input } from 'nanocat-ui'

withDefaults(defineProps<{
  start?: string
  end?: string
  separator?: string
  inputRootClass?: string
}>(), {
  start: '',
  end: '',
  separator: '至',
  inputRootClass: '',
})

const emit = defineEmits<{
  'update:start': [value: string]
  'update:end': [value: string]
}>()
</script>

<style scoped>
.date-range-inputs {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: var(--date-range-flex, 0 1 17rem);
  min-width: var(--date-range-min-width, min(100%, 16rem));
}

:deep(.date-range-input) {
  flex: 1 1 0;
  min-width: var(--date-range-input-min-width, 7.25rem);
}

.date-range-separator {
  flex: 0 0 auto;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

@media (max-width: 640px) {
  .date-range-inputs {
    width: 100%;
    min-width: 0;
    align-items: stretch;
  }

  :deep(.date-range-input) {
    flex: 1 1 auto;
    min-width: 0;
    width: 100%;
  }

  .date-range-separator {
    align-self: center;
  }
}
</style>
