<template>
  <div
    class="logs-page"
    :class="{ 'lg:flex lg:min-h-0 lg:flex-1 lg:flex-col': isWorkspaceLayout }"
  >
    <PagePanel
      class="log-main-panel flex flex-col gap-4"
      :class="{ 'min-h-0 flex-1': isWorkspaceLayout }"
    >
      <div class="log-control-panel">
        <PanelHeader title="日志管理" align="start">
          <template #actions>
            <Button size="sm" variant="outline" :disabled="isFetching" @click="fetchLogs">
              {{ isFetching ? '刷新中...' : '刷新' }}
            </Button>
            <Button size="sm" variant="outline" :disabled="exportDisabled" @click="exportSystemLogs">
              导出当前页摘要
            </Button>
            <Button
              size="sm"
              variant="outline"
              root-class="text-rose-600 hover:text-rose-700"
              :disabled="selectedLogCount === 0 || isFetching || isDeleting"
              @click="requestDeleteSelectedLogs"
            >
              删除所选{{ selectedLogCount ? ` (${selectedLogCount})` : '' }}
            </Button>
          </template>
        </PanelHeader>

        <MetricStrip
          :items="systemMetricItems"
          columns-class="grid-cols-2 md:grid-cols-3 xl:grid-cols-6"
          density="compact"
        />

        <FilterToolbar class="log-toolbar">
          <Input
            v-model.trim="filters.search"
            type="text"
            placeholder="搜索关键词、账号、错误码"
            block
            root-class="log-search-input"
          />
          <DateRangeInputs
            v-model:start="filters.startDate"
            v-model:end="filters.endDate"
            class="log-date-pair"
            input-root-class="log-date-input"
          />
          <div class="log-filter-select">
            <GroupedSelectMenu
              :model-value="systemQuickFilterSelection"
              :groups="systemQuickFilterGroups"
              multiple
              placeholder="筛选"
              selected-count-text="筛选"
              :max-visible-labels="1"
              aria-label="筛选"
              @update:model-value="updateSystemQuickFilters"
            />
          </div>
          <div class="log-filter-select">
            <GroupedSelectMenu
              :model-value="advancedConditionSelection"
              :groups="advancedConditionMenuGroups"
              multiple
              placeholder="更多条件"
              selected-count-text="条件"
              :max-visible-labels="1"
              aria-label="更多条件"
              @update:model-value="updateAdvancedConditions"
            />
          </div>
          <Button size="sm" variant="ghost" :disabled="activeSystemFilterCount === 0" @click="resetFilters">
            重置
          </Button>
        </FilterToolbar>
      </div>

      <LogsSystemTable
        v-model:page="currentPage"
        v-model:page-size="filters.limit"
        v-model:layout-mode="listLayoutMode"
        :visible-logs="logs"
        :is-fetching="isFetching"
        :logs-load-error="logsLoadError"
        :all-visible-logs-selected="allVisibleLogsSelected"
        :some-visible-logs-selected="someVisibleLogsSelected"
        :total-count="logMeta.total"
        :is-log-selected="isLogSelected"
        :is-preview-broken="isPreviewBroken"
        @toggle-select-all-visible="toggleSelectAllVisibleLogs"
        @toggle-log-selection="toggleLogSelection"
        @open-detail="openDetail"
        @request-delete-log="requestDeleteLog"
        @image-error="markPreviewBroken"
      />
    </PagePanel>

    <LogsDetailDrawer
      :open="detailOpen"
      :log="selectedLog"
      :loading="detailLoading"
      :error="detailError"
      :primary-fields="selectedPrimaryDetailFields"
      :diagnostic-fields="selectedDiagnosticDetailFields"
      :timeline-segments="selectedTimelineSegments"
      :timeline-legend-items="selectedTimelineLegendItems"
      :timeline-groups="selectedTimelineGroups"
      :timeline-step-count="selectedTimelineStepCount"
      :timeline-segment-total="selectedTimelineSegmentTotal"
      :timeline-details-visible="timelineDetailsVisible"
      :images="selectedDetailImages"
      @close="closeDetail"
      @copy="copyText"
      @image-error="markPreviewBroken"
      @preview-image="openDetailImagePreview"
      @toggle-timeline-details="toggleTimelineDetails"
    />

    <GalleryLightbox
      :file="selectedDetailPreviewFile"
      :image-url="selectedDetailPreview?.url || ''"
      size-label=""
      :copied="Boolean(selectedDetailPreviewFile && copiedLogPreviewKey === selectedDetailPreviewFile.path)"
      :show-actions="true"
      :show-tag-action="false"
      @download="downloadLogPreviewFile"
      @copy="copyLogPreviewFile"
      @close="closeDetailImagePreview"
    />

    <OperationProgressDrawer
      :open="operationProgress.open"
      :title="operationProgress.title"
      :subtitle="operationProgress.subtitle"
      :total="operationProgress.total"
      :current="operationProgress.current"
      :status-label="operationProgress.statusLabel"
      :error="operationProgress.error"
      :busy="operationProgress.busy"
      :tone="operationProgress.tone"
      :events="operationProgress.events"
      @close="closeOperationProgress"
    />

    <ConfirmDialog
      :open="deleteConfirmation.open"
      :title="deleteConfirmation.title"
      :message="deleteConfirmation.message"
      confirm-text="删除"
      cancel-text="取消"
      @confirm="logSelectionRuntime.confirmDeleteRequest"
      @cancel="closeDeleteConfirmation"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, reactive, ref, toRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button, Input } from 'nanocat-ui'
