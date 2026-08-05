<template>
  <div class="space-y-5">
    <PageLoadingState
      v-if="!dashboardDataReady && !dashboardLoadError"
      title="正在加载概览"
      description="读取最新账号和调用数据。"
    />

    <StateBlock
      v-else-if="!dashboardDataReady"
      title="概览加载失败"
      :description="dashboardLoadError"
    >
      <Button size="sm" variant="outline" root-class="mt-4" @click="retryDashboard">
        重新加载
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

    <section class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <StatCard
        v-for="stat in stats"
        :key="stat.label"
        :label="stat.label"
        :value="stat.value"
        :caption="stat.meta"
        :icon="stat.icon"
        :icon-bg="stat.iconBg"
        :icon-color="stat.iconColor"
      />
    </section>

    <section class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <StatCard
        v-for="stat in callStats"
        :key="stat.label"
        :label="stat.label"
        :value="stat.value"
        :icon="stat.icon"
        :icon-tone="stat.iconTone"
      />
    </section>

    <section class="grid grid-cols-1 gap-4">
      <ChartCard title="模型请求分布">
        <template #actions>
          <TimeRangeTabs v-model="modelTimeRange" aria-label="模型请求分布时间范围" />
        </template>
        <div ref="modelChartRef" class="h-72 w-full px-2"></div>
      </ChartCard>
    </section>

    <section class="grid grid-cols-1 gap-4">
      <ChartCard title="调用结果趋势">
        <template #actions>
          <TimeRangeTabs v-model="trendTimeRange" aria-label="调用结果趋势时间范围" />
        </template>
        <div ref="trendChartRef" class="h-56 w-full"></div>
      </ChartCard>
    </section>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ChartCard title="成功率趋势">
        <template #actions>
          <TimeRangeTabs v-model="successRateTimeRange" aria-label="成功率趋势时间范围" />
        </template>
        <div ref="successRateChartRef" class="h-56 w-full"></div>
      </ChartCard>

      <ChartCard title="成功耗时趋势">
        <template #actions>
          <TimeRangeTabs v-model="responseTimeTimeRange" aria-label="成功耗时趋势时间范围" />
        </template>
        <div ref="responseTimeChartRef" class="h-56 w-full"></div>
      </ChartCard>
    </section>

    <section>
      <ChartCard title="数据明细">
        <template #actions>
          <TimeRangeTabs v-model="detailTimeRange" aria-label="数据明细时间范围" />
        </template>
        <div ref="detailChartRef" class="h-[28rem] w-full"></div>
      </ChartCard>
    </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button, ChartCard, StatCard } from 'nanocat-ui'
import { Icon } from '@iconify/vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import StateBlock from '@/components/ai/StateBlock.vue'
import TimeRangeTabs from '@/components/ai/TimeRangeTabs.vue'
import { useDashboardPage } from './dashboard/useDashboardPage'

defineOptions({ name: 'Dashboard' })

const {
  stats,
  dashboardRanges,
  dashboardDataReady,
  dashboardLoadError,
  dashboardDataWarning,
  retryDashboard,
  modelTimeRange,
  trendTimeRange,
  successRateTimeRange,
  responseTimeTimeRange,
  detailTimeRange,
  trendChartRef,
  successRateChartRef,
  responseTimeChartRef,
  modelChartRef,
  detailChartRef,
} = useDashboardPage()

const selectedRange = computed(() => dashboardRanges.value?.['24h'] ?? null)

function formatCount(value: number) {
  return Math.max(0, Math.trunc(value)).toLocaleString('zh-CN')
}

function formatPercent(value: number | null) {
  return value === null ? '--' : `${value.toFixed(1)}%`
}

function formatDuration(value: number | null) {
  if (value === null) return '--'
  const magnitude = Math.abs(value)
  if (magnitude < 1_000) return `${Math.round(value)}ms`
  if (magnitude < 60_000) return `${(value / 1_000).toFixed(1)}s`
  return `${(value / 60_000).toFixed(1)}m`
}

const callStats = computed(() => {
  const range = selectedRange.value
  const totals = range?.totals
  return [
    {
      label: '总调用量',
      value: totals ? formatCount(totals.total) : '--',
      icon: 'lucide:message-square-text',
      iconTone: 'info' as const,
    },
    {
      label: '成功率',
      value: formatPercent(totals?.success_rate ?? null),
      icon: 'lucide:circle-check',
      iconTone: 'success' as const,
    },
    {
      label: '平均成功耗时',
      value: formatDuration(totals?.avg_success_duration_ms ?? null),
      icon: 'lucide:clock-3',
      iconTone: 'neutral' as const,
    },
    {
      label: 'P95 耗时',
      value: formatDuration(totals?.p95_success_duration_ms ?? null),
      icon: 'lucide:history',
      iconTone: 'warning' as const,
    },
    {
      label: '触发切号',
      value: range ? formatCount(range.switching.requests) : '--',
      icon: 'lucide:repeat-2',
      iconTone: 'info' as const,
    },
    {
      label: '切换恢复率',
      value: formatPercent(range?.switching.recovery_rate ?? null),
      icon: 'lucide:refresh-cw',
      iconTone: 'info' as const,
    },
  ]
})

</script>
