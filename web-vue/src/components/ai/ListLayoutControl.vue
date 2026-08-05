<template>
  <div class="flex shrink-0 items-center">
    <div class="w-32">
      <GroupedSelectMenu
        :model-value="modelValue"
        :options="layoutOptions"
        block
        placement="top"
        selected-indicator="check"
        aria-label="列表布局"
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
  { label: '工作区滚动', value: 'workspace' },
  { label: '随页面展开', value: 'page' },
] as const

function updateValue(value: string | string[]) {
  const next = Array.isArray(value) ? value[0] : value
  if (next === 'workspace' || next === 'page') emit('update:modelValue', next)
}
</script>
