<template>
  <TableShell
    class="logs-system-table"
    :scroll-mode="layoutMode === 'workspace' ? 'contained' : 'page'"
    hover-rows
    sticky-header
    unframed
    :loading="isFetching && visibleLogs.length === 0"
    loading-title="Loading logs"
    loading-description="Fetching the latest log data."
    :show-empty="!isFetching && visibleLogs.length === 0"
    :empty-colspan="9"
    :empty-title="logsLoadError ? 'Failed to load logs' : 'No logs'"
    :empty-description="logsLoadError || 'Try changing the filters or refreshing.'"
    :scroll-class="layoutMode === 'workspace' ? 'max-h-[min(36rem,60dvh)] lg:max-h-none' : ''"
    table-class="w-full min-w-[1080px] table-fixed"
    head-class="normal-case tracking-normal"
    style="--table-shell-footer-padding: 12px 0 0"
  >
    <template #head>
      <tr>
        <th class="w-[3%] py-3 pl-4 pr-2">
          <Checkbox
            :model-value="allVisibleLogsSelected"
            :indeterminate="someVisibleLogsSelected"
            :disabled="visibleLogs.length === 0"
            @update:model-value="emit('toggle-select-all-visible', $event)"
          >
            <span class="sr-only">Select all logs on this page</span>
          </Checkbox>
        </th>
        <th class="w-[8%] py-3 pr-5">Time</th>
        <th class="w-[17%] py-3 pr-5">Request</th>
        <th class="w-[13%] py-3 pr-5">Execution</th>
        <th class="w-[14%] py-3 pr-5">Resolution</th>
        <th class="w-[8%] py-3 pr-5">Duration</th>
        <th class="w-[7%] py-3 pr-5">Images</th>
        <th class="w-[17%] py-3 pr-5">Result</th>
        <th class="w-[13%] py-3 pr-4 text-right">Actions</th>
      </tr>
    </template>

    <LogsSystemRow
      v-for="item in visibleLogs"
      :key="item.id"
      :item="item"
      :signature="rowSignature(item)"
      :selected="isLogSelected(item.id)"
      :first-image-broken="isPreviewBroken(item.imageUrls[0] || '')"
      @toggle-selection="handleToggleLogSelection"
      @open-detail="emit('open-detail', $event)"
      @request-delete-log="emit('request-delete-log', $event)"
      @image-error="emit('image-error', $event)"
    />

    <template #footer>
      <ListPagination
        :page="page"
        :page-size="pageSize"
        :layout-mode="layoutMode"
        :total-count="totalCount"
        :page-size-options="systemLogPageSizeOptions"
        unit="logs"
        :disabled="isFetching"
        @update:page="emit('update:page', $event)"
        @update:page-size="emit('update:pageSize', $event)"
        @update:layout-mode="emit('update:layoutMode', $event)"
      />
    </template>
  </TableShell>
</template>

<script setup lang="ts">
import { Checkbox, TableShell } from 'nanocat-ui'

import ListPagination from '@/components/ai/ListPagination.vue'
import type { SystemLogRow } from '@/api/logs'
import type { ListLayoutMode } from '@/composables/useListLayoutPreference'
import LogsSystemRow from '@/views/logs/LogsSystemRow.vue'
import {
  systemLogPageSizeOptions,
  systemLogRowSignature,
} from '@/views/logs/logsView'

const props = defineProps<{
  visibleLogs: SystemLogRow[]
  isFetching: boolean
  logsLoadError: string
  allVisibleLogsSelected: boolean
  someVisibleLogsSelected: boolean
  page: number
  pageSize: number
  layoutMode: ListLayoutMode
  totalCount: number
  isLogSelected: (id: string) => boolean
  isPreviewBroken: (url: string) => boolean
}>()

const emit = defineEmits<{
  (e: 'update:page', value: number): void
  (e: 'update:pageSize', value: number): void
  (e: 'update:layoutMode', value: ListLayoutMode): void
  (e: 'toggle-select-all-visible', checked: boolean): void
  (e: 'toggle-log-selection', id: string, checked: boolean): void
  (e: 'open-detail', item: SystemLogRow): void
  (e: 'request-delete-log', item: SystemLogRow): void
  (e: 'image-error', url: string): void
}>()

function rowSignature(item: SystemLogRow) {
  return systemLogRowSignature(item, {
    selected: props.isLogSelected(item.id),
    firstImageBroken: props.isPreviewBroken(item.imageUrls[0] || ''),
  })
}

function handleToggleLogSelection(id: string, checked: boolean) {
  emit('toggle-log-selection', id, checked)
}
</script>
