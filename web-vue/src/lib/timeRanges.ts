export type DashboardTimeRange = '24h' | '7d' | '30d'

export const DEFAULT_DASHBOARD_TIME_RANGE: DashboardTimeRange = '24h'

export const DASHBOARD_TIME_RANGE_OPTIONS: Array<{
  label: string
  value: DashboardTimeRange
}> = [
  { label: '24小时', value: '24h' },
  { label: '7天', value: '7d' },
  { label: '30天', value: '30d' },
]
