<template>
  <div class="space-y-5">
    <PageLoadingState
      v-if="!dashboardDataReady && !dashboardLoadError"
      title="Loading dashboard"
      description="Loading the latest account and request data."
    />

    <StateBlock
      v-else-if="!dashboardDataReady"
      title="Dashboard failed to load"
      :description="dashboardLoadError"
    >
      <Button size="sm" variant="outline" root-class="mt-4" @click="retryDashboard">
        Reload
      </Button>
    </StateBlock>

    <template v-else>
    <div
      v-if="dashboardDataWarning"
      class="flex items-center gap-2 rounded-md border border-amber-300/70 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700/70 dark:bg-amber-950/30 dark:text-amber-200"
      role="status"
    >
      <Icon icon="lucide:triangle-alert" class="h-4 w-4 shrink-0" />
      <span>{{ dashboardDataWarning }}</span>
    </div>

    <section
      aria-label="Account overview"
      class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6"
    >
      <StatCard
        v-for="stat in accountStats"
        :key="stat.label"
        :label="stat.label"
        :value="stat.value"
        :icon="stat.icon"
        :icon-bg="stat.iconBg"
        :icon-color="stat.iconColor"
      />
    </section>

    <section
      aria-label="Request overview"
      class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6"
    >
      <StatCard
        v-for="stat in callStats"
        :key="stat.label"
        :label="stat.label"
        :value="stat.value"
        :icon="stat.icon"
        :icon-tone="stat.iconTone"
      />
    </section>

    <section>
      <PagePanel class="!rounded-xl">
        <PanelHeader title="Runtime environment" align="start" />

        <div class="mt-4 grid min-w-0 gap-5 xl:grid-cols-[minmax(20rem,0.9fr)_minmax(0,1.4fr)]">
          <section class="min-w-0 xl:h-full" aria-label="Resource usage">
            <div class="grid grid-cols-2 gap-x-5 gap-y-5 xl:h-full xl:grid-rows-2 xl:gap-y-0">
              <div
                v-for="metric in runtimeResourceMetrics"
                :key="metric.label"
                class="min-w-0 xl:flex xl:flex-col xl:justify-center"
              >
                <div class="flex items-center justify-between gap-3">
                  <div class="flex min-w-0 items-center gap-2">
                    <Icon :icon="metric.icon" class="h-4 w-4 shrink-0" :class="metric.iconClass" aria-hidden="true" />
                    <p class="truncate text-sm text-muted-foreground">{{ metric.label }}</p>
                  </div>
                  <p class="shrink-0 text-sm font-semibold tabular-nums text-foreground">{{ metric.value }}</p>
                </div>
                <div
                  class="mt-2.5 h-1.5 overflow-hidden rounded-full bg-muted/70"
                  :role="metric.progress === null ? undefined : 'progressbar'"
                  :aria-label="metric.progress === null ? undefined : `${metric.label} usage`"
                  :aria-valuenow="metric.progress === null ? undefined : metric.progress"
                  :aria-valuemin="metric.progress === null ? undefined : 0"
                  :aria-valuemax="metric.progress === null ? undefined : 100"
                >
                  <span
                    v-if="metric.progress !== null"
                    class="block h-full rounded-full bg-current transition-[width] duration-500"
                    :class="metric.progressClass"
                    :style="{ width: `${metric.progress}%` }"
                  ></span>
                </div>
              </div>
            </div>
          </section>

          <section
            class="min-w-0 border-t border-border/60 pt-4 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0"
            aria-label="Runtime details"
          >
            <dl class="grid min-w-0 grid-cols-1 gap-x-6 sm:grid-cols-2">
              <div
                v-for="detail in runtimeDetails"
                :key="detail.label"
                class="flex min-w-0 items-center justify-between gap-3 border-b border-border/50 py-2 first:pt-0 sm:[&:nth-child(2)]:pt-0"
              >
                <dt class="flex min-w-0 shrink-0 items-center gap-2 text-xs text-muted-foreground">
                  <Icon :icon="detail.icon" class="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span class="truncate">{{ detail.label }}</span>
                </dt>
                <dd class="min-w-0 truncate text-right text-sm font-medium tabular-nums" :title="detail.value">{{ detail.value }}</dd>
              </div>
            </dl>
          </section>
        </div>
      </PagePanel>
    </section>

    <section class="grid grid-cols-1 gap-4">
      <ChartCard title="Requests by model">
        <template #title-extra>
          <HelpTip text="Only successful and partially successful requests are included." />
        </template>
        <template #actions>
          <TimeRangeTabs v-model="modelTimeRange" aria-label="Requests by model time range" />
        </template>
        <div ref="modelChartRef" class="h-72 w-full px-2"></div>
      </ChartCard>
    </section>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ChartCard title="Request outcomes over time">
        <template #actions>
          <TimeRangeTabs v-model="trendTimeRange" aria-label="Request outcome time range" />
        </template>
        <div ref="trendChartRef" class="h-56 w-full"></div>
      </ChartCard>

      <ChartCard title="Request activity">
        <template #actions>
          <TimeRangeTabs v-model="activityTimeRange" aria-label="Request activity time range" />
        </template>
        <div class="flex h-56 items-center px-1">
          <div
            v-if="activityHasData"
            class="mx-auto flex w-full flex-col gap-4"
            :style="{ maxWidth: activityGridMaxWidth }"
          >
            <div
              :key="`${activityAnimationEpoch}-${activityTimeRange}`"
              class="grid gap-1.5"
              :style="{ gridTemplateColumns: `repeat(${activityColumnCount}, minmax(0, 1fr))` }"
            >
              <span
                v-for="(bucket, index) in activityBuckets"
                :key="`${activityAnimationEpoch}-${activityTimeRange}-${bucket.start_at}`"
                class="dashboard-activity-cell grid min-w-0"
                :style="{ animationDelay: `${Math.min(index * 2, 32)}ms` }"
              >
                <HoverCard card-class="w-52" :offset="8" focusable>
                  <span
                    class="dashboard-activity-cell-trigger block aspect-square w-full min-w-0 rounded-[3px] border border-transparent transition-[background-color,box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:shadow-sm"
                    :class="activityCellClass(bucket.total_calls)"
                    role="img"
                    :aria-label="activityTooltip(bucket)"
                  ></span>
                  <template #content>
                    <div class="mb-2 text-xs font-semibold text-foreground">{{ bucket.label }}</div>
                    <div class="grid gap-1.5 text-xs">
                      <div
                        v-for="item in activityTooltipItems(bucket)"
                        :key="item.label"
                        class="flex items-center justify-between gap-4"
                      >
                        <span class="inline-flex items-center gap-1.5 text-muted-foreground">
                          <span class="h-2 w-2 rounded-full" :class="item.markerClass"></span>
                          {{ item.label }}
                        </span>
                        <span class="font-semibold text-foreground">{{ item.value }}</span>
                      </div>
                    </div>
                  </template>
                </HoverCard>
              </span>
            </div>
            <div class="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>{{ activityBuckets[0]?.label || '--' }}</span>
              <span class="flex items-center gap-1.5">
                <span>Less</span>
                <span class="h-2.5 w-2.5 rounded-[2px] bg-muted/60"></span>
                <span class="h-2.5 w-2.5 rounded-[2px] bg-emerald-100 dark:bg-emerald-950/70"></span>
                <span class="h-2.5 w-2.5 rounded-[2px] bg-emerald-200 dark:bg-emerald-900/70"></span>
                <span class="h-2.5 w-2.5 rounded-[2px] bg-emerald-400 dark:bg-emerald-700"></span>
                <span class="h-2.5 w-2.5 rounded-[2px] bg-emerald-600 dark:bg-emerald-500"></span>
                <span>More</span>
              </span>
              <span>{{ activityBuckets[activityBuckets.length - 1]?.label || '--' }}</span>
            </div>
          </div>
          <p v-else class="w-full text-center text-sm text-muted-foreground" role="status">
            No requests to display for this time range.
          </p>
        </div>
      </ChartCard>

      <ChartCard title="Successful request duration">
        <template #actions>
          <TimeRangeTabs v-model="responseTimeTimeRange" aria-label="Successful request duration time range" />
        </template>
        <div ref="responseTimeChartRef" class="h-56 w-full"></div>
      </ChartCard>

      <ChartCard title="Response time by model">
        <template #actions>
          <TimeRangeTabs v-model="modelResponseTimeTimeRange" aria-label="Response time by model time range" />
        </template>
        <div ref="modelResponseTimeChartRef" class="h-56 w-full"></div>
      </ChartCard>
    </section>

    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button, ChartCard, HelpTip, HoverCard, StatCard } from 'nanocat-ui'