import ConfirmDialog from '@/components/ui/AppConfirmDialog.vue'
import { GroupedSelectMenu } from 'nanocat-ui'
import DateRangeInputs from '@/components/ai/DateRangeInputs.vue'
import FilterToolbar from '@/components/ai/FilterToolbar.vue'
import MetricStrip from '@/components/ai/MetricStrip.vue'
import OperationProgressDrawer from '@/components/ai/OperationProgressDrawer.vue'
import PagePanel from '@/components/ai/PagePanel.vue'
import PanelHeader from '@/components/ai/PanelHeader.vue'
import { logsApi } from '@/api/logs'
import type { SystemLogRow, SystemLogsResponse } from '@/api/logs'
import {
  normalizeSystemLogDetail,
  normalizeSystemLogRow,
} from '@/api/logs'
import { useToast } from '@/composables/useToast'
import { usePageRuntime } from '@/composables/usePageRuntime'
import { useListLayoutPreference } from '@/composables/useListLayoutPreference'
import { usePageDebouncedAction, usePagedQuery, usePageVisibilityReload } from '@/composables/usePageQuery'
import { useGalleryFileActions } from '@/composables/useGalleryFileActions'
import { errorMessage } from '@/lib/errorMessage'
import { getNumberPreference, preferenceKeys, setNumberPreference } from '@/lib/preferences'
import { useLogDetailRuntime } from '@/views/logs/logDetailRuntime'
import { useLogExportRuntime } from '@/views/logs/logExportRuntime'
import { useLogSelectionRuntime } from '@/views/logs/logSelectionRuntime'
import LogsDetailDrawer from '@/views/logs/LogsDetailDrawer.vue'
import LogsSystemTable from '@/views/logs/LogsSystemTable.vue'
import {
  activeSystemFilterCount as countActiveSystemFilters,
  advancedConditionCount as countAdvancedConditions,
  buildAdvancedConditionMenuGroups,
  buildAdvancedConditionSelection,
  buildSystemQuickFilterSelection,
  cleanLogString,
  filenameFromUrl,
  isQuickEndpointValue,
  latestAdvancedConditionValue,
  latestQuickEndpointValue,
  systemMetricItems as buildSystemMetricItems,
  statusLabel,
  statusTone,
  summaryText,
  systemQuickFilterGroups,
} from '@/views/logs/logsView'

defineOptions({ name: 'Logs' })

const GalleryLightbox = defineAsyncComponent(() => import('@/components/ai/GalleryLightbox.vue'))

type LogRow = SystemLogRow

const toast = useToast()
const route = useRoute()
const { listLayoutMode, isWorkspaceLayout } = useListLayoutPreference()
const pageRuntime = usePageRuntime('logs')
const apiBaseUrl = import.meta.env.VITE_API_URL || window.location.origin
const SYSTEM_LOGS_REQUEST_KEY = 'logs:system'
const SYSTEM_FILTER_FETCH_TIMER_KEY = 'logs:system-filter-fetch'
const logs = ref<LogRow[]>([])
const isFetching = ref(false)
const logsLoadError = ref('')
const DEFAULT_SYSTEM_LOG_LIMIT = 20

const logMeta = reactive<SystemLogsResponse>({
  items: [],
  total: 0,
  limit: DEFAULT_SYSTEM_LOG_LIMIT,
  offset: 0,
  has_more: false,
  facets_scope: '',
  stats_scope: '',
  total_scope: '',
  facets: {
    statuses: {},
    endpoints: {},
    models: {},
    accounts: {},
  },
  stats: {
    total: 0,
    success: 0,
    text_review: 0,
    failed: 0,
    limited: 0,
    image: 0,
  },
})

