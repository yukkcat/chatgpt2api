import type {
  MonitorTone,
  RealtimeMonitorRecord,
} from '@/api/monitor'

const TONE_TEXT_CLASSES: Record<MonitorTone, string> = {
  success: 'text-emerald-600 dark:text-emerald-400',
  danger: 'text-rose-600 dark:text-rose-400',
  warning: 'text-amber-600 dark:text-amber-400',
  info: 'text-sky-600 dark:text-sky-400',
  muted: 'text-foreground',
}

export function toneTextClass(tone: MonitorTone) {
  return TONE_TEXT_CLASSES[tone]
}

export function shortCallId(value: unknown) {
  const text = String(value || '')
  return text ? text.slice(0, 8) : '-'
}

export function activeRowSignature(row: RealtimeMonitorRecord) {
  return [
    row.call_id,
    row.endpoint,
    row.model,
    row.account_email,
    row.previous_account_email,
    row.presentation.status_label,
    row.presentation.stage_text,
    row.presentation.duration_text,
    row.presentation.metric_digest,
    row.presentation.egress_text,
    row.presentation.account_attempt_text,
  ].join('|')
}

export function recentRowSignature(row: RealtimeMonitorRecord) {
  return [
    row.call_id,
    row.ended_at,
    row.updated_at,
    row.model,
    row.presentation.status_label,
    row.presentation.status_tone,
    row.presentation.duration_text,
    row.presentation.metric_digest,
    row.presentation.account_egress_text,
  ].join('|')
}

export function slowRowSignature(row: RealtimeMonitorRecord) {
  return [
    row.call_id,
    row.ended_at,
    row.updated_at,
    row.model,
    row.endpoint,
    row.presentation.error_text,
    row.presentation.status_tone,
    row.presentation.duration_text,
    row.presentation.slow_reason_code,
    row.presentation.slow_reason,
    ...row.presentation.slow_metrics.map(item => `${item.key}:${item.value_text}:${item.important}`),
  ].join('|')
}