import { Icon } from '@iconify/vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import PagePanel from '@/components/ai/PagePanel.vue'
import PanelHeader from '@/components/ai/PanelHeader.vue'
import StateBlock from '@/components/ai/StateBlock.vue'
import TimeRangeTabs from '@/components/ai/TimeRangeTabs.vue'
import { formatRequestDuration } from '@/lib/requestDuration'
import type { DashboardBucket } from '@/types/api'
import { useDashboardPage } from './dashboard/useDashboardPage'

defineOptions({ name: 'Dashboard' })

const {
  stats: accountStats,
  dashboardRanges,
  dashboardRuntime,
  dashboardOperations,
  dashboardDataReady,
  dashboardLoadError,
  dashboardDataWarning,
  dashboardVersion,
  retryDashboard,
  modelTimeRange,
  trendTimeRange,
  activityTimeRange,
  activityAnimationEpoch,
  responseTimeTimeRange,
  modelResponseTimeTimeRange,
  activityBuckets,
  activityHasData,
  trendChartRef,
  responseTimeChartRef,
  modelResponseTimeChartRef,
  modelChartRef,
} = useDashboardPage()

const callStats = computed(() => {
  const range = dashboardRanges.value?.['24h']
  const totals = range?.totals
  const switching = range?.switching
  return [
    {
      label: 'Current concurrency',
      value: formatCount(dashboardOperations.value?.active_requests),
      icon: 'lucide:layers-3',
      iconTone: 'info' as const,
    },
    {
      label: 'Total requests',
      value: formatCount(totals?.total),
      icon: 'lucide:messages-square',
      iconTone: 'neutral' as const,
    },
    {
      label: 'Success rate',
      value: formatPercent(totals?.success_rate),
      icon: 'lucide:circle-check',
      iconTone: 'success' as const,
    },
    {
      label: 'Average successful duration',
      value: formatRequestDuration(totals?.avg_success_duration_ms) || '--',
      icon: 'lucide:timer',
      iconTone: 'info' as const,
    },
    {
      label: 'Account switches',
      value: formatCount(switching?.requests),
      icon: 'lucide:repeat-2',
      iconTone: 'warning' as const,
    },
    {
      label: 'Recovery rate after switching',
      value: formatPercent(switching?.recovery_rate),
      icon: 'lucide:shield-check',
      iconTone: 'success' as const,
    },
  ]
})

