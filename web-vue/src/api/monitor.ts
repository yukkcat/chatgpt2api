import apiClient from './client'

export type MonitorTone = 'success' | 'danger' | 'warning' | 'info' | 'muted'

export interface MonitorSlowMetric {
  key: string
  label: string
  value_ms: number
  value_text: string
  important: boolean
}

export interface MonitorRecordPresentation {
  status_label: string
  status_tone: MonitorTone
  stage_text: string
  error_text: string
  duration_text: string
  metric_digest: string
  egress_text: string
  account_attempt_text: string
  account_egress_text: string
  tracked_duration_ms: number
  untracked_duration_ms: number
  slow_metrics: MonitorSlowMetric[]
  slow_reason_code: string
  slow_reason: string
}

export interface RealtimeMonitorRecord {
  call_id: string
  status?: string
  endpoint?: string
  model?: string
  ended_at?: string
  updated_at?: string
  account_email?: string
  previous_account_email?: string
  presentation: MonitorRecordPresentation
}

export interface RealtimeMonitorRecordDetail extends RealtimeMonitorRecord {
  events: RealtimeMonitorEvent[]
}

export interface RealtimeMonitorEvent {
  time: string
  call_id: string
  event: string
  label: string
  detail_text: string
  model?: string
  timing_text: string
  account_email?: string
  previous_account_email?: string
  status?: string
  public_error?: string
  error?: string
  switched_account?: boolean
}

export interface MonitorStageCount {
  label: string
  count: number
}

export interface MonitorDiagnosticItem {
  key: string
  label: string
  value: string | number
  meta: string
  tone: MonitorTone
}

export interface MonitorDiagnosticGroup {
  key: string
  title: string
  meta: string
  items: MonitorDiagnosticItem[]
}

export interface RealtimeMonitorResponse {
  schema_version: 1
  updated_at: string
  threadpool: {
    tokens: number
  }
  active: RealtimeMonitorRecord[]
  recent: RealtimeMonitorRecord[]
  slow: RealtimeMonitorRecord[]
  completed_window_text: string
  entry_queue_text: string
  active_stage_items: MonitorStageCount[]
  diagnostic_groups: MonitorDiagnosticGroup[]
}

export const monitorApi = {
  realtime() {
    return apiClient.get<never, RealtimeMonitorResponse>('/api/monitor/realtime')
  },
  detail(callId: string) {
    return apiClient.get<never, RealtimeMonitorRecordDetail>(
      `/api/monitor/realtime/${encodeURIComponent(String(callId || '').trim())}`,
    )
  },
}
