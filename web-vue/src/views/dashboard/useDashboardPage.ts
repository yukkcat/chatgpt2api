import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { statsApi } from '@/api/stats'
import type {
  DashboardAccountStats,
  DashboardRangeStats,
  DashboardResponse,
} from '@/types/api'
import { usePageQuery, useSerialVisibilityPolling } from '@/composables/usePageQuery'
import { usePageRuntime } from '@/composables/usePageRuntime'
import {
  getLineChartTheme,
  createLineSeries,
  chartColors,
  getModelColor,
} from '@/lib/chartTheme'
import type { DashboardTimeRange } from '@/lib/timeRanges'
import { buildDashboardTrendSeries } from '@/views/dashboard/dashboardTrendSeries'
import {
  readDashboardDefaultTimeRange,
  readDashboardRefreshIntervalSeconds,
} from '@/views/dashboard/dashboardPreferences'

const SUCCESS_RATE_DEMO_VALUES = [92, 94, 91, 96, 95, 97, 96, 98]
const SUCCESS_DURATION_DEMO_SECONDS = [48, 54, 46, 59, 52, 49, 56, 51]
const DASHBOARD_TOOLTIP_HTML_ESCAPE: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

type DashboardTooltipItem = {
  axisValue?: unknown
  marker?: string
  seriesName?: unknown
  value?: unknown
}

function escapeDashboardTooltipText(value: unknown) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => (
    DASHBOARD_TOOLTIP_HTML_ESCAPE[character]
  ))
}

function formatDashboardAxisTooltip(
  rawParams: unknown,
  formatValue: (value: number, item: DashboardTooltipItem) => string,
) {
  if (!Array.isArray(rawParams)) return ''
  const params = rawParams.filter((item): item is DashboardTooltipItem => (
    Boolean(item) && typeof item === 'object'
  ))
  if (!params.length) return ''

  let result = `<div style="font-weight: 600; margin-bottom: 4px;">${escapeDashboardTooltipText(params[0].axisValue)}</div>`
  params.forEach((item) => {
    if (item.value === null || item.value === undefined) return
    const numericValue = Number(item.value)
    if (!Number.isFinite(numericValue)) return
    const marker = typeof item.marker === 'string' ? item.marker : ''
    const seriesName = escapeDashboardTooltipText(item.seriesName)
    const value = escapeDashboardTooltipText(formatValue(numericValue, item))
    result += `<div style="display: flex; justify-content: space-between; gap: 16px; align-items: center;">
      <span>${marker}${marker ? ' ' : ''}${seriesName}</span>
      <span style="font-weight: 600;">${value}</span>
    </div>`
  })
  return result
}

function resampleDemoValues(values: number[], pointCount: number) {
  if (pointCount <= 0) return []
  if (pointCount === 1) return [values[0]]

  return Array.from({ length: pointCount }, (_, index) => {
    const position = index * (values.length - 1) / (pointCount - 1)
    const lowerIndex = Math.floor(position)
    const upperIndex = Math.ceil(position)
    if (lowerIndex === upperIndex) return values[lowerIndex]

    const offset = position - lowerIndex
    return Number((
      values[lowerIndex] + (values[upperIndex] - values[lowerIndex]) * offset
    ).toFixed(2))
  })
}

function resolveDemoLabels(labels: string[]) {
  return labels.length > 0
    ? labels
    : ['-7h', '-6h', '-5h', '-4h', '-3h', '-2h', '-1h', 'Now']
}

function createStraightAreaLineSeries(
  name: string,
  data: Array<number | null>,
  color: string,
  areaOpacity: number,
) {
  return {
    name,
    type: 'line',
    data,
    smooth: false,
    showSymbol: true,
    connectNulls: true,
    symbolSize: 5,
    lineStyle: { width: 2 },
    areaStyle: { opacity: areaOpacity },
    itemStyle: { color },
    emphasis: { disabled: true },
    z: 2,
  }
}

function resolveDashboardBarMaxWidth(pointCount: number) {
  if (pointCount <= 7) return 96
  if (pointCount <= 24) return 48
  return 36
}

function prefersReducedDashboardMotion() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}


