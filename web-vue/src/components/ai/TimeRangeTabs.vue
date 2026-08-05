<template>
  <ConsoleSegmentedTabs
    :model-value="modelValue"
    :options="DASHBOARD_TIME_RANGE_OPTIONS"
    :aria-label="ariaLabel"
    fit="content"
    @update:model-value="(value) => emit('update:modelValue', value as DashboardTimeRange)"
  />
</template>

<script setup lang="ts">
import ConsoleSegmentedTabs from './ConsoleSegmentedTabs.vue'
import {
  DASHBOARD_TIME_RANGE_OPTIONS,
  type DashboardTimeRange,
} from '@/lib/timeRanges'

defineProps<{
  modelValue: DashboardTimeRange
  ariaLabel?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: DashboardTimeRange]
}>()
</script>
