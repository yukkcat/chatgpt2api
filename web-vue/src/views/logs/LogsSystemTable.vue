<template>
  <TableShell
    class="logs-system-table"
    :scroll-mode="layoutMode === 'workspace' ? 'contained' : 'page'"
    hover-rows
    sticky-header
    unframed
    :loading="isFetching && visibleLogs.length === 0"
    loading-title="正在加载日志"
    loading-description="正在获取最新日志数据。"
    :show-empty="!isFetching && visibleLogs.length === 0"
    :empty-colspan="8"
    :empty-title="logsLoadError ? '日志加载失败' : '暂无日志'"
    :empty-description="logsLoadError || '换个筛选条件或刷新后再看。'"
    :scroll-class="layoutMode === 'workspace' ? 'max-h-[min(36rem,60dvh)] lg:max-h-none' : ''"
    table-class="w-full min-w-[900px] table-fixed"
    head-class="normal-case tracking-normal"
    style="--table-shell-footer-padding: 12px 0 0"
  >
    <template #head>
      <tr>
        <th class="w-[4%] py-3 pl-4 pr-2">
          <Checkbox
            :model-value="allVisibleLogsSelected"
            :indeterminate="someVisibleLogsSelected"
            :disabled="visibleLogs.length === 0"
            @update:model-value="emit('toggle-select-all-visible', $event)"
          >
            <span class="sr-only">全选当前页日志</span>
          </Checkbox>
        </th>
        <th class="w-[9%] py-3 pr-5">时间</th>
        <th class="w-[19%] py-3 pr-5">请求</th>
        <th class="w-[16%] py-3 pr-5">执行</th>
        <th class="w-[9%] py-3 pr-5">耗时</th>
        <th class="w-[9%] py-3 pr-5">图片</th>
        <th class="w-[19%] py-3 pr-5">结果</th>
        <th class="w-[15%] py-3 pr-4 text-right">操作</th>
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
        unit="条日志"
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