export function useDashboardPage() {
  type ChartInstance = {
    setOption: (
      option: unknown,
      opts?: boolean | { notMerge?: boolean; lazyUpdate?: boolean; replaceMerge?: string[] }
    ) => void
    resize: () => void
    dispose: () => void
    clear?: () => void
  }
  type RenderMode = 'initial' | 'entry' | 'range' | 'refresh'
  const pageRuntime = usePageRuntime('dashboard')
  const DASHBOARD_DATA_REQUEST_KEY = 'dashboard:data'
  const CHART_BOOTSTRAP_TIMER_KEY = 'dashboard:chart-bootstrap'
  const DASHBOARD_POLL_TIMER_KEY = 'dashboard:poll'
  const dashboardQueryError = ref('')
  const dashboardDataQuery = usePageQuery({
    runtime: pageRuntime,
    key: DASHBOARD_DATA_REQUEST_KEY,
    error: dashboardQueryError,
    errorMessage: 'Dashboard failed to load',
  })
  const dashboardLoadError = ref('')
  const dashboardDataWarning = ref('')

  const defaultTimeRange = readDashboardDefaultTimeRange()
  const modelTimeRange = ref<DashboardTimeRange>(defaultTimeRange)
  const trendTimeRange = ref<DashboardTimeRange>(defaultTimeRange)
  const activityTimeRange = ref<DashboardTimeRange>(defaultTimeRange)
  const activityAnimationEpoch = ref(0)
  const responseTimeTimeRange = ref<DashboardTimeRange>(defaultTimeRange)
  const modelResponseTimeTimeRange = ref<DashboardTimeRange>(defaultTimeRange)

  function applyDashboardDefaultTimeRange() {
    const nextTimeRange = readDashboardDefaultTimeRange()
    modelTimeRange.value = nextTimeRange
    trendTimeRange.value = nextTimeRange
    activityTimeRange.value = nextTimeRange
    responseTimeTimeRange.value = nextTimeRange
    modelResponseTimeTimeRange.value = nextTimeRange
  }

  function createDefaultStats() {
    return [
      {
        label: 'Total accounts',
        value: '0',
        meta: '',
        icon: 'lucide:users',
        iconBg: 'bg-sky-100',
        iconColor: 'text-sky-600'
      },
      {
        label: 'Normal accounts',
        value: '0',
        meta: '',
        icon: 'lucide:check-circle',
        iconBg: 'bg-emerald-100',
        iconColor: 'text-emerald-600'
      },
      {
        label: 'Rate-limited accounts',
        value: '0',
        meta: '',
        icon: 'lucide:clock',
        iconBg: 'bg-amber-100',
        iconColor: 'text-amber-600'
      },
      {
        label: 'Invalid accounts',
        value: '0',
        meta: '',
        icon: 'lucide:alert-circle',
        iconBg: 'bg-rose-100',
        iconColor: 'text-rose-600'
      },
      {
        label: 'Disabled accounts',
        value: '0',
        meta: '',
        icon: 'lucide:ban',
        iconBg: 'bg-slate-100',
        iconColor: 'text-slate-600'
      },
      {
        label: 'Remaining quota',
        value: '0',
        meta: '',
        icon: 'lucide:coins',
        iconBg: 'bg-cyan-100',
        iconColor: 'text-cyan-600'
      },
    ]
  }

  const stats = ref(createDefaultStats())
  const dashboardRanges = shallowRef<DashboardResponse['ranges'] | null>(null)
  const activityBuckets = computed(() => (
    dashboardRanges.value?.[activityTimeRange.value]?.buckets ?? []
  ))
  const activityHasData = computed(() => (
    activityBuckets.value.some(bucket => bucket.total_calls > 0)
  ))
  const dashboardRuntime = shallowRef<DashboardResponse['runtime'] | null>(null)
  const dashboardOperations = shallowRef<DashboardResponse['operations'] | null>(null)
  const dashboardVersion = ref('--')

  // Each chart has an independent data state.
  function createEmptyChartData() {
    return {
      trend: {
        labels: [] as string[],
        finalFailedRequests: [] as number[],
        switchCount: [] as number[],
        successRequests: [] as number[],
        successRate: [] as Array<number | null>,
      },
      model: {
        labels: [] as string[],
        successRequests: {} as Record<string, number[]>,
      },
      responseTime: {
        labels: [] as string[],
        avgSuccessDurationMs: [] as Array<number | null>,
      },
      modelResponseTime: {
        labels: [] as string[],
        modelAvgSuccessDurationMs: {} as Record<string, Array<number | null>>,
      },
    }
  }

  const chartData = ref(createEmptyChartData())

  let dashboardSnapshot: DashboardResponse | null = null
  let dashboardRenderSignature: string | null = null

  let dashboardRefreshEpoch = 0
  let dashboardRefreshInFlight: {
    epoch: number
    promise: Promise<boolean>
    controller: AbortController
  } | null = null
  const trendChartRef = ref<HTMLDivElement | null>(null)
  const modelChartRef = ref<HTMLDivElement | null>(null)
  const responseTimeChartRef = ref<HTMLDivElement | null>(null)
  const modelResponseTimeChartRef = ref<HTMLDivElement | null>(null)

  const charts = {
    trend: null as ChartInstance | null,
    model: null as ChartInstance | null,
    responseTime: null as ChartInstance | null,
    modelResponseTime: null as ChartInstance | null,
  }

  type ChartKey = keyof typeof charts
  const renderProfiles: Record<RenderMode, {
    duration: number
    updateDuration: number
    delayStep: number
    lazyUpdate: boolean
  }> = {
    initial: { duration: 860, updateDuration: 620, delayStep: 14, lazyUpdate: false },
    entry: { duration: 560, updateDuration: 460, delayStep: 8, lazyUpdate: false },
    range: { duration: 560, updateDuration: 460, delayStep: 8, lazyUpdate: false },
    refresh: { duration: 260, updateDuration: 220, delayStep: 0, lazyUpdate: true },
  }
  const chartFirstRenderState = ref<Record<ChartKey, boolean>>({
    trend: true,
    model: true,
    responseTime: true,
    modelResponseTime: true,
  })
  const chartsBootstrapped = ref(false)
  const dashboardDataReady = ref(false)
  let dashboardEntrySeq = 0
  let chartResizeObserver: ResizeObserver | null = null
  let chartResizeFrame = 0

  function chartElements() {
    return [
      trendChartRef.value,
      modelChartRef.value,
      responseTimeChartRef.value,
      modelResponseTimeChartRef.value,
    ].filter((element): element is HTMLDivElement => Boolean(element))
  }

  function scheduleChartResize() {
    if (chartResizeFrame) return
    chartResizeFrame = requestAnimationFrame(() => {
      chartResizeFrame = 0
      handleResize()
    })
  }

  function bindChartResizeObserver() {
    chartResizeObserver?.disconnect()
    chartResizeObserver = null
    if (typeof ResizeObserver === 'undefined') return
    const elements = chartElements()
    if (!elements.length) return
    chartResizeObserver = new ResizeObserver(scheduleChartResize)
    elements.forEach((element) => chartResizeObserver?.observe(element))
  }

  function unbindChartResizeObserver() {
    chartResizeObserver?.disconnect()
    chartResizeObserver = null
    if (!chartResizeFrame) return
    cancelAnimationFrame(chartResizeFrame)
    chartResizeFrame = 0
  }

  function bindResizeListener() {
    window.removeEventListener('resize', handleResize)
    window.addEventListener('resize', handleResize)
    bindChartResizeObserver()
  }

  function unbindResizeListener() {
    window.removeEventListener('resize', handleResize)
    unbindChartResizeObserver()
  }

  function applyAnimatedOption(key: ChartKey, option: Record<string, unknown>, mode: RenderMode = 'refresh') {
    const chart = charts[key]
    if (!chart) return
    const isFirstRender = chartFirstRenderState.value[key]
    const activeMode: RenderMode = isFirstRender ? 'initial' : mode
    const profile = renderProfiles[activeMode]
    const optionWithAnimation = {
      ...option,
      animation: true,
      animationDuration: profile.duration,
      animationDurationUpdate: profile.updateDuration,
      animationEasing: 'cubicOut',
      animationEasingUpdate: 'cubicOut',
      animationDelay: profile.delayStep > 0 ? (idx: number) => Math.min(idx * profile.delayStep, 180) : 0,
      animationDelayUpdate: profile.delayStep > 0 ? (idx: number) => Math.min(idx * Math.max(4, Math.floor(profile.delayStep / 2)), 120) : 0,
    }
    const resetsSeries = activeMode === 'entry' || activeMode === 'range'
    if (resetsSeries) {
      chart.clear?.()
    }
    chart.setOption(optionWithAnimation, {
      notMerge: resetsSeries,
      lazyUpdate: profile.lazyUpdate,
      replaceMerge: ['series', 'xAxis', 'yAxis', 'legend', 'graphic', 'grid'],
    })
    chartFirstRenderState.value[key] = false
  }

  function initChart(
    ref: HTMLDivElement | null,
    key: ChartKey,
    updateFn: (mode?: RenderMode) => void
  ) {
    const echarts = (window as any).echarts as { init: (el: HTMLElement) => ChartInstance } | undefined
    if (!echarts || !ref) return
    charts[key] = echarts.init(ref)
    updateFn('initial')
  }

  function bootstrapCharts() {
    if (chartsBootstrapped.value || !pageRuntime.canRun.value) return
    initChart(trendChartRef.value, 'trend', updateTrendChart)
    initChart(modelChartRef.value, 'model', updateModelChart)
    initChart(responseTimeChartRef.value, 'responseTime', updateResponseTimeChart)
    initChart(modelResponseTimeChartRef.value, 'modelResponseTime', updateModelResponseTimeChart)
    chartsBootstrapped.value = true
    bindChartResizeObserver()
  }

  function resetChartFirstRenderState() {
    chartFirstRenderState.value = {
      trend: true,
      model: true,
      responseTime: true,
      modelResponseTime: true,
    }
  }

  function disposeCharts() {
    ;(Object.keys(charts) as ChartKey[]).forEach((key) => {
      charts[key]?.dispose()
      charts[key] = null
    })
    chartsBootstrapped.value = false
    resetChartFirstRenderState()
  }

  function clearChartBootstrapTimer() {
    pageRuntime.clearTimer(CHART_BOOTSTRAP_TIMER_KEY)
  }

  function cancelDashboardDataRequests() {
    dashboardRefreshEpoch += 1
    const controller = dashboardRefreshInFlight?.controller
    dashboardRefreshInFlight = null
    dashboardDataQuery.invalidate()
    controller?.abort()
  }

  function scheduleChartBootstrap(delayMs = 80) {
    if (chartsBootstrapped.value) return
    clearChartBootstrapTimer()
    pageRuntime.setTimer(CHART_BOOTSTRAP_TIMER_KEY, delayMs, () => {
      if (!pageRuntime.canRun.value) return
      requestAnimationFrame(() => {
        if (!pageRuntime.canRun.value) return
        requestAnimationFrame(() => {
          if (!pageRuntime.canRun.value) return
          bootstrapCharts()
        })
      })
    })
  }

  const dashboardPolling = useSerialVisibilityPolling({
    runtime: pageRuntime,
    key: DASHBOARD_POLL_TIMER_KEY,
    intervalMs: () => readDashboardRefreshIntervalSeconds() * 1000,
    action: async () => {
      await refreshDashboardData({ silent: true })
    },
  })

  let applyDefaultTimeRangeWhenShown = false
  let replayEntryAnimationWhenShown = false

  pageRuntime.onActivate(({ initial, visible }) => {
    if (!visible) {
      applyDefaultTimeRangeWhenShown = true
      replayEntryAnimationWhenShown = !initial
      return
    }
    applyDefaultTimeRangeWhenShown = false
    replayEntryAnimationWhenShown = false
    applyDashboardDefaultTimeRange()
    bindResizeListener()
    void reloadDashboardOnEnter({ replay: !initial })
  })

  pageRuntime.onDeactivate(() => {
    applyDefaultTimeRangeWhenShown = false
    replayEntryAnimationWhenShown = false
    dashboardPolling.stop()
    unbindResizeListener()
    dashboardEntrySeq += 1
    cancelDashboardDataRequests()
    clearChartBootstrapTimer()
  })

  pageRuntime.onHide(() => {
    dashboardPolling.stop()
    unbindResizeListener()
    dashboardEntrySeq += 1
    cancelDashboardDataRequests()
    clearChartBootstrapTimer()
  })

  pageRuntime.onShow(() => {
    const replay = replayEntryAnimationWhenShown
    replayEntryAnimationWhenShown = false
    if (applyDefaultTimeRangeWhenShown) {
      applyDefaultTimeRangeWhenShown = false
      applyDashboardDefaultTimeRange()
    }
    bindResizeListener()
    void reloadDashboardOnEnter({ replay })
  })

  onBeforeUnmount(() => {
    dashboardPolling.stop()
    unbindResizeListener()
    dashboardEntrySeq += 1
    cancelDashboardDataRequests()
    clearChartBootstrapTimer()
    disposeCharts()
  })

  function updateTrendChart(mode: RenderMode = 'refresh') {
    if (!charts.trend) return

    const theme = getLineChartTheme()
    const trendSeries = buildDashboardTrendSeries(chartData.value.trend, createLineSeries, {
      success: chartColors.primary,
      failure: chartColors.danger,
      switchAccount: chartColors.purple,
    })
    const hasSuccessRateData = chartData.value.trend.successRate.some((value) => value !== null)
    const useDemoData = import.meta.env.DEV && !hasSuccessRateData
    const labels = useDemoData
      ? resolveDemoLabels(chartData.value.trend.labels)
      : chartData.value.trend.labels
    const successRateValues = useDemoData
      ? resampleDemoValues(SUCCESS_RATE_DEMO_VALUES, labels.length)
      : chartData.value.trend.successRate
    const hasTrendData = chartData.value.trend.successRequests.some(value => value > 0)
      || chartData.value.trend.finalFailedRequests.some(value => value > 0)
      || chartData.value.trend.switchCount.some(value => value > 0)
      || hasSuccessRateData
    const successRateSeries = {
      ...createStraightAreaLineSeries('Success rate', successRateValues, chartColors.warning, 0.08),
      yAxisIndex: 1,
      symbolSize: 4,
      connectNulls: true,
    }

    applyAnimatedOption('trend', {
      ...theme,
      tooltip: {
        ...theme.tooltip,
        formatter: (params: unknown) => formatDashboardAxisTooltip(params, (value, item) => (
          item.seriesName === 'Success rate'
            ? `${value.toFixed(1)}%`
            : value.toLocaleString('zh-CN')
        )),
      },
      legend: {
        ...theme.legend,
        data: [...trendSeries.map(series => series.name), 'Success rate'],
      },
      grid: {
        ...theme.grid,
        top: 44,
        bottom: 32,
      },
      xAxis: {
        ...theme.xAxis,
        data: labels,
      },
      yAxis: [
        {
          ...theme.yAxis,
          minInterval: 1,
        },
        {
          ...theme.yAxis,
          position: 'right',
          min: 0,
          max: 100,
          axisLabel: {
            ...theme.yAxis.axisLabel,
            formatter: '{value}%',
          },
        },
      ],
      graphic: useDemoData || hasTrendData
        ? (useDemoData ? [demoChartGraphic()] : [])
        : [emptyChartGraphic('No requests to display for this time range.')],
      series: [...trendSeries, successRateSeries],
    }, mode)
  }

  function emptyChartGraphic(message: string) {
    return {
      type: 'text',
      left: 'center',
      top: 'middle',
      silent: true,
      style: {
        text: message,
        fill: '#737373',
        fontSize: 12,
      },
    }
  }

  function demoChartGraphic() {
    return {
      type: 'text',
      left: 12,
      top: 8,
      silent: true,
      style: {
        text: 'Demo data',
        fill: '#a3a3a3',
        fontSize: 11,
      },
    }
  }

  function updateModelChart(mode: RenderMode = 'refresh') {
    if (!charts.model) return

    const theme = getLineChartTheme()
    const modelNames = Object.keys(chartData.value.model.successRequests)
      .filter((modelName) => (
        chartData.value.model.successRequests[modelName] || []
      ).some((value) => Number(value || 0) > 0))
      .sort((left, right) => {
        const leftTotal = (chartData.value.model.successRequests[left] || [])
          .reduce((total, value) => total + Number(value || 0), 0)
        const rightTotal = (chartData.value.model.successRequests[right] || [])
          .reduce((total, value) => total + Number(value || 0), 0)
        return rightTotal - leftTotal || left.localeCompare(right)
      })
    const pointCount = chartData.value.model.labels.length
    const barMaxWidth = resolveDashboardBarMaxWidth(pointCount)
    const topSeriesIndexByPoint = Array.from({ length: pointCount }, (_, pointIndex) => {
      for (let seriesIndex = modelNames.length - 1; seriesIndex >= 0; seriesIndex -= 1) {
        const value = Number(
          chartData.value.model.successRequests[modelNames[seriesIndex]]?.[pointIndex] || 0,
        )
        if (value > 0) return seriesIndex
      }
      return -1
    })
    const series = modelNames.map((modelName, seriesIndex) => ({
      name: modelName,
      type: 'bar',
      stack: 'requests',
      barMaxWidth,
      data: (chartData.value.model.successRequests[modelName] || []).map((value, pointIndex) => ({
        value,
        itemStyle: {
          color: getModelColor(modelName),
          borderRadius: topSeriesIndexByPoint[pointIndex] === seriesIndex
            ? [4, 4, 0, 0]
            : [0, 0, 0, 0],
        },
      })),
    }))

    applyAnimatedOption('model', {
      ...theme,
      color: modelNames.map(modelName => getModelColor(modelName)),
      tooltip: {
        ...theme.tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: unknown) => formatDashboardAxisTooltip(
          params,
          (value) => value.toLocaleString('zh-CN'),
        ),
      },
      legend: {
        ...theme.legend,
        data: modelNames,
        top: 0,
        right: 0,
        type: 'scroll',
        pageIconSize: 10,
        pageTextStyle: { fontSize: 10 },
      },
      grid: {
        ...theme.grid,
        left: 34,
        right: 24,
        top: modelNames.length > 5 ? 56 : 48,
        bottom: 32,
      },
      xAxis: {
        ...theme.xAxis,
        data: chartData.value.model.labels,
        boundaryGap: true,
      },
      yAxis: {
        ...theme.yAxis,
        minInterval: 1,
      },
      graphic: modelNames.length ? [] : [emptyChartGraphic('No successful requests in this time range.')],
      series,
    }, mode)
  }

  function handleResize() {
    Object.values(charts).forEach((chart) => {
      chart?.resize()
    })
  }

  function formatStatNumber(value: unknown) {
    const number = Number(value || 0)
    if (!Number.isFinite(number)) return '0'
    return Math.max(0, Math.trunc(number)).toLocaleString('zh-CN')
  }

  function applyAccountStats(accounts: DashboardAccountStats) {
    stats.value[0].value = formatStatNumber(accounts.total)
    stats.value[1].value = formatStatNumber(accounts.active)
    stats.value[2].value = formatStatNumber(accounts.limited)
    stats.value[3].value = formatStatNumber(accounts.abnormal)
    stats.value[4].value = formatStatNumber(accounts.disabled)
    stats.value[5].value = formatStatNumber(accounts.total_quota)
    stats.value[5].meta = ''
  }

  function applyTrendRangeToChartData(range: DashboardRangeStats) {
    const trend = range.trend
    chartData.value.trend.labels = trend.labels
    chartData.value.trend.finalFailedRequests = trend.final_failed_requests
    chartData.value.trend.switchCount = trend.switch_count
    chartData.value.trend.successRequests = trend.success_requests
    chartData.value.trend.successRate = trend.success_rate
  }

  function applyResponseTimeRangeToChartData(range: DashboardRangeStats) {
    const trend = range.trend
    chartData.value.responseTime.labels = trend.labels
    chartData.value.responseTime.avgSuccessDurationMs = range.buckets.map(
      (bucket) => bucket.avg_success_duration_ms,
    )
  }

  function applyModelResponseTimeRangeToChartData(range: DashboardRangeStats) {
    const trend = range.trend
    chartData.value.modelResponseTime.labels = trend.labels
    chartData.value.modelResponseTime.modelAvgSuccessDurationMs = trend.model_avg_success_duration_ms
  }

  function applyModelRangeToChartData(range: DashboardRangeStats) {
    chartData.value.model.labels = range.trend.labels
    chartData.value.model.successRequests = range.trend.model_success_requests
  }

  function bindChartRange(
    timeRange: typeof modelTimeRange,
    applyRange: (range: DashboardRangeStats) => void,
    updateChart: (mode?: RenderMode) => void,
  ) {
    watch(timeRange, (nextRange) => {
      if (!pageRuntime.canRun.value || !dashboardSnapshot) return
      applyRange(dashboardSnapshot.ranges[nextRange])
      updateChart('range')
    })
  }

  bindChartRange(modelTimeRange, applyModelRangeToChartData, updateModelChart)
  bindChartRange(trendTimeRange, applyTrendRangeToChartData, updateTrendChart)
  bindChartRange(responseTimeTimeRange, applyResponseTimeRangeToChartData, updateResponseTimeChart)
  bindChartRange(
    modelResponseTimeTimeRange,
    applyModelResponseTimeRangeToChartData,
    updateModelResponseTimeChart,
  )

  function getDashboardRenderSignature(snapshot: DashboardResponse) {
    const accounts = snapshot.accounts
    return JSON.stringify({
      accounts: [
        accounts.total,
        accounts.active,
        accounts.limited,
        accounts.abnormal,
        accounts.disabled,
        accounts.total_quota,
      ],
      ranges: snapshot.meta.available_ranges.map((timeRange) => ({
        timeRange,
        trend: snapshot.ranges[timeRange].trend,
        totals: snapshot.ranges[timeRange].totals,
        switching: snapshot.ranges[timeRange].switching,
        buckets: snapshot.ranges[timeRange].buckets.map((bucket) => [
          bucket.start_at,
          bucket.total_calls,
          bucket.success_calls,
          bucket.final_failed_calls,
          bucket.success_rate,
          bucket.avg_success_duration_ms,
        ]),
      })),
    })
  }

  function applyDashboardSnapshot(snapshot: DashboardResponse) {
    const nextRenderSignature = getDashboardRenderSignature(snapshot)
    dashboardSnapshot = snapshot
    dashboardRanges.value = snapshot.ranges
    dashboardRuntime.value = snapshot.runtime
    dashboardOperations.value = snapshot.operations
    dashboardVersion.value = snapshot.version
    dashboardDataWarning.value = snapshot.metrics.status === 'degraded'
      ? 'Statistics have not been updated. Showing the most recent available snapshot.'
      : ''
    if (nextRenderSignature === dashboardRenderSignature) return false
    dashboardRenderSignature = nextRenderSignature
    applyAccountStats(snapshot.accounts)
    applyModelRangeToChartData(snapshot.ranges[modelTimeRange.value])
    applyTrendRangeToChartData(snapshot.ranges[trendTimeRange.value])
    applyResponseTimeRangeToChartData(snapshot.ranges[responseTimeTimeRange.value])
    applyModelResponseTimeRangeToChartData(snapshot.ranges[modelResponseTimeTimeRange.value])
    return true
  }

  function updatePrimaryCharts(mode: RenderMode = 'refresh') {
    updateTrendChart(mode)
    updateResponseTimeChart(mode)
    updateModelResponseTimeChart(mode)
  }

  function updateDashboardCharts(mode: RenderMode = 'refresh') {
    updatePrimaryCharts(mode)
    updateModelChart(mode)
  }

  async function refreshDashboardData(options: { silent?: boolean; replay?: boolean } = {}) {
    const epoch = dashboardRefreshEpoch

    if (dashboardRefreshInFlight?.epoch === epoch) {
      return dashboardRefreshInFlight.promise
    }

    if (epoch !== dashboardRefreshEpoch || !pageRuntime.canRun.value) return false

    const controller = new AbortController()
    let refreshPromise: Promise<boolean>
    refreshPromise = dashboardDataQuery.run(
      () => statsApi.overview(controller.signal),
      {
        apply: (snapshot) => {
          if (epoch !== dashboardRefreshEpoch) return
          const wasReady = dashboardDataReady.value
          const changed = applyDashboardSnapshot(snapshot)
          dashboardLoadError.value = ''
          dashboardDataReady.value = true
          const shouldReplay = Boolean(
            options.replay
            && wasReady
            && chartsBootstrapped.value
            && !prefersReducedDashboardMotion(),
          )
          if (shouldReplay) {
            activityAnimationEpoch.value += 1
          }
          if ((changed || shouldReplay) && wasReady && chartsBootstrapped.value) {
            updateDashboardCharts(shouldReplay ? 'entry' : 'refresh')
          }
          if (!wasReady || !chartsBootstrapped.value) {
            void nextTick().then(() => {
              if (epoch === dashboardRefreshEpoch && pageRuntime.canRun.value) {
                scheduleChartBootstrap(0)
              }
            })
          }
        },
        silentError: options.silent,
        silentLoading: options.silent,
      },
    ).then((snapshot) => {
      const refreshed = Boolean(snapshot)
      if (!refreshed && epoch === dashboardRefreshEpoch) {
        if (dashboardSnapshot) {
          dashboardDataWarning.value = 'Failed to refresh the latest statistics. Showing the most recent available snapshot.'
        } else if (!options.silent) {
          dashboardLoadError.value = dashboardQueryError.value || 'Dashboard failed to load'
        }
      }
      return refreshed
    }).finally(() => {
      if (dashboardRefreshInFlight?.promise === refreshPromise) {
        dashboardRefreshInFlight = null
      }
    })
    dashboardRefreshInFlight = { epoch, promise: refreshPromise, controller }
    return refreshPromise
  }
  async function reloadDashboardOnEnter(options: { replay?: boolean } = {}) {
    const entrySeq = ++dashboardEntrySeq
    dashboardPolling.stop()
    cancelDashboardDataRequests()
    const hasSnapshot = dashboardSnapshot !== null
    if (!hasSnapshot) {
      dashboardDataReady.value = false
      dashboardLoadError.value = ''
      dashboardDataWarning.value = ''
    }
    await nextTick()
    if (entrySeq !== dashboardEntrySeq) return
    if (hasSnapshot) {
      dashboardDataReady.value = true
      scheduleChartBootstrap(0)
      requestAnimationFrame(handleResize)
    }
    dashboardPolling.start()
    await refreshDashboardData({
      silent: hasSnapshot,
      replay: hasSnapshot && options.replay,
    })
  }

  function retryDashboard() {
    if (!pageRuntime.canRun.value) return
    void reloadDashboardOnEnter()
  }

  function createDurationChartOption(
    labels: string[],
    series: Array<Record<string, unknown>>,
    legendData: string[],
    graphic: Array<Record<string, unknown>>,
  ) {
    const theme = getLineChartTheme()
    return {
      ...theme,
      color: series.map((item) => item.itemStyle && typeof item.itemStyle === 'object'
        ? (item.itemStyle as { color?: string }).color
        : undefined).filter(Boolean),
      tooltip: {
        ...theme.tooltip,
        trigger: 'axis',
        formatter: (params: unknown) => formatDashboardAxisTooltip(
          params,
          (value) => `${value}s`,
        ),
      },
      legend: {
        ...theme.legend,
        data: legendData,
        top: 0,
        right: 0,
        type: 'scroll',
        pageIconSize: 10,
        pageTextStyle: {
          fontSize: 10,
        },
      },
      grid: {
        ...theme.grid,
        top: legendData.length > 5 ? 56 : legendData.length ? 48 : 32,
        bottom: 32,
      },
      xAxis: {
        ...theme.xAxis,
        data: labels,
      },
      yAxis: {
        ...theme.yAxis,
        axisLabel: {
          ...theme.yAxis.axisLabel,
          formatter: '{value}s',
        },
      },
      graphic,
      series,
    }
  }

  function durationSeconds(values: Array<number | null>) {
    return values.map((value) => value === null ? null : Number((value / 1000).toFixed(2)))
  }

  function updateResponseTimeChart(mode: RenderMode = 'refresh') {
    if (!charts.responseTime) return

    const realValues = chartData.value.responseTime.avgSuccessDurationMs
    const hasData = realValues.some((value) => value !== null && Number(value) >= 0)
    const useDemoData = import.meta.env.DEV && !hasData
    const labels = useDemoData
      ? resolveDemoLabels(chartData.value.responseTime.labels)
      : chartData.value.responseTime.labels
    const values = useDemoData
      ? resampleDemoValues(SUCCESS_DURATION_DEMO_SECONDS, labels.length)
      : durationSeconds(realValues)
    const series = [
      createStraightAreaLineSeries(
        'Average duration',
        values,
        chartColors.primary,
        0.16,
      ),
    ]

    applyAnimatedOption('responseTime', createDurationChartOption(
      labels,
      hasData || useDemoData ? series : [],
      hasData || useDemoData ? ['Average duration'] : [],
      useDemoData
        ? [demoChartGraphic()]
        : (hasData ? [] : [emptyChartGraphic('No successful response times in this range.')]),
    ), mode)
  }

  function updateModelResponseTimeChart(mode: RenderMode = 'refresh') {
    if (!charts.modelResponseTime) return

    const responseSeriesByModel = chartData.value.modelResponseTime.modelAvgSuccessDurationMs
    const realModelNames = Object.keys(responseSeriesByModel)
      .filter((modelName) => (responseSeriesByModel[modelName] || []).some((value) => Number(value || 0) > 0))
    const useDemoData = import.meta.env.DEV && realModelNames.length === 0
    const modelNames = useDemoData ? ['Demo model'] : realModelNames
    const labels = useDemoData
      ? resolveDemoLabels(chartData.value.modelResponseTime.labels)
      : chartData.value.modelResponseTime.labels

    const series = modelNames.map((modelName) => {
      const color = getModelColor(modelName)
      const seconds = useDemoData
        ? resampleDemoValues(SUCCESS_DURATION_DEMO_SECONDS, labels.length)
        : (responseSeriesByModel[modelName] || []).map((ms) => (
            ms === null ? null : Number((ms / 1000).toFixed(2))
          ))
      return createStraightAreaLineSeries(modelName, seconds, color, 0.16)
    })

    applyAnimatedOption('modelResponseTime', createDurationChartOption(
      labels,
      series,
      modelNames,
      useDemoData
        ? [demoChartGraphic()]
        : (modelNames.length ? [] : [emptyChartGraphic('No model response times in this range.')]),
    ), mode)
  }

  return {
    stats,
    dashboardRanges,
    dashboardRuntime,
    dashboardOperations,
    dashboardDataReady,
    dashboardLoadError,
    retryDashboard,
    dashboardDataWarning,
    dashboardVersion,
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
  }
}