const filters = reactive({
  type: 'call',
  status: '',
  endpoint: '',
  model: '',
  account: '',
  conversationId: '',
  search: '',
  startDate: '',
  endDate: '',
  limit: DEFAULT_SYSTEM_LOG_LIMIT,
})
const systemLogPageSize = toRef(filters, 'limit')

const logPreviewActions = useGalleryFileActions({
  showDownloadSuccess: false,
  copyErrorMessage: '复制图片链接失败。',
  downloadErrorMessage: (error) => `下载失败：${errorMessage(error, '图片源不可读取')}`,
})
const logDetailRuntime = useLogDetailRuntime({
  loadDetail: async (id) => normalizeSystemLogDetail(await logsApi.get(id), { apiBaseUrl }),
})
const copiedLogPreviewKey = logPreviewActions.copiedFileKey
const selectedLog = logDetailRuntime.selectedLog
const detailOpen = logDetailRuntime.detailOpen
const detailLoading = logDetailRuntime.detailLoading
const detailError = logDetailRuntime.detailError
const selectedDetailPreview = logDetailRuntime.selectedDetailPreview
const selectedDetailPreviewFile = logDetailRuntime.selectedDetailPreviewFile
const selectedDetailImages = logDetailRuntime.selectedDetailImages
const selectedPrimaryDetailFields = logDetailRuntime.selectedPrimaryDetailFields
const selectedDiagnosticDetailFields = logDetailRuntime.selectedDiagnosticDetailFields
const selectedTimelineSegments = logDetailRuntime.selectedTimelineSegments
const selectedTimelineLegendItems = logDetailRuntime.selectedTimelineLegendItems
const selectedTimelineGroups = logDetailRuntime.selectedTimelineGroups
const selectedTimelineStepCount = logDetailRuntime.selectedTimelineStepCount
const selectedTimelineSegmentTotal = logDetailRuntime.selectedTimelineSegmentTotal
const timelineDetailsVisible = logDetailRuntime.timelineDetailsVisible
const isPreviewBroken = logDetailRuntime.isPreviewBroken
const markPreviewBroken = logDetailRuntime.markPreviewBroken
const openDetail = logDetailRuntime.openDetail
const openDetailById = logDetailRuntime.openDetailById
const closeDetail = logDetailRuntime.closeDetail
const openDetailImagePreview = logDetailRuntime.openDetailImagePreview
const closeDetailImagePreview = logDetailRuntime.closeDetailImagePreview
const toggleTimelineDetails = logDetailRuntime.toggleTimelineDetails
const logSelectionRuntime = useLogSelectionRuntime({
  visibleLogs: logs,
  selectedLog,
  closeDetail,
  deleteLogs: (ids) => logsApi.delete(ids),
  refreshLogs: () => fetchLogs(),
})
const deleteTarget = logSelectionRuntime.deleteTarget
const deleteSelectedOpen = logSelectionRuntime.deleteSelectedOpen
const isDeleting = logSelectionRuntime.isDeleting
const operationProgress = logSelectionRuntime.operationProgress
const closeOperationProgress = logSelectionRuntime.closeOperationProgress
const selectedLogCount = logSelectionRuntime.selectedLogCount
const allVisibleLogsSelected = logSelectionRuntime.allVisibleLogsSelected
const someVisibleLogsSelected = logSelectionRuntime.someVisibleLogsSelected
const pruneLogSelectionToVisible = logSelectionRuntime.pruneSelectionToVisible
const isLogSelected = logSelectionRuntime.isLogSelected
const toggleLogSelection = logSelectionRuntime.toggleLogSelection
const toggleSelectAllVisibleLogs = logSelectionRuntime.toggleSelectAllVisibleLogs
const clearLogSelection = logSelectionRuntime.clearLogSelection
const requestDeleteLog = logSelectionRuntime.requestDeleteLog
const requestDeleteSelectedLogs = logSelectionRuntime.requestDeleteSelectedLogs
const deleteConfirmation = computed(() => {
  if (deleteTarget.value) {
    return {
      open: true,
      title: '删除日志',
      message: '确认删除这条日志？',
    }
  }
  if (deleteSelectedOpen.value) {
    return {
      open: true,
      title: '删除日志',
      message: `确认删除 ${selectedLogCount.value} 条日志？`,
    }
  }
  return {
    open: false,
    title: '删除日志',
    message: '',
  }
})

