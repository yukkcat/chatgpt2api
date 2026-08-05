import type { SystemLogRow } from '@/api/logs'
import type { DetailField as RequestDetailField } from '@/views/logs/requestDetailView'
export {
  buildTimelineView,
  type DetailField,
  type DetailTimelineCategory,
  type DetailTimelineGroup,
  type DetailTimelineLegendItem,
  type DetailTimelineSegment,
  type DetailTimelineStep,
  type DetailTimelineView,
  type DetailTone,
} from '@/views/logs/requestDetailView'

export function shouldAutoExpandTimeline(item: SystemLogRow | null): boolean {
  return item?.detailPresentation.auto_expand_timeline === true
}

export function buildPrimaryDetailFields(item: SystemLogRow | null): RequestDetailField[] {
  return item?.detailPresentation.primary_fields || []
}

export function hasImageAttemptBreakdown(item: SystemLogRow): boolean {
  return item.detailPresentation.has_attempt_breakdown
}

export function buildDiagnosticDetailFields(item: SystemLogRow | null): RequestDetailField[] {
  return item?.detailPresentation.diagnostic_fields || []
}
