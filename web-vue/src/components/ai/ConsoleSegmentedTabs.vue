<template>
  <div
    class="console-segmented-tabs"
    :class="`console-segmented-tabs--${fit}`"
  >
    <SegmentedTabs
      :model-value="modelValue"
      :options="options"
      :aria-label="ariaLabel"
      :fit="fit"
      @update:model-value="(value) => emit('update:modelValue', value)"
    />
  </div>
</template>

<script setup lang="ts">
import { SegmentedTabs } from 'nanocat-ui'
import type { SegmentedOption, SegmentedValue } from 'nanocat-ui'

withDefaults(defineProps<{
  modelValue: SegmentedValue
  options: SegmentedOption[]
  ariaLabel?: string
  fit?: 'stretch' | 'content'
}>(), {
  fit: 'stretch',
})

const emit = defineEmits<{
  'update:modelValue': [value: SegmentedValue]
}>()
</script>

<style scoped>
.console-segmented-tabs {
  display: flex;
  min-width: 0;
  width: 100%;
}

.console-segmented-tabs--content {
  width: max-content;
  max-width: 100%;
}
</style>