function closeDeleteConfirmation() {
  deleteTarget.value = null
  deleteSelectedOpen.value = false
}

let silentSystemFilterUpdates = 0
let pendingSilentSystemFilterCallbacks: Array<() => void> = []
const routeTargetLogId = ref('')

const systemLogsQuery = usePagedQuery({
  runtime: pageRuntime,
  key: SYSTEM_LOGS_REQUEST_KEY,
  pageSize: systemLogPageSize,
  loading: isFetching,
  error: logsLoadError,
  errorMessage: '日志加载失败',
  fetch: ({ page, pageSize }) => logsApi.listSystem({
    type: filters.type || undefined,
    start_date: filters.startDate || undefined,
    end_date: filters.endDate || undefined,
    status: filters.status || undefined,
    endpoint: filters.endpoint || undefined,
    model: filters.model || undefined,
    account: filters.account || undefined,
    conversation_id: filters.conversationId || undefined,
    search: filters.search || undefined,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  }),
  resolvePage: (response) => Math.floor(response.offset / Math.max(1, response.limit || filters.limit)) + 1,
  resolvePageCount: (response) => Math.ceil(response.total / Math.max(1, response.limit || filters.limit)),
  resolveTotal: (response) => response.total,
  apply: (response) => {
    logs.value = response.items.map((item, index) => normalizeSystemLogRow(item, index, { apiBaseUrl }))
    pruneLogSelectionToVisible()
    logMeta.total = response.total
    logMeta.limit = response.limit
    logMeta.offset = response.offset
    logMeta.has_more = response.has_more
    logMeta.facets_scope = response.facets_scope
    logMeta.stats_scope = response.stats_scope
    logMeta.total_scope = response.total_scope
    logMeta.facets = response.facets
    logMeta.stats = response.stats
  },
  onError: (message) => {
    toast.error(message)
  },
})
const currentPage = systemLogsQuery.currentPage
const systemFilterFetch = usePageDebouncedAction({
  runtime: pageRuntime,
  key: SYSTEM_FILTER_FETCH_TIMER_KEY,
  delayMs: 250,
  shouldRun: () => silentSystemFilterUpdates === 0,
  action: () => {
    systemLogsQuery.resetAndLoad()
  },
})
function cleanString(value: unknown): string {
  return cleanLogString(value)
}

const logExportRuntime = useLogExportRuntime({
  logs,
  logMeta,
  currentPage,
})
const exportDisabled = logExportRuntime.exportDisabled
const exportSystemLogs = logExportRuntime.exportSystemLogs

const systemMetricItems = computed(() => buildSystemMetricItems(logMeta))

const activeSystemFilterCount = computed(() => countActiveSystemFilters(filters))

const systemQuickFilterSelection = computed(() => buildSystemQuickFilterSelection(filters))

const advancedConditionCount = computed(() => countAdvancedConditions(filters))
const advancedConditionMenuGroups = computed(() => buildAdvancedConditionMenuGroups(logMeta.facets.models, logMeta.facets.accounts))
const advancedConditionSelection = computed(() => buildAdvancedConditionSelection(filters))

function loadStoredLogLimits() {
  runWithSilentSystemFilters(() => {
    filters.limit = getNumberPreference(preferenceKeys.systemLogLimit, DEFAULT_SYSTEM_LOG_LIMIT, { min: 1, max: 20000 })
  })
}

function queryValue(value: unknown): string {
  if (Array.isArray(value)) return cleanString(value[0])
  return cleanString(value)
}

function runWithSilentSystemFilters(action: () => void, after?: () => void) {
  silentSystemFilterUpdates += 1
  if (after) pendingSilentSystemFilterCallbacks.push(after)
  try {
    action()
  } finally {
    void nextTick(() => {
      silentSystemFilterUpdates = Math.max(0, silentSystemFilterUpdates - 1)
      if (silentSystemFilterUpdates > 0) return
      const callbacks = pendingSilentSystemFilterCallbacks
      pendingSilentSystemFilterCallbacks = []
      callbacks.forEach((callback) => callback())
    })
  }
}

