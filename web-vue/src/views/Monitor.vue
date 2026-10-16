<template>
  <div
    class="monitor-page"
    :class="{ 'monitor-page--ready': Boolean(monitorData) }"
  >
    <PagePanel class="monitor-overview-panel space-y-5">
      <PanelHeader title="Live Monitor" align="start">
        <template #copy>
          <p class="mt-1 text-xs text-muted-foreground">
            Live in-process view of ingress, accounts, egress, upstream generation, stream interruptions, and local rejections or busy responses. If the ingress queue is high, check CHATGPT2API_THREAD_TOKENS. Last updated: {{ monitorData?.updated_at || 'Not fetched' }}
          </p>
        </template>
        <template #actions>
          <StateBadge :tone="autoRefresh ? 'success' : 'muted'" shape="rounded">
            {{ autoRefresh ? 'Auto-refresh' : 'Paused' }}
          </StateBadge>
          <label class="flex items-center gap-2 text-xs text-muted-foreground">
            <span class="whitespace-nowrap">Interval</span>
            <Input
              :model-value="String(refreshIntervalSeconds)"
              type="number"
              min="1"
              max="300"
              step="1"
              root-class="w-16"
              @update:model-value="setRefreshIntervalInput"
              @blur="applyRefreshInterval()"
              @change="applyRefreshInterval()"
              @keyup.enter="applyRefreshInterval()"
            />
            <span class="whitespace-nowrap">sec</span>
          </label>
          <Button size="sm" variant="outline" :disabled="isLoading" @click="refreshMonitor(false)">
            {{ isLoading ? 'Refreshing...' : 'Refresh now' }}
          </Button>
          <Button size="sm" variant="outline" @click="toggleAutoRefresh">
            {{ autoRefresh ? 'Pause refresh' : 'Resume refresh' }}
          </Button>
        </template>
      </PanelHeader>

      <div class="grid gap-3 xl:grid-cols-2">
        <div
          v-for="group in diagnosticGroups"
          :key="group.key"
          class="monitor-metric-group"
        >
          <div class="flex items-center justify-between gap-3">
            <p class="text-sm font-semibold text-foreground">{{ group.title }}</p>
            <p class="text-xs text-muted-foreground">{{ group.meta }}</p>
          </div>
          <div class="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <div
              v-for="item in group.items"
              :key="`${group.key}-${item.key}`"
              class="monitor-metric-cell"
            >
              <p class="text-xs leading-4 text-muted-foreground">{{ item.label }}</p>
              <p
                class="mt-1 text-base font-semibold leading-none tabular-nums"
                :class="item.value === '-' ? 'text-muted-foreground' : toneTextClass(item.tone)"
              >
                {{ item.value }}
              </p>
              <p v-if="item.meta" class="mt-1 break-words text-[11px] leading-4 text-muted-foreground">
                {{ item.meta }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <StateBlock
        v-if="loadError"
        compact
        dashed
        title="Failed to load live monitor"
        :description="loadError"
      />
    </PagePanel>

    <PageLoadingState
      v-if="!monitorData && !loadError"
      title="Fetching live snapshot"
      description="Loading active requests, completed records, and bottleneck diagnostics for the current process."
      compact
    />

    <PagePanel v-else-if="monitorData" flush class="monitor-detail-panel">
      <div class="monitor-detail-tabs">
        <ConsoleSegmentedTabs
          v-model="activeDetailPanel"
          :options="detailPanelOptions"
          aria-label="Live monitor details"
          fit="content"
        />
      </div>

      <section v-if="activeDetailPanel === 'active'" class="monitor-detail-section">
        <div class="monitor-detail-header">
          <PanelHeader title="Active requests" align="start">
            <template #copy>
              <p class="mt-1 text-xs text-muted-foreground">
                Running image requests, sorted by arrival time.
              </p>
            </template>
            <template #actions>
              <MetaChip size="xs" tone="info">Current concurrency {{ activeRows.length }} / {{ threadTokens }}</MetaChip>
              <MetaChip size="xs" tone="muted">Ingress queue {{ entryQueueText }}</MetaChip>
            </template>
          </PanelHeader>
        </div>
        <div v-if="activeStageItems.length" class="flex flex-wrap gap-2 px-4 pb-3">
          <MetaChip
            v-for="item in activeStageItems"
            :key="item.label"
            size="xs"
            tone="muted"
          >
            {{ item.label }} {{ item.count }}
          </MetaChip>
        </div>
        <TableShell
          fill
          scroll-mode="contained"
          hover-rows
          unframed
          sticky-header
          :show-empty="activeRows.length === 0"
          :empty-colspan="7"
          empty-title="No active requests"
          empty-description="Running calls will appear here when you start a load test or send an image request."
          table-class="monitor-table"
        >
          <template #head>
            <tr>
              <th>Request</th>
              <th>Model</th>
              <th>Stage</th>
              <th>Elapsed</th>
              <th>Key timings</th>
              <th>Egress</th>
              <th>Account</th>
            </tr>
          </template>
          <MonitorActiveRow
            v-for="row in activeRows"
            :key="row.call_id"
            :row="row"
            :signature="activeRowSignature(row)"
            @open-detail="openDetail"
          />
        </TableShell>
      </section>

      <section v-else-if="activeDetailPanel === 'recent'" class="monitor-detail-section">
        <div class="monitor-detail-header">
          <PanelHeader title="Recently completed" align="start">
            <template #copy>
              <p class="mt-1 text-xs text-muted-foreground">
                Recently completed image calls. This window is stored in process memory.
              </p>
            </template>
            <template #actions>
              <MetaChip size="xs" tone="muted">{{ completedWindowText }}</MetaChip>
            </template>
          </PanelHeader>
        </div>
        <TableShell
          fill
          scroll-mode="contained"
          hover-rows
          unframed
          sticky-header
          :show-empty="recentRows.length === 0"
          :empty-colspan="6"
          empty-title="No completed records"
          empty-description="No image requests have completed since this container started."
          table-class="monitor-table"
        >
          <template #head>
            <tr>
              <th>Request</th>
              <th>Status</th>
              <th>Model</th>
              <th>Total time</th>
              <th>Key timings</th>
              <th>Account / Egress</th>
            </tr>
          </template>
          <MonitorRecentRow
            v-for="row in recentRows"
            :key="`recent-${row.call_id}-${row.ended_at}`"
            :row="row"
            :signature="recentRowSignature(row)"
            @open-detail="openDetail"
          />
        </TableShell>
      </section>

      <section v-else-if="activeDetailPanel === 'slow'" class="monitor-detail-section">
        <div class="monitor-detail-header">
          <PanelHeader title="Slow requests" align="start">
            <template #copy>
              <p class="mt-1 text-xs text-muted-foreground">
                Ranked by ingress wait, account wait, egress wait, upstream generation, and upstream stream interruption.
              </p>
            </template>
          </PanelHeader>
        </div>
        <div
          v-if="slowRows.length"
          class="monitor-detail-card-list scrollbar-slim px-4 pb-4"
        >
          <MonitorSlowCard
            v-for="row in slowRows"
            :key="`slow-${row.call_id}-${row.ended_at}`"
            :row="row"
            :signature="slowRowSignature(row)"
            @open-detail="openDetail"
          />
        </div>
        <div v-else class="monitor-detail-empty px-4 pb-4">
          <EmptyState plain title="No slow requests" description="There are no completed requests in this window to rank." />
        </div>
      </section>

    </PagePanel>

    <MonitorDetailDrawer
      :open="detailOpen"
      :record="detailRecord"
      :loading="detailLoading"
      :error="detailError"
      @close="closeDetail"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, shallowRef } from 'vue'
