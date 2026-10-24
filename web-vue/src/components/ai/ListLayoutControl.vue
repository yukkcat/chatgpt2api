<template>
  <div class="flex shrink-0 items-center">
    <div class="w-32">
      <GroupedSelectMenu
        :model-value="modelValue"
        :options="layoutOptions"
        block
        placement="top"
        selected-indicator="check"
        aria-label="List layout"
        @update:model-value="updateValue"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { GroupedSelectMenu } from 'nanocat-ui'

import type { ListLayoutMode } from '@/composables/useListLayoutPreference'

defineProps<{
  modelValue: ListLayoutMode
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: ListLayoutMode): void
}>()

const layoutOptions = [
  { label: 'Scroll within workspace', value: 'workspace' },
  { label: 'Expand with page', value: 'page' },
] as const

function updateValue(value: string | string[]) {
  const next = Array.isArray(value) ? value[0] : value
  if (next === 'workspace' || next === 'page') emit('update:modelValue', next)
}
</script>