const activityMaxCalls = computed(() => Math.max(
  0,
  ...activityBuckets.value.map((bucket) => bucket.total_calls),
))
const activityColumnCount = computed(() => {
  if (activityTimeRange.value === '24h') return 12
  if (activityTimeRange.value === '7d') return 7
  return 10
})
const activityGridMaxWidth = computed(() => {
  const columnCount = activityColumnCount.value
  const cellWidthRem = activityTimeRange.value === '7d' ? 5.5 : 3.5
  const gapWidthRem = 0.375
  return `${columnCount * cellWidthRem + (columnCount - 1) * gapWidthRem}rem`
})

const runtimeResourceMetrics = computed(() => {
  const runtime = dashboardRuntime.value
  return [
    {
      label: 'Application CPU',
      value: formatPercent(runtime?.process_cpu_percent),
      icon: 'lucide:cpu',
      iconClass: 'text-sky-600 dark:text-sky-400',
      progress: runtime?.process_cpu_percent ?? null,
      progressClass: 'text-sky-500 dark:text-sky-400',
    },
    {
      label: 'Application memory',
      value: formatBytes(runtime?.process_memory_bytes),
      icon: 'lucide:memory-stick',
      iconClass: 'text-indigo-600 dark:text-indigo-400',
      progress: runtime?.process_memory_percent ?? null,
      progressClass: 'text-indigo-500 dark:text-indigo-400',
    },
    {
      label: memoryScopeLabel(runtime?.memory_scope),
      value: formatPercent(runtime?.memory_percent),
      icon: 'lucide:memory-stick',
      iconClass: 'text-amber-600 dark:text-amber-400',
      progress: runtime?.memory_percent ?? null,
      progressClass: 'text-amber-500 dark:text-amber-400',
    },
    {
      label: 'Data disk',
      value: formatPercent(runtime?.storage_percent),
      icon: 'lucide:hard-drive',
      iconClass: 'text-muted-foreground',
      progress: runtime?.storage_percent ?? null,
      progressClass: 'text-slate-500 dark:text-slate-400',
    },
  ]
})