import { Button, EmptyState, Input, TableShell } from 'nanocat-ui'
import type { SegmentedOption, SegmentedValue } from 'nanocat-ui'
import {
  monitorApi,
  type RealtimeMonitorResponse,
} from '@/api/monitor'
import ConsoleSegmentedTabs from '@/components/ai/ConsoleSegmentedTabs.vue'
import MetaChip from '@/components/ai/MetaChip.vue'
import PagePanel from '@/components/ai/PagePanel.vue'
import PanelHeader from '@/components/ai/PanelHeader.vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import StateBlock from '@/components/ai/StateBlock.vue'
import { usePageQuery, useSerialVisibilityPolling } from '@/composables/usePageQuery'
import { usePageRuntime } from '@/composables/usePageRuntime'
import MonitorActiveRow from '@/views/monitor/MonitorActiveRow.vue'
import MonitorDetailDrawer from '@/views/monitor/MonitorDetailDrawer.vue'
import MonitorRecentRow from '@/views/monitor/MonitorRecentRow.vue'
import MonitorSlowCard from '@/views/monitor/MonitorSlowCard.vue'
import { useMonitorDetailRuntime } from '@/views/monitor/monitorDetailRuntime'
import {
  activeRowSignature,
  recentRowSignature,
  slowRowSignature,
  toneTextClass,
} from '@/views/monitor/monitorView'

