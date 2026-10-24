<template>
  <label class="block text-xs">
    <span class="ui-field-label">Target group</span>
    <GroupedSelectMenu
      :model-value="modelValue"
      :options="options"
      selected-indicator="none"
      aria-label="Target group"
      block
      :disabled="disabled || loading"
      @update:model-value="$emit('update:modelValue', String($event))"
    />
  </label>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { GroupedSelectMenu } from 'nanocat-ui'

import type { AccountGroup } from '@/api/accounts'

const props = withDefaults(defineProps<{
  modelValue: string
  groups: AccountGroup[]
  disabled?: boolean
  loading?: boolean
}>(), {
  disabled: false,
  loading: false,
})

defineEmits<{
  'update:modelValue': [value: string]
}>()

const options = computed(() => [
  { label: 'Keep source group', value: '__preserve__' },
  { label: 'No group', value: '' },
  ...props.groups.map((group) => ({
    label: group.name || group.id,
    value: group.id,
  })),
])
</script>
