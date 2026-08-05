import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { statsApi } from '@/api/stats'
import type { DashboardAccountStats, DashboardRangeStats, DashboardResponse } from '@/types/api'
import { usePageQuery, useVisibilityPolling } from '@/composables/usePageQuery'
import { usePageRuntime } from '@/composables/usePageRuntime'
import {
  getLineChartTheme,
  getPieChartTheme,
  createLineSeries,
  createPieDataItem,
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
  type ChartType = 'hourlyRequests' | 'trend' | 'successRate' | 'model' | 'modelRank' | 'responseTime'
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

  // 每个图表独立的时间范围
  const timeRangeHourlyRequests = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)
  const timeRangeTrend = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)
  const timeRangeSuccessRate = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)
  const timeRangeModel = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)
  const timeRangeModelRank = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)
  const timeRangeResponseTime = ref<DashboardTimeRange>(DEFAULT_DASHBOARD_TIME_RANGE)

  // 创建图表监听器的工厂函数
  function createChartWatcher(chartType: ChartType, updateFn: (mode?: RenderMode) => void) {
    return (newVal: DashboardTimeRange) => {
      if (!pageRuntime.canRun.value || !dashboardSnapshot) return
      applyRangeToChartData(chartType, dashboardSnapshot.ranges[newVal])
      updateFn('range')
      void refreshDashboardData({ silent: true })
    }
  }

  // 监听各图表时间范围变化 - 只更新对应图表
  watch(timeRangeHourlyRequests, createChartWatcher('hourlyRequests', updateHourlyRequestsChart))
  watch(timeRangeTrend, createChartWatcher('trend', updateTrendChart))
  watch(timeRangeSuccessRate, createChartWatcher('successRate', updateSuccessRateChart))
  watch(timeRangeModel, createChartWatcher('model', updateModelChart))
  watch(timeRangeModelRank, createChartWatcher('modelRank', updateModelRankChart))
  watch(timeRangeResponseTime, createChartWatcher('responseTime', updateResponseTimeChart))

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

  // 每个图表独立的数据状态
  function createEmptyChartData() {
    return {
      hourlyRequests: {
        labels: [] as string[],
        modelRequests: {} as Record<string, number[]>,
      },
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
        models: [] as DashboardRangeStats['models'],
      },
      modelRank: {
        models: [] as DashboardRangeStats['models'],
      },
      responseTime: {
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
  const successRateChartRef = ref<HTMLDivElement | null>(null)
  const hourlyRequestsChartRef = ref<HTMLDivElement | null>(null)
  const modelRankChartRef = ref<HTMLDivElement | null>(null)
  const responseTimeChartRef = ref<HTMLDivElement | null>(null)

  const charts = {
    trend: null as ChartInstance | null,
    model: null as ChartInstance | null,
    successRate: null as ChartInstance | null,
    hourlyRequests: null as ChartInstance | null,
    modelRank: null as ChartInstance | null,
    responseTime: null as ChartInstance | null,
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
    hourlyRequests: true,
    modelRank: true,
    responseTime: true,
  })
  const chartsBootstrapped = ref(false)
  const dashboardDataReady = ref(false)
  let dashboardEntrySeq = 0
  const modelLayoutIsMobile = ref<boolean | null>(null)
  let chartResizeObserver: ResizeObserver | null = null
  let chartResizeFrame = 0

  function chartElements() {
    return [
      trendChartRef.value,
      modelChartRef.value,
      successRateChartRef.value,
      hourlyRequestsChartRef.value,
      modelRankChartRef.value,
      responseTimeChartRef.value,
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
      replaceMerge: ['series', 'xAxis', 'yAxis', 'legend'],
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
    initChart(hourlyRequestsChartRef.value, 'hourlyRequests', updateHourlyRequestsChart)
    initChart(modelRankChartRef.value, 'modelRank', updateModelRankChart)
    initChart(responseTimeChartRef.value, 'responseTime', updateResponseTimeChart)
    chartsBootstrapped.value = true
    bindChartResizeObserver()
  }

  function resetChartFirstRenderState() {
    chartFirstRenderState.value = {
      trend: true,
      model: true,
      successRate: true,
      hourlyRequests: true,
      modelRank: true,
      responseTime: true,
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
  function getModelTotals() {
    return chartData.value.model.models
      .filter(model => model.success_calls > 0)
      .map(model => ({
        model: model.name,
        data: createPieDataItem(model.name, model.success_calls, getModelColor(model.name)),
        total: model.success_calls,
      }))
  }

  function updateModelChart(mode: RenderMode = 'refresh') {
    if (!charts.model) return

    const isMobile = window.innerWidth < 768
    modelLayoutIsMobile.value = isMobile
    const theme = getPieChartTheme(isMobile)
    const modelData = getModelTotals().map(item => item.data)
    const modelColors = modelData.map(item => String(item?.itemStyle?.color || getModelColor(String(item?.name || ''))))

    applyAnimatedOption('model', {
      ...theme,
      color: modelColors,
      tooltip: {
        ...theme.tooltip,
        formatter: (params: { name: string; value: number; percent: number }) =>
          `${params.name}: ${params.value} 次 (${params.percent}%)`,
      },
      legend: {
        ...theme.legend,
        data: modelData.map(item => item.name),
      },
      series: [
        {
          ...theme.series,
          center: ['50%', '50%'],
          data: modelData,
        },
      ],
    }, mode)
  }

  function handleResize() {
    Object.entries(charts).forEach(([key, chart]) => {
      if (chart) {
        if (key === 'model') {
          const nowMobile = window.innerWidth < 768
          if (modelLayoutIsMobile.value !== nowMobile) {
            updateModelChart()
          } else {
            chart.resize()
          }
        } else {
          chart.resize()
        }
      }
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

  function applyRangeToChartData(chartType: ChartType, range: DashboardRangeStats) {
    const trend = range.trend
    switch (chartType) {
      case 'hourlyRequests':
        chartData.value.hourlyRequests.labels = trend.labels
        chartData.value.hourlyRequests.modelRequests = trend.model_success_requests
        break
      case 'trend':
        chartData.value.trend.labels = trend.labels
        chartData.value.trend.finalFailedRequests = trend.final_failed_requests
        chartData.value.trend.switchCount = trend.switch_count
        chartData.value.trend.successRequests = trend.success_requests
        break
      case 'successRate':
        chartData.value.successRate.labels = trend.labels
        chartData.value.successRate.values = trend.success_rate
        break
      case 'model':
        chartData.value.model.models = range.models
        break
      case 'modelRank':
        chartData.value.modelRank.models = range.models
        break
      case 'responseTime':
        chartData.value.responseTime.labels = trend.labels
        chartData.value.responseTime.modelAvgSuccessDurationMs = trend.model_avg_success_duration_ms
        break
    }
  }

  function getDashboardChartRanges(): Record<ChartType, DashboardTimeRange> {
    return {
      hourlyRequests: timeRangeHourlyRequests.value,
      trend: timeRangeTrend.value,
      successRate: timeRangeSuccessRate.value,
      model: timeRangeModel.value,
      modelRank: timeRangeModelRank.value,
      responseTime: timeRangeResponseTime.value,
    }
  }

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
      })),
    })
  }

  function applyDashboardSnapshot(snapshot: DashboardResponse) {
    const nextRenderSignature = getDashboardRenderSignature(snapshot)
    dashboardSnapshot = snapshot
    dashboardDataWarning.value = snapshot.metrics.status === 'degraded'
      ? '统计数据暂未更新，当前展示最近一次可用快照。'
      : ''
    if (nextRenderSignature === dashboardRenderSignature) return false
    dashboardRenderSignature = nextRenderSignature
    applyAccountStats(snapshot.accounts)
    const chartRanges = getDashboardChartRanges()
    ;(Object.keys(chartRanges) as ChartType[]).forEach((chartType) => {
      applyRangeToChartData(chartType, snapshot.ranges[chartRanges[chartType]])
    })
    return true
  }

  function updateDashboardCharts() {
    updateHourlyRequestsChart('refresh')
    updateTrendChart('refresh')
    updateSuccessRateChart('refresh')
    updateResponseTimeChart('refresh')
    updateModelChart('refresh')
    updateModelRankChart('refresh')
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
      series: [
        {
          name: '成功率',
          type: 'line',
          data: chartData.value.successRate.values,
          smooth: true,
          showSymbol: false,
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

  function updateHourlyRequestsChart(mode: RenderMode = 'refresh') {
    if (!charts.hourlyRequests) return

    const theme = getLineChartTheme()
    const modelNames = Object.keys(chartData.value.hourlyRequests.modelRequests)
      .filter((modelName) => (
        chartData.value.hourlyRequests.modelRequests[modelName] || []
      ).some((value) => Number(value || 0) > 0))

    if (modelNames.length === 0) {
      applyAnimatedOption('hourlyRequests', {
        ...theme,
        grid: {
          ...theme.grid,
          left: 34,
          right: 24,
          top: 32,
          bottom: 32,
        },
        xAxis: {
          ...theme.xAxis,
          data: chartData.value.hourlyRequests.labels,
          boundaryGap: true,
        },
        yAxis: {
          ...theme.yAxis,
        },
        series: [
          {
            name: '总请求',
            type: 'bar',
            data: [],
            barWidth: '60%',
            itemStyle: {
              color: chartColors.primary,
              borderRadius: [4, 4, 0, 0],
            },
          },
        ],
      }, mode)
      return
    }

    const pointCount = chartData.value.hourlyRequests.labels.length
    const topSeriesIndexByPoint = Array.from({ length: pointCount }, (_, pointIndex) => {
      for (let seriesIndex = modelNames.length - 1; seriesIndex >= 0; seriesIndex -= 1) {
        const value = Number(chartData.value.hourlyRequests.modelRequests[modelNames[seriesIndex]]?.[pointIndex] || 0)
        if (value > 0) return seriesIndex
      }
      return -1
    })

    const series = modelNames.map((modelName, seriesIndex) => ({
      name: modelName,
      type: 'bar',
      stack: 'total',
      itemStyle: {
        color: getModelColor(modelName),
      },
      data: (chartData.value.hourlyRequests.modelRequests[modelName] || []).map((value, pointIndex) => ({
        value,
        itemStyle: {
          color: getModelColor(modelName),
          borderRadius: topSeriesIndexByPoint[pointIndex] === seriesIndex ? [4, 4, 0, 0] : [0, 0, 0, 0],
        },
      })),
    }))

    applyAnimatedOption('hourlyRequests', {
      ...theme,
      color: modelNames.map(name => getModelColor(name)),
      tooltip: {
        ...theme.tooltip,
        trigger: 'axis',
        axisPointer: {
          type: 'shadow',
        },
        formatter: (params: any) => {
          if (!params || params.length === 0) return ''
          let result = `<div style="font-weight: 600; margin-bottom: 4px;">${params[0].axisValue}</div>`
          let total = 0
          params.forEach((item: any) => {
            total += item.value || 0
            result += `<div style="display: flex; justify-content: space-between; gap: 16px; align-items: center;">
              <span>${item.marker} ${item.seriesName}</span>
              <span style="font-weight: 600;">${item.value || 0}</span>
            </div>`
          })
          result += `<div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid #e5e5e5; font-weight: 600;">
            总计: ${total}
          </div>`
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
        left: 34,
        right: 24,
        top: modelNames.length > 5 ? 56 : 48,
        bottom: 32,
      },
      xAxis: {
        ...theme.xAxis,
        data: chartData.value.hourlyRequests.labels,
        boundaryGap: true,
      },
      yAxis: {
        ...theme.yAxis,
      },
      series: series,
    }, mode)

  }

  function updateModelRankChart(mode: RenderMode = 'refresh') {
    if (!charts.modelRank) return

    const theme = getLineChartTheme()
    const modelTotals = chartData.value.modelRank.models
      .filter(model => model.success_calls > 0)
      .map(model => ({
        model: model.name,
        total: model.success_calls,
      }))
      .sort((left, right) => right.total - left.total || left.model.localeCompare(right.model))

    const modelNames = modelTotals.map(item => item.model)
    const modelValues = modelTotals.map(item => item.total)
    const modelColors = modelNames.map(name => getModelColor(name))

    applyAnimatedOption('modelRank', {
      ...theme,
      grid: {
        left: 12,
        right: 60,
        top: 16,
        bottom: 16,
        containLabel: true,
      },
      xAxis: {
        type: 'value',
        minInterval: 1,
        axisLine: {
          show: false,
        },
        axisTick: {
          show: false,
        },
        axisLabel: {
          ...theme.xAxis.axisLabel,
          fontSize: 10,
          formatter: (value: number) => `${Math.trunc(Number(value || 0))}`,
        },
        splitLine: {
          lineStyle: {
            color: '#e5e5e5',
            type: 'solid',
          },
        },
      },
      yAxis: {
        type: 'category',
        data: modelNames,
        axisLine: {
          show: false,
        },
        axisTick: {
          show: false,
        },
        axisLabel: {
          ...theme.yAxis.axisLabel,
          fontSize: 11,
        },
      },
      series: [
        {
          type: 'bar',
          data: modelValues.map((value, idx) => ({
            value,
            itemStyle: {
              color: modelColors[idx],
              borderRadius: [0, 4, 4, 0],
            },
          })),
          barWidth: '50%',
          label: {
            show: true,
            position: 'right',
            fontSize: 11,
            color: '#6b6b6b',
            formatter: '{c}',
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
        series: [],
      }, mode)
      return
    }

    const series = modelNames.map((modelName) => {
      const color = getModelColor(modelName)
      const seconds = (responseSeriesByModel[modelName] || []).map((ms) => (
        ms === null ? null : Number((ms / 1000).toFixed(2))
      ))
      return createLineSeries(modelName, seconds, color, {
        smooth: true,
        areaOpacity: 0.15,
        zIndex: 2,
      })
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
      series,
    }, mode)
  }

  return {
    stats,
    dashboardDataReady,
    dashboardLoadError,
    retryDashboard,
    dashboardDataWarning,
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
  }
}