defineOptions({ name: 'Monitor' })

const monitorData = shallowRef<RealtimeMonitorResponse | null>(null)
const isLoading = ref(false)
const loadError = ref('')
const autoRefresh = ref(true)
const REFRESH_INTERVAL_STORAGE_KEY = 'chatgpt2api_monitor_refresh_interval_secs'
const DEFAULT_REFRESH_INTERVAL_SECONDS = 5
const MIN_REFRESH_INTERVAL_SECONDS = 1
const MAX_REFRESH_INTERVAL_SECONDS = 300
const refreshIntervalSeconds = ref(readStoredRefreshInterval())
const pageRuntime = usePageRuntime('monitor')
const REFRESH_REQUEST_KEY = 'monitor:refresh'
const POLL_TIMER_KEY = 'monitor:poll'
const monitorQuery = usePageQuery({
  runtime: pageRuntime,
  key: REFRESH_REQUEST_KEY,
  loading: isLoading,
  error: loadError,
  errorMessage: 'Request failed',
})
const monitorDetail = useMonitorDetailRuntime({
  loadDetail: callId => monitorApi.detail(callId),
})
const {
  detailOpen,
  detailLoading,
  detailError,
  detailRecord,
  openDetail,
  closeDetail,
} = monitorDetail
const monitorPolling = useSerialVisibilityPolling({
  runtime: pageRuntime,
  key: POLL_TIMER_KEY,
  intervalMs: () => normalizedRefreshIntervalSeconds() * 1000,
  enabled: () => autoRefresh.value,
  action: () => refreshMonitor(true, 'auto'),
})

const activeRows = computed(() => monitorData.value?.active || [])
const recentRows = computed(() => monitorData.value?.recent.slice(0, 20) || [])
const slowRows = computed(() => monitorData.value?.slow.slice(0, 8) || [])
const activeDetailPanel = ref<SegmentedValue>('active')
const detailPanelOptions = computed<SegmentedOption[]>(() => [
  { value: 'active', label: 'Active requests', count: activeRows.value.length },
  { value: 'recent', label: 'Recently completed', count: recentRows.value.length },
  { value: 'slow', label: 'Slow requests', count: slowRows.value.length },
])
const threadTokens = computed(() => monitorData.value?.threadpool?.tokens || '-')
const completedWindowText = computed(() => monitorData.value?.completed_window_text || 'Window 0 / 0')
const activeStageItems = computed(() => monitorData.value?.active_stage_items || [])
const entryQueueText = computed(() => monitorData.value?.entry_queue_text || '-')
const diagnosticGroups = computed(() => monitorData.value?.diagnostic_groups || [])

async function loadMonitor(silent = true, source: 'auto' | 'manual' = silent ? 'auto' : 'manual') {
  const autoRequest = source === 'auto'
  if (autoRequest && (!pageRuntime.canRun.value || !autoRefresh.value)) return
  if (isLoading.value && silent) return
  await monitorQuery.run(
    () => monitorApi.realtime(),
    {
      apply: (data) => {
        if (autoRequest && !autoRefresh.value) return
        monitorData.value = data
        loadError.value = ''
      },
      silentLoading: silent,
    },
  )
}

async function refreshMonitor(
  silent = true,
  source: 'auto' | 'manual' = silent ? 'auto' : 'manual',
) {
  await Promise.all([
    loadMonitor(silent, source),
    monitorDetail.refreshIfRunning(),
  ])
}

function startPolling() {
  monitorPolling.start()
}

function stopPolling() {
  monitorPolling.stop()
  monitorQuery.invalidate()
}

function activateMonitor(refresh = false) {
  if (refresh) {
    void refreshMonitor(false, 'manual')
  }
  startPolling()
}

function deactivateMonitor() {
  isLoading.value = false
  stopPolling()
}

function handleVisibilityChange() {
  startPolling()
  if (autoRefresh.value) {
    void refreshMonitor(true, 'auto')
  }
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    applyRefreshInterval(false)
    startPolling()
    void refreshMonitor(true, 'auto')
  } else {
    stopPolling()
  }
}