function applyRouteQuery() {
  const previousTargetLogId = routeTargetLogId.value
  runWithSilentSystemFilters(() => {
    const query = route.query
    const limit = Number(queryValue(query.limit))
    routeTargetLogId.value = queryValue(query.log_id)
    filters.type = queryValue(query.type) || 'call'
    filters.status = queryValue(query.status)
    filters.endpoint = queryValue(query.endpoint)
    filters.model = queryValue(query.model)
    filters.account = queryValue(query.account)
    filters.conversationId = queryValue(query.conversation_id || query.conversationId)
    filters.search = queryValue(query.search)
    filters.startDate = queryValue(query.start_date || query.startDate)
    filters.endDate = queryValue(query.end_date || query.endDate)
    if (Number.isFinite(limit) && limit > 0) {
      filters.limit = Math.min(Math.max(Math.trunc(limit), 1), 20000)
    }
    clearLogSelection()
  })
  if (routeTargetLogId.value) {
    if (routeTargetLogId.value !== previousTargetLogId || !detailOpen.value) {
      openDetailById(routeTargetLogId.value)
    }
  } else if (previousTargetLogId) {
    closeDetail()
  }
}

function resetFilters() {
  runWithSilentSystemFilters(() => {
    filters.type = 'call'
    filters.status = ''
    filters.endpoint = ''
    filters.model = ''
    filters.account = ''
    filters.conversationId = ''
    filters.search = ''
    filters.startDate = ''
    filters.endDate = ''
    clearLogSelection()
  }, scheduleFilterFetch)
}

function touchSystemFilters() {
  clearLogSelection()
  scheduleFilterFetch()
}

function updateAdvancedConditions(value: string | string[]) {
  const values = Array.isArray(value) ? value : value ? [value] : []
  runWithSilentSystemFilters(() => {
    filters.type = latestAdvancedConditionValue(values, 'type') ?? 'call'
    filters.status = latestAdvancedConditionValue(values, 'status') ?? ''
    filters.model = latestAdvancedConditionValue(values, 'model') ?? ''
    filters.account = latestAdvancedConditionValue(values, 'account') ?? ''
  }, touchSystemFilters)
}

function updateSystemQuickFilters(value: string | string[]) {
  const values = Array.isArray(value) ? value : value ? [value] : []
  const hasFailedFilter = values.includes('quick:status:failed')
  const endpoint = latestQuickEndpointValue(values)

  runWithSilentSystemFilters(() => {
    if (hasFailedFilter) {
      filters.status = 'failed'
    } else if (filters.status === 'failed') {
      filters.status = ''
    }

    if (endpoint) {
      filters.endpoint = endpoint
    } else if (isQuickEndpointValue(filters.endpoint)) {
      filters.endpoint = ''
    }
  }, touchSystemFilters)
}

const downloadLogPreviewFile = logPreviewActions.downloadFile
const copyLogPreviewFile = logPreviewActions.copyFileLink

async function copyText(value: string) {
  const text = cleanString(value)
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    toast.success('已复制')
  } catch {
    toast.error('复制失败')
  }
}

async function fetchLogs() {
  await systemLogsQuery.load()
}

function clearLogsTimers() {
  systemFilterFetch.clear()
  logPreviewActions.clearCopyState()
}

function deactivateLogsView() {
  systemLogsQuery.invalidate()
  closeDetail()
  clearLogsTimers()
}

function scheduleFilterFetch() {
  systemFilterFetch.schedule()
}

watch(
  () => [
    filters.type,
    filters.status,
    filters.endpoint,
    filters.model,
    filters.account,
    filters.conversationId,
    filters.search,
    filters.startDate,
    filters.endDate,
    filters.limit,
  ],
  scheduleFilterFetch,
)

watch(
  () => filters.limit,
  (limit) => {
    setNumberPreference(preferenceKeys.systemLogLimit, limit)
  },
)

watch(
  () => route.query,
  () => {
    if (!pageRuntime.canRun.value) return
    applyRouteQuery()
    systemLogsQuery.resetAndLoad()
  },
  { deep: true },
)

pageRuntime.onActivate(({ initial }) => {
  loadStoredLogLimits()
  applyRouteQuery()
  if (initial) {
    systemLogsQuery.resetAndLoad()
    return
  }
  void fetchLogs()
})

pageRuntime.onDeactivate(() => {
  deactivateLogsView()
})

usePageVisibilityReload({
  runtime: pageRuntime,
  invalidate: deactivateLogsView,
  reload: fetchLogs,
})

</script>

<style scoped>
.log-control-panel {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  gap: 16px;
}

:deep(.log-search-input) {
  min-width: min(100%, 18rem);
  flex: 1 1 22rem;
}

.log-date-pair {
  --date-range-flex: 0 0 auto;
  --date-range-min-width: 0;
  --date-range-input-min-width: 9.25rem;
}

.log-filter-select {
  flex: 0 0 auto;
}

</style>
