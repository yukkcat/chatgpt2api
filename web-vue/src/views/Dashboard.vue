<template>
  <div class="space-y-5">
    <PageLoadingState
      v-if="!dashboardDataReady && !dashboardLoadError"
      title="正在加载概览"
      description="读取最新账号、调用趋势和模型统计。"
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

    <section class="grid grid-cols-1 gap-4">
      <ChartCard title="模型调用分布">
        <template #actions>
          <TimeRangeTabs v-model="timeRangeHourlyRequests" aria-label="模型调用分布时间范围" />
        </template>
        <div ref="hourlyRequestsChartRef" class="h-72 w-full px-2"></div>
      </ChartCard>
    </section>

    <section class="grid grid-cols-1 gap-4">
      <ChartCard title="调用趋势">
        <template #actions>
          <TimeRangeTabs v-model="timeRangeTrend" aria-label="调用趋势时间范围" />
        </template>
        <div ref="trendChartRef" class="h-56 w-full"></div>
      </ChartCard>
    </section>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ChartCard title="成功率趋势">
        <template #actions>
          <TimeRangeTabs v-model="timeRangeSuccessRate" aria-label="成功率趋势时间范围" />
        </template>
        <div ref="successRateChartRef" class="h-56 w-full"></div>
      </ChartCard>

      <ChartCard title="平均成功耗时">
        <template #actions>
          <TimeRangeTabs v-model="timeRangeResponseTime" aria-label="平均成功耗时时间范围" />
        </template>
        <div ref="responseTimeChartRef" class="h-56 w-full"></div>
      </ChartCard>
    </section>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ChartCard title="模型调用占比">
        <template #actions>
          <TimeRangeTabs v-model="timeRangeModel" aria-label="模型调用占比时间范围" />
        </template>
        <div ref="modelChartRef" class="h-56 w-full"></div>
      </ChartCard>

      <ChartCard title="模型成功排行">
        <template #actions>
          <TimeRangeTabs v-model="timeRangeModelRank" aria-label="模型成功排行时间范围" />
        </template>
        <div ref="modelRankChartRef" class="h-56 w-full"></div>
      </ChartCard>
    </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { Button, ChartCard, StatCard } from 'nanocat-ui'
import { Icon } from '@iconify/vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import StateBlock from '@/components/ai/StateBlock.vue'
import TimeRangeTabs from '@/components/ai/TimeRangeTabs.vue'
import { useDashboardPage } from './dashboard/useDashboardPage'

defineOptions({ name: 'Dashboard' })

const {
  stats,
  dashboardDataReady,
  dashboardLoadError,
  dashboardDataWarning,
  retryDashboard,
  timeRangeHourlyRequests,
  timeRangeTrend,
  timeRangeSuccessRate,
  timeRangeModel,
  timeRangeModelRank,
  timeRangeResponseTime,
  hourlyRequestsChartRef,
  trendChartRef,
  successRateChartRef,
  responseTimeChartRef,
  modelChartRef,
  modelRankChartRef,
} = useDashboardPage()
</script>