function clampRefreshInterval(value: unknown) {
  const seconds = Math.round(Number(value || DEFAULT_REFRESH_INTERVAL_SECONDS))
  if (!Number.isFinite(seconds)) return DEFAULT_REFRESH_INTERVAL_SECONDS
  return Math.min(MAX_REFRESH_INTERVAL_SECONDS, Math.max(MIN_REFRESH_INTERVAL_SECONDS, seconds))
}

function readStoredRefreshInterval() {
  try {
    return clampRefreshInterval(window.localStorage.getItem(REFRESH_INTERVAL_STORAGE_KEY))
  } catch {
    return DEFAULT_REFRESH_INTERVAL_SECONDS
  }
}

function normalizedRefreshIntervalSeconds() {
  return clampRefreshInterval(refreshIntervalSeconds.value)
}

function setRefreshIntervalInput(value: unknown) {
  refreshIntervalSeconds.value = clampRefreshInterval(value)
}

function applyRefreshInterval(restart = true) {
  const nextValue = normalizedRefreshIntervalSeconds()
  refreshIntervalSeconds.value = nextValue
  try {
    window.localStorage.setItem(REFRESH_INTERVAL_STORAGE_KEY, String(nextValue))
  } catch {
    // ignore storage errors
  }
  if (restart && autoRefresh.value) {
    startPolling()
  }
}

pageRuntime.onActivate(({ initial }) => {
  activateMonitor(true)
})

pageRuntime.onShow(() => {
  handleVisibilityChange()
})

pageRuntime.onHide(() => {
  deactivateMonitor()
})

pageRuntime.onDeactivate(() => {
  deactivateMonitor()
  closeDetail()
})
</script>

<style scoped>
:deep(.monitor-table) {
  width: 100%;
  min-width: 840px;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

:deep(.monitor-table th) {
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--muted) / 0.42);
  padding: 10px 14px;
  color: hsl(var(--muted-foreground));
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

:deep(.monitor-table td) {
  border-bottom: 1px solid hsl(var(--border) / 0.72);
  height: 3.75rem;
  padding: 12px 14px;
  vertical-align: top;
  color: hsl(var(--foreground));
  line-height: 1.45;
}

:deep(.monitor-table td:nth-child(1)) {
  min-width: 8.75rem;
}

:deep(.monitor-table td:nth-child(2)),
:deep(.monitor-table td:nth-child(3)),
:deep(.monitor-table td:nth-child(4)) {
  white-space: nowrap;
}

:deep(.monitor-table td:nth-child(5)),
:deep(.monitor-table td:nth-child(6)),
:deep(.monitor-table td:nth-child(7)) {
  max-width: 18rem;
  white-space: normal;
  overflow-wrap: anywhere;
}

.monitor-metric-group {
  border-radius: 16px;
  border: 1px solid hsl(var(--border));
  background: hsl(var(--background));
  padding: 14px;
}

.monitor-metric-cell {
  display: flex;
  min-height: 4.5rem;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  border-radius: 12px;
  background: hsl(var(--muted) / 0.34);
  padding: 10px 12px;
}

.monitor-page {
  display: grid;
  gap: 1.5rem;
}

.monitor-overview-panel,
.monitor-detail-panel {
  min-width: 0;
}

.monitor-detail-tabs {
  flex: 0 0 auto;
  overflow: hidden;
  border-bottom: 1px solid hsl(var(--border));
  padding: 14px 16px;
}

.monitor-detail-header {
  padding: 16px;
}

.monitor-detail-panel {
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}

.monitor-detail-section {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
}

.monitor-detail-card-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-content: start;
  gap: 0.75rem;
  min-height: 0;
  flex: 1 1 auto;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.monitor-detail-empty {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  align-items: center;
  justify-content: center;
}

@media (min-width: 1024px) {
  .monitor-page--ready {
    grid-auto-rows: minmax(0, 1fr);
  }

  .monitor-page--ready > .monitor-overview-panel,
  .monitor-page--ready > .monitor-detail-panel {
    height: 100%;
  }

  .monitor-page--ready > .monitor-detail-panel {
    contain: size;
  }
}

@media (max-width: 1023px) {
  .monitor-detail-panel {
    height: min(36rem, 72dvh);
    min-height: 24rem;
  }
}

</style>
