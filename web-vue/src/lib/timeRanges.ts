export type DashboardTimeRange = '24h' | '7d' | '30d'

export const DEFAULT_DASHBOARD_TIME_RANGE: DashboardTimeRange = '24h'

export const DASHBOARD_TIME_RANGE_OPTIONS: Array<{
  label: string
  value: DashboardTimeRange
}> = [
  { label: '24 hours', value: '24h' },
  { label: '7 days', value: '7d' },
  { label: '30 days', value: '30d' },
]
