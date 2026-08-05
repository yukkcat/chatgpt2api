import { computed, ref, watch } from 'vue'
import type { GalleryFile } from '@/api/gallery'
import type { SystemLogRow } from '@/api/logs'
import { errorMessage } from '@/lib/errorMessage'
import {
  buildDiagnosticDetailFields,
  buildPrimaryDetailFields,
  buildTimelineView,
  shouldAutoExpandTimeline,
} from '@/views/logs/logDetailView'
import {
  buildLogPreviewGalleryFile,
  buildLogPreviewImages,
  type LogPreviewImage,
} from '@/views/logs/logsView'

export type DetailPreviewImage = LogPreviewImage

type LogDetailRuntimeOptions = {
  loadDetail: (id: string) => Promise<SystemLogRow>
}

export function useLogDetailRuntime(options: LogDetailRuntimeOptions) {
  const selectedLog = ref<SystemLogRow | null>(null)
  const selectedDetailPreview = ref<DetailPreviewImage | null>(null)
  const detailTargetId = ref('')
  const detailLoading = ref(false)
  const detailError = ref('')
  const timelineDetailsExpanded = ref(false)
  const brokenPreviewUrls = ref<Set<string>>(new Set())
  let detailRequestSequence = 0

  const detailOpen = computed(() => Boolean(detailTargetId.value || selectedLog.value))

  const selectedTimeline = computed(() => buildTimelineView(
    selectedLog.value?.detailPresentation.timeline,
  ))
  const selectedTimelineSegments = computed(() => selectedTimeline.value.segments)
  const selectedTimelineLegendItems = computed(() => selectedTimeline.value.legendItems)
  const selectedTimelineGroups = computed(() => selectedTimeline.value.groups)
  const selectedTimelineStepCount = computed(() => selectedTimeline.value.stepCount)
  const selectedTimelineSegmentTotal = computed(() => selectedTimeline.value.segmentTotalMs)
  const timelineDetailsAutoExpanded = computed(() => shouldAutoExpandTimeline(selectedLog.value))
  const timelineDetailsVisible = computed(() => timelineDetailsExpanded.value)

  const selectedPrimaryDetailFields = computed(() => buildPrimaryDetailFields(selectedLog.value))
  const selectedDiagnosticDetailFields = computed(() => buildDiagnosticDetailFields(selectedLog.value))

  const selectedDetailImages = computed(() => buildLogPreviewImages(selectedLog.value, isPreviewBroken))
  const selectedDetailPreviewFile = computed<GalleryFile | null>(() => buildLogPreviewGalleryFile(selectedDetailPreview.value))

  function isPreviewBroken(url: string): boolean {
    return brokenPreviewUrls.value.has(url)
  }

  function markPreviewBroken(event: Event, url: string) {
    const img = event.target as HTMLImageElement
    img.style.opacity = '0'
    brokenPreviewUrls.value = new Set([...brokenPreviewUrls.value, url])
  }

  async function loadDetail(id: string) {
    const targetId = id.trim()
    if (!targetId) return
    const requestSequence = ++detailRequestSequence
    detailTargetId.value = targetId
    selectedDetailPreview.value = null
    detailError.value = ''
    detailLoading.value = true
    selectedLog.value = null

    try {
      const item = await options.loadDetail(targetId)
      if (requestSequence !== detailRequestSequence || detailTargetId.value !== targetId) return
      selectedLog.value = item
    } catch (caught) {
      if (requestSequence !== detailRequestSequence || detailTargetId.value !== targetId) return
      detailError.value = errorMessage(caught, '日志详情加载失败')
    } finally {
      if (requestSequence === detailRequestSequence && detailTargetId.value === targetId) {
        detailLoading.value = false
      }
    }
  }

  function openDetail(item: SystemLogRow) {
    void loadDetail(item.id)
  }

  function openDetailById(id: string) {
    void loadDetail(id)
  }

  function closeDetail() {
    detailRequestSequence += 1
    detailTargetId.value = ''
    detailLoading.value = false
    detailError.value = ''
    selectedLog.value = null
    selectedDetailPreview.value = null
  }

  function openDetailImagePreview(image: DetailPreviewImage) {
    selectedDetailPreview.value = image
  }

  function closeDetailImagePreview() {
    selectedDetailPreview.value = null
  }

  function toggleTimelineDetails() {
    timelineDetailsExpanded.value = !timelineDetailsExpanded.value
  }

  watch(
    [
      () => selectedLog.value?.id || '',
      () => timelineDetailsAutoExpanded.value,
    ],
    () => {
      timelineDetailsExpanded.value = timelineDetailsAutoExpanded.value
    },
  )

  return {
    selectedLog,
    detailOpen,
    detailLoading,
    detailError,
    detailTargetId,
    selectedDetailPreview,
    selectedDetailPreviewFile,
    selectedDetailImages,
    selectedPrimaryDetailFields,
    selectedDiagnosticDetailFields,
    selectedTimelineSegments,
    selectedTimelineLegendItems,
    selectedTimelineGroups,
    selectedTimelineStepCount,
    selectedTimelineSegmentTotal,
    timelineDetailsVisible,
    isPreviewBroken,
    markPreviewBroken,
    openDetail,
    openDetailById,
    closeDetail,
    openDetailImagePreview,
    closeDetailImagePreview,
    toggleTimelineDetails,
  }
}