const runtimeDetails = computed(() => {
  const runtime = dashboardRuntime.value
  return [
    {
      label: 'Runtime type',
      value: runtime
        ? runtime.runtime_mode === 'docker'
          ? 'Docker'
          : `Python ${runtime.python_version}`
        : '--',
      icon: 'lucide:server-cog',
    },
    { label: 'Application version', value: dashboardVersion.value, icon: 'lucide:tag' },
    {
      label: 'Instance name',
      value: runtime?.instance_name || '--',
      icon: 'lucide:hard-drive',
    },
    {
      label: 'Operating system',
      value: runtime?.distribution || '--',
      icon: 'lucide:binary',
    },
    {
      label: 'Kernel / architecture',
      value: runtime ? `${runtime.kernel_version} / ${runtime.architecture}` : '--',
      icon: 'lucide:binary',
    },
    {
      label: 'CPU capacity',
      value: formatCpuCapacity(runtime?.cpu_capacity),
      icon: 'lucide:cpu',
    },
    {
      label: 'Service started',
      value: formatDateTime(runtime?.service_started_at),
      icon: 'lucide:clock-3',
    },
    {
      label: 'Inbound rate',
      value: formatRate(runtime?.network_rx_bytes_per_sec),
      icon: 'lucide:arrow-down-to-line',
    },
    {
      label: 'Uptime',
      value: formatUptime(runtime?.service_uptime_seconds),
      icon: 'lucide:timer',
    },
    {
      label: 'Outbound rate',
      value: formatRate(runtime?.network_tx_bytes_per_sec),
      icon: 'lucide:arrow-up-from-line',
    },
  ]
})

function formatCount(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--'
  return Math.max(0, Math.trunc(value)).toLocaleString('zh-CN')
}

function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined ? '--' : `${value.toFixed(1)}%`
}

function formatBytes(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--'
  if (value < 1_024) return `${Math.round(value)} B`
  if (value < 1_024 ** 2) return `${(value / 1_024).toFixed(1)} KB`
  if (value < 1_024 ** 3) return `${(value / 1_024 ** 2).toFixed(1)} MB`
  if (value < 1_024 ** 4) return `${(value / 1_024 ** 3).toFixed(1)} GB`
  return `${(value / 1_024 ** 4).toFixed(1)} TB`
}

function formatRate(value: number | null | undefined) {
  if (value === null || value === undefined) return '--'
  if (value < 1_000) return `${Math.round(value)} B/s`
  if (value < 1_000_000) return `${(value / 1_000).toFixed(1)} KB/s`
  return `${(value / 1_000_000).toFixed(1)} MB/s`
}

function formatCpuCapacity(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value) || value <= 0) return '--'
  const digits = Number.isInteger(value) ? 0 : 2
  return `${value.toLocaleString('en-US', { maximumFractionDigits: digits })} cores`
}

function memoryScopeLabel(scope: 'container' | 'system' | 'visible' | undefined) {
  if (scope === 'container') return 'Container memory'
  if (scope === 'system') return 'System memory'
  return 'Available memory'
}

function formatUptime(value: number | null | undefined) {
  if (value === null || value === undefined) return '--'
  const seconds = Math.max(0, Math.trunc(value))
  const days = Math.floor(seconds / 86_400)
  const hours = Math.floor((seconds % 86_400) / 3_600)
  const minutes = Math.floor((seconds % 3_600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '--'
  return value.replace('T', ' ').replace(/([+-]\d\d:\d\d|Z)$/, '')
}

function activityCellClass(value: number) {
  const maximum = activityMaxCalls.value
  if (value <= 0 || maximum <= 0) return 'bg-muted/60'
  const ratio = Math.log1p(value) / Math.log1p(maximum)
  if (ratio <= 0.25) return 'bg-emerald-100 dark:bg-emerald-950/70'
  if (ratio <= 0.5) return 'bg-emerald-200 dark:bg-emerald-900/70'
  if (ratio <= 0.75) return 'bg-emerald-400 dark:bg-emerald-700'
  return 'bg-emerald-600 dark:bg-emerald-500'
}

function activityTooltip(bucket: DashboardBucket) {
  return `${bucket.label} · Requests ${formatCount(bucket.total_calls)} · Successful ${formatCount(bucket.success_calls)} · Failed ${formatCount(bucket.final_failed_calls)} · Success rate ${formatPercent(bucket.success_rate)}`
}

function activityTooltipItems(bucket: DashboardBucket) {
  return [
    {
      label: 'Requests',
      value: formatCount(bucket.total_calls),
      markerClass: 'bg-slate-500 dark:bg-slate-400',
    },
    {
      label: 'Successful',
      value: formatCount(bucket.success_calls),
      markerClass: 'bg-emerald-500',
    },
    {
      label: 'Failed',
      value: formatCount(bucket.final_failed_calls),
      markerClass: 'bg-rose-500',
    },
    {
      label: 'Success rate',
      value: formatPercent(bucket.success_rate),
      markerClass: 'bg-amber-500',
    },
  ]
}

</script>

<style scoped>
.dashboard-activity-cell {
  animation: dashboard-activity-cell-enter 180ms ease-out both;
}

@keyframes dashboard-activity-cell-enter {
  from {
    opacity: 0.35;
  }
  to {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .dashboard-activity-cell,
  .dashboard-activity-cell-trigger {
    animation: none;
    transition: none;
  }

  .dashboard-activity-cell-trigger:hover {
    transform: none;
  }
}
</style>
