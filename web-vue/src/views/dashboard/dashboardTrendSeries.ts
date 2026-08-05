export type DashboardTrendSeriesData = {
  successRequests: number[]
  finalFailedRequests: number[]
  switchCount: number[]
}

type DashboardTrendColors = {
  success: string
  failure: string
  switchAccount: string
}

type LineSeriesOptions = {
  areaOpacity: number
  lineStyle?: { type: 'solid' | 'dashed' | 'dotted'; width: number }
  zIndex: number
}

type LineSeriesFactory<T> = (
  name: string,
  data: number[],
  color: string,
  options: LineSeriesOptions,
) => T

export function buildDashboardTrendSeries<T>(
  trend: DashboardTrendSeriesData,
  createLineSeries: LineSeriesFactory<T>,
  colors: DashboardTrendColors,
): T[] {
  return [
    createLineSeries('成功', trend.successRequests, colors.success, {
      areaOpacity: 0.25,
      zIndex: 1,
    }),
    createLineSeries('失败', trend.finalFailedRequests, colors.failure, {
      areaOpacity: 0.3,
      zIndex: 2,
    }),
    createLineSeries('切号', trend.switchCount, colors.switchAccount, {
      areaOpacity: 0,
      lineStyle: { type: 'dashed', width: 2 },
      zIndex: 3,
    }),
  ]
}
