<template>
  <StatusPill
    :label="laneSummaryText(lanes)"
    :tone="laneSummaryTone(lanes)"
    title="Lane 详情"
    card-class="w-56"
  >
    <template #content>
      <div class="mb-2 text-xs font-medium text-foreground">Lane 详情</div>
      <div class="space-y-1.5 text-xs">
        <div
          v-for="lane in laneOrder"
          :key="lane"
          class="flex items-center justify-between rounded-md px-2 py-1"
          :class="laneLineClass(lane, lanes)"
        >
          <span class="font-medium">{{ lane }}</span>
          <span>{{ laneEnabled(lanes, lane) ? '已启用' : '未启用' }}</span>
        </div>
      </div>
    </template>
  </StatusPill>
</template>

<script setup lang="ts">
import { StatusPill } from 'nanocat-ui'
import type { AccountLane } from '@/api/accounts'
import {
  laneEnabled,
  laneLineClass,
  laneSummaryTone,
  laneSummaryText,
} from '@/views/accounts/viewUtils'

withDefaults(
  defineProps<{
    lanes: AccountLane[]
    laneOrder?: AccountLane[]
  }>(),
  {
    laneOrder: () => ['fast', 'thinking', 'pro'],
  }
)
</script>
