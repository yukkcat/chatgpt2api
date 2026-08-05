import { nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { statsApi } from '@/api/stats'
import type {
  DashboardAccountStats,
  DashboardBucket,
  DashboardRangeStats,
  DashboardResponse,
} from '@/types/api'
import { usePageQuery, useVisibilityPolling } from '@/composables/usePageQuery'
import { usePageRuntime } from '@/composables/usePageRuntime'
import {
  getLineChartTheme,
  createLineSeries,
  chartColors,
  getModelColor,
} from '@/lib/chartTheme'
import { DEFAULT_DASHBOARD_TIME_RANGE, type DashboardTimeRange } from '@/lib/timeRanges'
import { buildDashboardTrendSeries } from '@/views/dashboard/dashboardTrendSeries'


export function useDashboardPage() {
  type ChartInstance = {
    setOption: (
      option: unknown,
      opts?: boolean | { notMerge?: boolean; lazyUpdate?: boolean; replaceMerge?: string[] }
    ) => void
    resize: () => void
    dispose: () => void
    clear?: () => void
    off?: (eventName: string) => void
    on?: (eventName: string, handler: (params: any) => void) => void
    dispatchAction?: (payload: Record<string, unknown>) => void
  }
  type RenderMode = 'initial' | 'range' | 'refresh'
  const pageRuntime = usePageRuntime('dashboard')
  const DASHBOARD_DATA_REQUEST_KEY = 'dashboard:data'
  const CHART_BOOTSTRAP_TIMER_KEY = 'dashboard:chart-bootstrap'
  const DASHBOARD_POLL_TIMER_KEY = 'dashboard:poll'
  const DASHBOARD_POLL_INTERVAL_MS = 5_000
  const dashboardQueryError = ref('')
  const dashboardDataQuery = usePageQuery({
    runtime: pageRuntime,
    key: DASHBOARD_DATA_REQUEST_KEY,
    error: dashboardQueryError,
    errorMessage: '概览加载失败',
  })
  const dashboardLoadError = ref('')
  const dashboardDataWarning = ref('')

  const modelTimeRange = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)
  const trendTimeRange = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)
  const successRateTimeRange = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)
  const responseTimeTimeRange = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)
  const detailTimeRange = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)

  function createDefaultStats() {
    return [
      {
        label: '账号总数',
        value: '0',
        meta: '',
        icon: 'lucide:users',
        iconBg: 'bg-sky-100',
        iconColor: 'text-sky-600'
      },
      {
        label: '正常账号',
        value: '0',
        meta: '',
        icon: 'lucide:check-circle',
        iconBg: 'bg-emerald-100',
        iconColor: 'text-emerald-600'
      },
      {
        label: '限流账号',
        value: '0',
        meta: '',
        icon: 'lucide:clock',
        iconBg: 'bg-amber-100',
        iconColor: 'text-amber-600'
      },
      {
        label: '异常账号',
        value: '0',
        meta: '',
        icon: 'lucide:alert-circle',
        iconBg: 'bg-rose-100',
        iconColor: 'text-rose-600'
      },
      {
        label: '禁用账号',
        value: '0',
        meta: '',
        icon: 'lucide:ban',
        iconBg: 'bg-slate-100',
        iconColor: 'text-slate-600'
      },
      {
        label: '剩余额度',
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

  // 每个图表独立的数据状态
  function createEmptyChartData() {
    return {
      trend: {
        labels: [] as string[],
        finalFailedRequests: [] as number[],
        switchCount: [] as number[],
        successRequests: [] as number[],
      },
      successRate: {
        labels: [] as string[],
        values: [] as Array<number | null>,
      },
      model: {
        labels: [] as string[],
        requests: {} as Record<string, number[]>,
      },
      responseTime: {
        labels: [] as string[],
        modelAvgSuccessDurationMs: {} as Record<string, Array<number | null>>,
      },
      detail: {
        labels: [] as string[],
        buckets: [] as DashboardBucket[],
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
  const successRateChartRef = ref<HTMLDivElement | null>(null)
  const responseTimeChartRef = ref<HTMLDivElement | null>(null)
  const detailChartRef = ref<HTMLDivElement | null>(null)

  const charts = {
    trend: null as ChartInstance | null,
    model: null as ChartInstance | null,
    successRate: null as ChartInstance | null,
    responseTime: null as ChartInstance | null,
    detail: null as ChartInstance | null,
  }

  type ChartKey = keyof typeof charts
  const renderProfiles: Record<RenderMode, {
    duration: number
    updateDuration: number
    delayStep: number
    lazyUpdate: boolean
  }> = {
    initial: { duration: 860, updateDuration: 620, delayStep: 14, lazyUpdate: false },
    range: { duration: 560, updateDuration: 460, delayStep: 8, lazyUpdate: false },
    refresh: { duration: 260, updateDuration: 220, delayStep: 0, lazyUpdate: true },
  }
  const chartFirstRenderState = ref<Record<ChartKey, boolean>>({
    trend: true,
    model: true,
    successRate: true,
    responseTime: true,
    detail: true,
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
      successRateChartRef.value,
      responseTimeChartRef.value,
      detailChartRef.value,
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
    if (activeMode === 'range') {
      chart.clear?.()
    }
    chart.setOption(optionWithAnimation, {
      notMerge: activeMode === 'range',
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
    initChart(successRateChartRef.value, 'successRate', updateSuccessRateChart)
    initChart(responseTimeChartRef.value, 'responseTime', updateResponseTimeChart)
    initChart(detailChartRef.value, 'detail', updateDetailChart)
    chartsBootstrapped.value = true
    bindChartResizeObserver()
  }

  function resetChartFirstRenderState() {
    chartFirstRenderState.value = {
      trend: true,
      model: true,
      successRate: true,
      responseTime: true,
      detail: true,
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

  const dashboardPolling = useVisibilityPolling({
    runtime: pageRuntime,
    key: DASHBOARD_POLL_TIMER_KEY,
    intervalMs: DASHBOARD_POLL_INTERVAL_MS,
    action: async () => {
      await refreshDashboardData({ silent: true })
    },
  })

  pageRuntime.onActivate(({ visible }) => {
    if (!visible) return
    bindResizeListener()
    void reloadDashboardOnEnter()
  })

  pageRuntime.onDeactivate(() => {
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
    bindResizeListener()
    void reloadDashboardOnEnter()
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
    const series = buildDashboardTrendSeries(chartData.value.trend, createLineSeries, {
      success: chartColors.primary,
      failure: chartColors.danger,
      switchAccount: chartColors.purple,
    })

    applyAnimatedOption('trend', {
      ...theme,
      xAxis: {
        ...theme.xAxis,
        data: chartData.value.trend.labels,
      },
      series,
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

  function updateModelChart(mode: RenderMode = 'refresh') {
    if (!charts.model) return

    const theme = getLineChartTheme()
    const modelNames = Object.keys(chartData.value.model.requests)
      .filter((modelName) => (
        chartData.value.model.requests[modelName] || []
      ).some((value) => Number(value || 0) > 0))
      .sort((left, right) => {
        const leftTotal = (chartData.value.model.requests[left] || [])
          .reduce((total, value) => total + Number(value || 0), 0)
        const rightTotal = (chartData.value.model.requests[right] || [])
          .reduce((total, value) => total + Number(value || 0), 0)
        return rightTotal - leftTotal || left.localeCompare(right)
      })
    const pointCount = chartData.value.model.labels.length
    const topSeriesIndexByPoint = Array.from({ length: pointCount }, (_, pointIndex) => {
      for (let seriesIndex = modelNames.length - 1; seriesIndex >= 0; seriesIndex -= 1) {
        const value = Number(
          chartData.value.model.requests[modelNames[seriesIndex]]?.[pointIndex] || 0,
        )
        if (value > 0) return seriesIndex
      }
      return -1
    })
    const series = modelNames.map((modelName, seriesIndex) => ({
      name: modelName,
      type: 'bar',
      stack: 'requests',
      barMaxWidth: 48,
      data: (chartData.value.model.requests[modelName] || []).map((value, pointIndex) => ({
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
      graphic: modelNames.length ? [] : [emptyChartGraphic('当前范围内暂无模型请求')],
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
  }

  function applySuccessRateRangeToChartData(range: DashboardRangeStats) {
    const trend = range.trend
    chartData.value.successRate.labels = trend.labels
    chartData.value.successRate.values = trend.success_rate
  }

  function applyResponseTimeRangeToChartData(range: DashboardRangeStats) {
    const trend = range.trend
    chartData.value.responseTime.labels = trend.labels
    chartData.value.responseTime.modelAvgSuccessDurationMs = trend.model_avg_success_duration_ms
  }

  function applyModelRangeToChartData(range: DashboardRangeStats) {
    chartData.value.model.labels = range.trend.labels
    chartData.value.model.requests = range.trend.model_requests
  }

  function applyDetailRangeToChartData(range: DashboardRangeStats) {
    chartData.value.detail.labels = range.trend.labels
    chartData.value.detail.buckets = range.buckets
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
  bindChartRange(successRateTimeRange, applySuccessRateRangeToChartData, updateSuccessRateChart)
  bindChartRange(responseTimeTimeRange, applyResponseTimeRangeToChartData, updateResponseTimeChart)
  bindChartRange(detailTimeRange, applyDetailRangeToChartData, updateDetailChart)

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
        models: snapshot.ranges[timeRange].models,
        trend: snapshot.ranges[timeRange].trend,
        totals: snapshot.ranges[timeRange].totals,
        switching: snapshot.ranges[timeRange].switching,
        buckets: snapshot.ranges[timeRange].buckets,
      })),
    })
  }

  function applyDashboardSnapshot(snapshot: DashboardResponse) {
    const nextRenderSignature = getDashboardRenderSignature(snapshot)
    dashboardSnapshot = snapshot
    dashboardRanges.value = snapshot.ranges
    dashboardDataWarning.value = snapshot.metrics.status === 'degraded'
      ? '统计数据暂未更新，当前展示最近一次可用快照。'
      : ''
    if (nextRenderSignature === dashboardRenderSignature) return false
    dashboardRenderSignature = nextRenderSignature
    applyAccountStats(snapshot.accounts)
    applyModelRangeToChartData(snapshot.ranges[modelTimeRange.value])
    applyTrendRangeToChartData(snapshot.ranges[trendTimeRange.value])
    applySuccessRateRangeToChartData(snapshot.ranges[successRateTimeRange.value])
    applyResponseTimeRangeToChartData(snapshot.ranges[responseTimeTimeRange.value])
    applyDetailRangeToChartData(snapshot.ranges[detailTimeRange.value])
    return true
  }

  function updatePrimaryCharts(mode: RenderMode = 'refresh') {
    updateTrendChart(mode)
    updateSuccessRateChart(mode)
    updateResponseTimeChart(mode)
    updateDetailChart(mode)
  }

  function updateDashboardCharts(mode: RenderMode = 'refresh') {
    updatePrimaryCharts(mode)
    updateModelChart(mode)
  }

  async function refreshDashboardData(options: { silent?: boolean } = {}) {
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
          if (changed && wasReady && chartsBootstrapped.value) {
            updateDashboardCharts()
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
          dashboardDataWarning.value = '最新统计刷新失败，当前展示最近一次可用快照。'
        } else if (!options.silent) {
          dashboardLoadError.value = dashboardQueryError.value || '概览加载失败'
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
  async function reloadDashboardOnEnter() {
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
    await refreshDashboardData({ silent: hasSnapshot })
  }

  function retryDashboard() {
    if (!pageRuntime.canRun.value) return
    void reloadDashboardOnEnter()
  }

  function updateSuccessRateChart(mode: RenderMode = 'refresh') {
    if (!charts.successRate) return

    const theme = getLineChartTheme()
    const hasData = chartData.value.successRate.values.some((value) => value !== null)
    applyAnimatedOption('successRate', {
      ...theme,
      tooltip: {
        ...theme.tooltip,
        trigger: 'axis',
        formatter: (params: any) => {
          if (!params || params.length === 0) return ''
          const param = params[0]
          const value = typeof param.value === 'number' && Number.isFinite(param.value)
            ? `${param.value}%`
            : '--'
          return `<div style="font-weight: 600; margin-bottom: 4px;">${param.axisValue}</div>
            <div style="display: flex; justify-content: space-between; gap: 16px; align-items: center;">
              <span>${param.marker} ${param.seriesName}</span>
              <span style="font-weight: 600;">${value}</span>
            </div>`
        },
      },
      grid: {
        ...theme.grid,
        top: 32,
        bottom: 32,
      },
      xAxis: {
        ...theme.xAxis,
        data: chartData.value.successRate.labels,
      },
      yAxis: {
        ...theme.yAxis,
        max: 100,
        axisLabel: {
          ...theme.yAxis.axisLabel,
          formatter: '{value}%',
        },
      },
      graphic: hasData ? [] : [emptyChartGraphic('当前范围内暂无可统计请求')],
      series: [
        {
          name: '成功率',
          type: 'line',
          data: chartData.value.successRate.values,
          smooth: true,
          showSymbol: true,
          connectNulls: true,
          symbolSize: 6,
          lineStyle: {
            width: 3,
          },
          areaStyle: {
            opacity: 0.3,
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: chartColors.success },
                { offset: 1, color: 'rgba(16, 185, 129, 0.1)' },
              ],
            },
          },
          itemStyle: {
            color: chartColors.success,
          },
        },
      ],
    }, mode)
  }

  function updateResponseTimeChart(mode: RenderMode = 'refresh') {
    if (!charts.responseTime) return

    const theme = getLineChartTheme()
    const responseSeriesByModel = chartData.value.responseTime.modelAvgSuccessDurationMs
    const modelNames = Object.keys(responseSeriesByModel)
      .filter((modelName) => (responseSeriesByModel[modelName] || []).some((value) => Number(value || 0) > 0))

    if (modelNames.length === 0) {
      applyAnimatedOption('responseTime', {
        ...theme,
        grid: {
          ...theme.grid,
          top: 32,
          bottom: 32,
        },
        xAxis: {
          ...theme.xAxis,
          data: chartData.value.responseTime.labels,
        },
        yAxis: {
          ...theme.yAxis,
          axisLabel: {
            ...theme.yAxis.axisLabel,
            formatter: '{value}s',
          },
        },
        graphic: [emptyChartGraphic('当前范围内暂无成功耗时')],
        series: [],
      }, mode)
      return
    }

    const series = modelNames.map((modelName) => {
      const color = getModelColor(modelName)
      const seconds = (responseSeriesByModel[modelName] || []).map((ms) => (
        ms === null ? null : Number((ms / 1000).toFixed(2))
      ))
      return {
        ...createLineSeries(modelName, seconds, color, {
          smooth: true,
          showSymbol: true,
          areaOpacity: 0.15,
          zIndex: 2,
        }),
        connectNulls: true,
        symbolSize: 6,
      }
    })

    applyAnimatedOption('responseTime', {
      ...theme,
      color: modelNames.map((modelName) => getModelColor(modelName)),
      tooltip: {
        ...theme.tooltip,
        trigger: 'axis',
        formatter: (params: any) => {
          if (!params || params.length === 0) return ''
          let result = `<div style="font-weight: 600; margin-bottom: 4px;">${params[0].axisValue}</div>`
          params.forEach((item: any) => {
            if (typeof item.value !== 'number' || !Number.isFinite(item.value)) return
            result += `<div style="display: flex; justify-content: space-between; gap: 16px; align-items: center;">
              <span>${item.marker} ${item.seriesName}</span>
              <span style="font-weight: 600;">${item.value}s</span>
            </div>`
          })
          return result
        },
      },
      legend: {
        ...theme.legend,
        data: modelNames,
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
        top: modelNames.length > 5 ? 56 : 48,
        bottom: 32,
      },
      xAxis: {
        ...theme.xAxis,
        data: chartData.value.responseTime.labels,
      },
      yAxis: {
        ...theme.yAxis,
        axisLabel: {
          ...theme.yAxis.axisLabel,
          formatter: '{value}s',
        },
      },
      graphic: [],
      series,
    }, mode)
  }

  function updateDetailChart(mode: RenderMode = 'refresh') {
    if (!charts.detail) return

    const theme = getLineChartTheme()
    const buckets = chartData.value.detail.buckets
    const labels = chartData.value.detail.labels
    const hasData = buckets.some((bucket) => (
      bucket.total_calls > 0 || bucket.switch_count > 0 || bucket.switch_recovered > 0
    ))
    const durationSeconds = (value: number | null) => (
      value === null ? null : Number((value / 1_000).toFixed(2))
    )
    const formatDuration = (value: number | null) => {
      if (value === null) return '--'
      if (value < 1_000) return `${Math.round(value)}ms`
      if (value < 60_000) return `${(value / 1_000).toFixed(1)}s`
      return `${(value / 60_000).toFixed(1)}m`
    }
    const formatPercent = (value: number | null) => (
      value === null ? '--' : `${value.toFixed(1)}%`
    )

    applyAnimatedOption('detail', {
      ...theme,
      tooltip: {
        ...theme.tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any[]) => {
          const dataIndex = params?.[0]?.dataIndex
          const bucket = Number.isInteger(dataIndex) ? buckets[dataIndex] : null
          if (!bucket) return ''
          return `<div style="font-weight:600;margin-bottom:6px">${bucket.label}</div>
            <div style="display:grid;grid-template-columns:auto auto;gap:3px 18px">
              <span>调用</span><strong>${bucket.total_calls}</strong>
              <span>成功 / 最终失败</span><strong>${bucket.success_calls} / ${bucket.final_failed_calls}</strong>
              <span>成功率</span><strong>${formatPercent(bucket.success_rate)}</strong>
              <span>平均耗时 / P95</span><strong>${formatDuration(bucket.avg_success_duration_ms)} / ${formatDuration(bucket.p95_success_duration_ms)}</strong>
              <span>账号切换 / 恢复</span><strong>${bucket.switch_count} / ${bucket.switch_recovered}</strong>
              <span>切换恢复率</span><strong>${formatPercent(bucket.switch_recovery_rate)}</strong>
            </div>`
        },
      },
      legend: {
        ...theme.legend,
        data: ['成功', '最终失败', '平均耗时', 'P95', '账号切换', '切换恢复'],
        top: 0,
        right: 0,
        type: 'scroll',
      },
      grid: {
        left: 46,
        right: 52,
        top: 52,
        bottom: 38,
      },
      xAxis: {
        ...theme.xAxis,
        type: 'category',
        data: labels,
        boundaryGap: true,
        axisTick: { show: false },
      },
      yAxis: [
        {
          ...theme.yAxis,
          type: 'value',
          minInterval: 1,
        },
        {
          ...theme.yAxis,
          type: 'value',
          position: 'right',
          axisLabel: {
            ...theme.yAxis.axisLabel,
            formatter: '{value}s',
          },
        },
      ],
      graphic: hasData ? [] : [emptyChartGraphic('当前范围内暂无调用明细')],
      series: [
        {
          name: '成功',
          type: 'bar',
          stack: 'result',
          barMaxWidth: 40,
          data: buckets.map((bucket) => bucket.success_calls),
          itemStyle: { color: chartColors.success },
        },
        {
          name: '最终失败',
          type: 'bar',
          stack: 'result',
          barMaxWidth: 40,
          data: buckets.map((bucket) => bucket.final_failed_calls),
          itemStyle: { color: chartColors.danger, borderRadius: [4, 4, 0, 0] },
        },
        {
          ...createLineSeries(
            '平均耗时',
            buckets.map((bucket) => durationSeconds(bucket.avg_success_duration_ms)),
            chartColors.primary,
            { areaOpacity: 0.12, zIndex: 2 },
          ),
          yAxisIndex: 1,
          connectNulls: true,
        },
        {
          ...createLineSeries(
            'P95',
            buckets.map((bucket) => durationSeconds(bucket.p95_success_duration_ms)),
            chartColors.warning,
            { areaOpacity: 0, lineStyle: { type: 'dashed', width: 2 }, zIndex: 3 },
          ),
          yAxisIndex: 1,
          connectNulls: true,
        },
        {
          ...createLineSeries(
            '账号切换',
            buckets.map((bucket) => bucket.switch_count),
            chartColors.purple,
            { areaOpacity: 0, lineStyle: { type: 'dashed', width: 2 }, zIndex: 4 },
          ),
        },
        {
          ...createLineSeries(
            '切换恢复',
            buckets.map((bucket) => bucket.switch_recovered),
            chartColors.info,
            { areaOpacity: 0, lineStyle: { type: 'dotted', width: 2 }, zIndex: 5 },
          ),
        },
      ],
    }, mode)
  }

  return {
    stats,
    dashboardRanges,
    dashboardDataReady,
    dashboardLoadError,
    retryDashboard,
    dashboardDataWarning,
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
  }
}
