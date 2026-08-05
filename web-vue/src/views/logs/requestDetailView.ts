import type {
  CallDetailField,
  TimelineCategory,
  TimelinePresentation,
  TimelineTone,
} from '@/api/requestDetail'

export type DetailField = CallDetailField
export type DetailTone = TimelineTone
export type DetailTimelineCategory = TimelineCategory

export type DetailTimelineStep = {
  key: string
  label: string
  category: DetailTimelineCategory
  valueMs: number
  value: string
  tone: DetailTone
  statusLabel: string
  barStyle: Record<string, string>
  time: string
  note: string
}

export type DetailTimelineSegment = {
  key: string
  label: string
  valueMs: number
  value: string
  percent: string
  tone: DetailTone
  category: DetailTimelineCategory
  compact: boolean
  barStyle: Record<string, string>
  title: string
}

export type DetailTimelineLegendItem = {
  key: string
  label: string
  category: DetailTimelineCategory | 'state'
  tone: DetailTone
}

export type DetailTimelineGroup = {
  key: DetailTimelineCategory
  name: string
  steps: DetailTimelineStep[]
}

export type DetailTimelineView = {
  segments: DetailTimelineSegment[]
  legendItems: DetailTimelineLegendItem[]
  groups: DetailTimelineGroup[]
  stepCount: number
  segmentTotalMs: number
}

export function buildTimelineView(timeline: TimelinePresentation | null | undefined): DetailTimelineView {
  const source = timeline || { segments: [], legend_items: [], groups: [] }
  const segmentTotalMs = source.segments.reduce((total, segment) => total + segment.value_ms, 0)
  const maxStepMs = Math.max(
    ...source.groups.flatMap((group) => group.steps.map((step) => step.value_ms)),
    0,
  )

  const segments = source.segments.map((segment) => {
    const percent = segmentTotalMs > 0 ? (segment.value_ms / segmentTotalMs) * 100 : 0
    return {
      key: segment.key,
      label: segment.label,
      category: segment.category,
      valueMs: segment.value_ms,
      value: segment.value_text,
      tone: segment.tone,
      percent: `${percent.toFixed(percent >= 10 ? 0 : 1)}%`,
      compact: percent < 12,
      barStyle: { flexGrow: String(Math.max(segment.value_ms, 1)) },
      title: `${segment.label} ${segment.value_text} · ${percent.toFixed(1)}%`,
    }
  })

  const groups = source.groups.map((group) => ({
    key: group.key,
    name: group.label,
    steps: group.steps.map((step) => ({
      key: step.key,
      label: step.label,
      category: step.category,
      valueMs: step.value_ms,
      value: step.value_text,
      tone: step.tone,
      statusLabel: step.status_label,
      barStyle: {
        width: `${Math.max(3, Math.round((step.value_ms / Math.max(maxStepMs, 1)) * 100))}%`,
      },
      time: step.time,
      note: step.description,
    })),
  }))

  return {
    segments,
    legendItems: source.legend_items.map((item) => ({ ...item })),
    groups,
    stepCount: groups.reduce((total, group) => total + group.steps.length, 0),
    segmentTotalMs,
  }
}
