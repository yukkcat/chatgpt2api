<template>
  <FormSection title="Dashboard">
    <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
      <FormField label="Default time range">
        <template #label-extra>
          <HelpTip text="Charts use this time range by default when you open the dashboard. You can change it on the page." />
        </template>
        <GroupedSelectMenu
          :model-value="defaultTimeRange"
          :options="DASHBOARD_TIME_RANGE_OPTIONS"
          selected-indicator="none"
          aria-label="Dashboard default time range"
          block
          @update:model-value="setDefaultTimeRange"
        />
      </FormField>

      <FormField label="Auto-refresh interval (seconds)">
        <template #label-extra>
          <HelpTip text="Default: 10 seconds. Range: 5–300 seconds. This preference is saved in this browser and is not sent to the backend." />
        </template>
        <Input
          :model-value="refreshIntervalDraft"
          type="number"
          min="5"
          max="300"
          step="1"
          block
          @update:model-value="refreshIntervalDraft = $event"
          @blur="commitRefreshInterval"
          @keyup.enter="commitRefreshInterval"
        />
      </FormField>
    </div>
  </FormSection>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { FormField, FormSection, GroupedSelectMenu, HelpTip, Input } from 'nanocat-ui'
import { DASHBOARD_TIME_RANGE_OPTIONS } from '@/lib/timeRanges'
import {
  readDashboardDefaultTimeRange,
  readDashboardRefreshIntervalSeconds,
  writeDashboardDefaultTimeRange,
  writeDashboardRefreshIntervalSeconds,
} from '@/views/dashboard/dashboardPreferences'

const defaultTimeRange = ref(readDashboardDefaultTimeRange())
const refreshIntervalDraft = ref(String(readDashboardRefreshIntervalSeconds()))

function setDefaultTimeRange(value: string | string[]) {
  defaultTimeRange.value = writeDashboardDefaultTimeRange(value)
}

function commitRefreshInterval() {
  const seconds = writeDashboardRefreshIntervalSeconds(refreshIntervalDraft.value)
  refreshIntervalDraft.value = String(seconds)
}
</script>
