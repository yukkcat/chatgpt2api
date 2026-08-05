export type PresentationTone = 'success' | 'danger' | 'warning' | 'info' | 'muted'
export type TimelineTone = 'info' | 'warning' | 'danger'
export type TimelineCategory = 'entry' | 'prepare' | 'upstream' | 'resolve' | 'download'
export type TimelineLegendCategory = TimelineCategory | 'state'

export type TimelineSegmentPresentation = {
  key: string
  label: string
  category: TimelineCategory
  value_ms: number
  value_text: string
  tone: TimelineTone
}

export type TimelineStepPresentation = TimelineSegmentPresentation & {
  status_label: string
  time: string
  description: string
}

export type TimelineGroupPresentation = {
  key: TimelineCategory
  label: string
  steps: TimelineStepPresentation[]
}

export type TimelineLegendPresentation = {
  key: string
  label: string
  category: TimelineLegendCategory
  tone: TimelineTone
}

export type TimelinePresentation = {
  segments: TimelineSegmentPresentation[]
  legend_items: TimelineLegendPresentation[]
  groups: TimelineGroupPresentation[]
}

export type CallPresentationStatus = {
  label: string
  tone: PresentationTone
}

export type CallDetailField = {
  label: string
  value: string
  copyable: boolean
  wide: boolean
}

export type RequestDetailPresentation = {
  primary_fields: CallDetailField[]
  diagnostic_fields: CallDetailField[]
  auto_expand_timeline: boolean
  timeline: TimelinePresentation
}
