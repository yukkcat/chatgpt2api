<template>
  <div class="gallery-page" :class="{ 'gallery-page--contained': isWorkspaceLayout }">
    <PagePanel class="gallery-hero">
      <PanelHeader title="图片管理">
        <template #actions>
          <Button size="sm" variant="outline" :disabled="isLoading" @click="openStorageModal">
            存储管理
          </Button>
          <Button size="sm" variant="outline" :disabled="isLoading" @click="refreshAll">
            {{ isLoading ? '刷新中...' : '刷新' }}
          </Button>
        </template>
      </PanelHeader>
      <MetricStrip
        :items="galleryMetricItems"
        columns-class="grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"
        density="compact"
      />
      <FilterToolbar class="gallery-filter-grid" gap="tight" mobile-mode="stack">
        <Input
          :model-value="searchQuery"
          type="text"
          placeholder="搜索文件名、路径、标签"
          block
          root-class="gallery-filter-search"
          @update:model-value="searchQuery = $event"
        />
        <div class="gallery-filter-field gallery-filter-field--tag">
          <GroupedSelectMenu
            v-model="tagFilter"
            :options="tagOptions"
            placeholder="全部标签"
            selected-indicator="none"
          />
        </div>
        <DateRangeInputs
          v-model:start="startDate"
          v-model:end="endDate"
          class="gallery-date-range"
          input-root-class="gallery-date-input"
        />
      </FilterToolbar>
    </PagePanel>

    <PagePanel
      flush
      class="gallery-results-panel"
      :class="{ 'gallery-results-panel--contained': isWorkspaceLayout }"
    >
      <div class="gallery-content-toolbar">
        <div class="flex min-w-0 items-center gap-3">
          <Checkbox
            :model-value="allVisibleSelected"
            :indeterminate="someVisibleSelected"
            :disabled="files.length === 0 || isLoading"
            @update:model-value="toggleSelectAllVisible"
          >
            <span class="sr-only">全选当前视图图片</span>
          </Checkbox>
          <div class="min-w-0">
            <p class="ui-section-kicker">当前视图</p>
            <p class="mt-1 text-xs text-muted-foreground">{{ paginationSummary }}</p>
          </div>
        </div>

        <ActionRow class="gallery-content-actions" gap="tight" mobile-stretch>
          <Button
            size="xs"
            variant="outline"
            :disabled="selectedCount === 0 || batchBusy"
            @click="handleBatchDownload"
          >
            批量下载
          </Button>
          <Button
            size="xs"
            variant="outline"
            :disabled="selectedCount === 0 || batchBusy"
            @click="handleDeleteSelected"
          >
            批量删除
          </Button>
          <Button
            size="xs"
            variant="ghost"
            :disabled="selectedCount === 0 || batchBusy"
            @click="clearSelection"
          >
            取消选择
          </Button>
        </ActionRow>
      </div>

      <PageLoadingState
        v-if="!hasLoadedOnce && files.length === 0"
        class="gallery-state-block"
        title="正在加载图片"
        description="读取图片记录、标签和分页数据。"
      />

      <StateBlock
        v-else-if="files.length === 0"
        class="gallery-state-block"
        :title="galleryLoadError ? '图片管理加载失败' : '暂无图片'"
        :description="galleryLoadError || '换个筛选条件或刷新后再看。'"
      >
        <template #media>
          <Icon icon="lucide:image-off" class="h-12 w-12 text-muted-foreground/40" />
        </template>
      </StateBlock>

      <div
        v-else
        class="gallery-results scrollbar-slim"
        :class="{ 'gallery-results--contained': isWorkspaceLayout }"
      >
        <div class="image-grid">
          <GalleryImageCard
            v-for="file in files"
            :key="file.path"
            :file="file"
            :signature="galleryCardSignature(file)"
            :selected="isSelected(file.path)"
            :previewable="canPreviewFile(file)"
            :copied="copiedFileKey === file.path"
            :image-url="galleryCardImageUrl(file)"
            :storage-label="storageLabel(file)"
            :size-label="formatSize(file.size_bytes)"
            :dimensions="formatDimensions(file)"
            :time-remaining="galleryCardTimeRemaining(file)"
            :genbox-busy="genboxPushBusyPath === file.path"
            @preview="openPreview"
            @select="handleCardSelect"
            @image-error="handleCardImageError"
            @copy="copyFileLink"
            @edit-tags="openTagEditor"
            @download="downloadFile"
            @genbox-push="handleGenBoxPush"
            @delete="handleDelete"
            @tag-click="setTagFilter"
          />
        </div>
      </div>

      <ListPagination
        v-model:page="currentPage"
        v-model:page-size="pageSize"
        v-model:layout-mode="listLayoutMode"
        class="gallery-pagination"
        :total-count="totalItems"
        :page-size-options="galleryPageSizeOptions"
        unit="张图片"
        :disabled="isLoading"
      />
    </PagePanel>

    <GalleryLightbox
      :file="previewFile"
      :image-url="previewFile ? getFileUrl(previewFile.url) : ''"
      :size-label="previewFile ? formatSize(previewFile.size_bytes) : ''"
      :copied="Boolean(previewFile && copiedFileKey === previewFile.path)"
      @close="closePreview"
      @download="downloadFile"
      @copy="copyFileLink"
      @edit-tags="openTagEditor"
    />

    <GalleryTagEditorModal
      :file="tagEditorFile"
      :image-url="tagEditorFile ? getFileUrl(tagEditorFile.thumbnail_url || tagEditorFile.url) : ''"
      :draft="tagDraft"
      :draft-tags="draftTags"
      :all-tags="allTags"
      :is-saving="isTagSaving"
      @close="closeTagEditor"
      @clear="tagDraft = ''"
      @save="saveTagEditor"
      @toggle-tag="toggleDraftTag"
      @update:draft="tagDraft = $event"
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

    <ModalShell
      :open="isStorageModalOpen"
      aria-label="图片存储管理"
      close-on-backdrop
      @close="closeStorageModal"
    >
      <div class="gallery-storage-modal">
        <header class="gallery-storage-header">
          <div>
            <p class="ui-section-kicker">磁盘与图库</p>
            <h3>存储管理</h3>
            <p>查看图片占用、磁盘剩余空间，并执行简单清理。</p>
          </div>
          <CloseButton label="关闭存储管理" @click="closeStorageModal" />
        </header>

        <ModalBody density="normal">
          <div v-if="storageActionError" class="gallery-storage-alert is-error">
            <Icon icon="lucide:circle-alert" class="h-4 w-4" />
            <span>{{ storageActionError }}</span>
          </div>
          <div v-else-if="storageActionMessage" class="gallery-storage-alert is-success">
            <Icon icon="lucide:circle-check" class="h-4 w-4" />
            <span>{{ storageActionMessage }}</span>
          </div>

          <div class="gallery-storage-grid">
            <div v-for="item in storageCardItems" :key="item.label" class="gallery-storage-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>

          <div class="gallery-storage-meter" aria-label="磁盘使用率">
            <div class="gallery-storage-meter__bar">
              <span :style="{ width: storageUsageBarWidth }"></span>
            </div>
            <div class="gallery-storage-meter__meta">
              <span>磁盘使用率</span>
              <strong>{{ storageUsagePercent }}</strong>
            </div>
          </div>

          <div class="gallery-storage-summary">
            <div v-for="item in storageSummaryItems" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>

          <div class="gallery-storage-target">
            <div>
              <span>按目标剩余空间清理</span>
              <p>输入希望保留的磁盘剩余空间，系统会从旧图片开始清理。</p>
            </div>
            <Input
              :model-value="targetFreeMb"
              type="number"
              min="1"
              placeholder="500"
              root-class="gallery-storage-target-input"
              @update:model-value="targetFreeMb = String($event)"
            />
            <div class="gallery-storage-target-actions">
              <Button size="sm" variant="ghost" :disabled="isStorageBusy" @click="handleCleanupToTarget(true)">
                预估
              </Button>
              <Button size="sm" variant="outline" :disabled="isStorageBusy" @click="handleCleanupToTarget(false)">
                清理到目标
              </Button>
            </div>
          </div>
        </ModalBody>

        <ModalFooter align="between" compact>
          <Button size="sm" variant="ghost" :disabled="isStorageBusy" @click="refreshStorageStats">
            {{ isStorageBusy ? '处理中...' : '刷新统计' }}
          </Button>
          <div class="gallery-storage-actions">
            <Button size="sm" variant="outline" :disabled="isStorageBusy" @click="handleCompressStorage">
              压缩图片
            </Button>
            <Button size="sm" variant="outline" :disabled="isStorageBusy" @click="handleCleanupExpired">
              清理过期
            </Button>
          </div>
        </ModalFooter>
      </div>
    </ModalShell>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from 'vue'
import { Icon } from '@iconify/vue'
import {
  resolveGalleryFileUrl,
  type GalleryFile,
  type ImageStorageStats,
} from '@/api/gallery'
import { Button, Checkbox, CloseButton, GroupedSelectMenu, Input } from 'nanocat-ui'
import ActionRow from '@/components/ai/ActionRow.vue'
import DateRangeInputs from '@/components/ai/DateRangeInputs.vue'
import FilterToolbar from '@/components/ai/FilterToolbar.vue'
import GalleryImageCard from '@/components/ai/GalleryImageCard.vue'
import ListPagination from '@/components/ai/ListPagination.vue'
import MetricStrip from '@/components/ai/MetricStrip.vue'
import ModalBody from '@/components/ai/ModalBody.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import PagePanel from '@/components/ai/PagePanel.vue'
import PanelHeader from '@/components/ai/PanelHeader.vue'
import StateBlock from '@/components/ai/StateBlock.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import { usePageRuntime } from '@/composables/usePageRuntime'
import { useListLayoutPreference } from '@/composables/useListLayoutPreference'
import { useGalleryFileActions } from '@/composables/useGalleryFileActions'
import { useGalleryInteractionRuntime } from '@/views/gallery/galleryInteractionRuntime'
import { useGalleryOperationsRuntime } from '@/views/gallery/galleryOperationsRuntime'
import { useGalleryQueryRuntime } from '@/views/gallery/galleryQueryRuntime'
import {
  buildStorageCardItems,
  buildStorageSummaryItems,
  formatDimensions,
  formatSize,
  formatStorageUsagePercent,
  formatTimeRemaining,
  galleryFileCardSignature,
  galleryPageSizeOptions,
  storageUsageBarWidth as getStorageUsageBarWidth,
  storageLabel,
} from '@/views/gallery/galleryView'

defineOptions({ name: 'Gallery' })

const GalleryLightbox = defineAsyncComponent(() => import('@/components/ai/GalleryLightbox.vue'))
const GalleryTagEditorModal = defineAsyncComponent(() => import('@/components/ai/GalleryTagEditorModal.vue'))
const OperationProgressDrawer = defineAsyncComponent(() => import('@/components/ai/OperationProgressDrawer.vue'))

const toast = useToast()
const confirmDialog = useConfirmDialog()
const { listLayoutMode, isWorkspaceLayout } = useListLayoutPreference()

const storageStats = ref<ImageStorageStats | null>(null)

const pageRuntime = usePageRuntime('gallery')
const galleryQueryRuntime = useGalleryQueryRuntime({
  runtime: pageRuntime,
  toast,
  storageStats,
  onApplied: handleGalleryApplied,
})
const files = galleryQueryRuntime.files
const totalSize = galleryQueryRuntime.totalSize
const isLoading = galleryQueryRuntime.isLoading
const hasLoadedOnce = galleryQueryRuntime.hasLoadedOnce
const galleryLoadError = galleryQueryRuntime.galleryLoadError
const tagFilter = galleryQueryRuntime.tagFilter
const searchQuery = galleryQueryRuntime.searchQuery
const startDate = galleryQueryRuntime.startDate
const endDate = galleryQueryRuntime.endDate
const pageSize = galleryQueryRuntime.pageSize
const counts = galleryQueryRuntime.counts
const allTags = galleryQueryRuntime.allTags
const tagOptions = galleryQueryRuntime.tagOptions
const currentPage = galleryQueryRuntime.currentPage
const totalItems = galleryQueryRuntime.totalItems
const paginationSummary = galleryQueryRuntime.paginationSummary
const galleryMetricItems = galleryQueryRuntime.galleryMetricItems
const loadGallery = galleryQueryRuntime.loadGallery
const refreshAll = galleryQueryRuntime.refreshAll
const resetAndLoad = galleryQueryRuntime.resetAndLoad
const storageUsagePercent = computed(() => formatStorageUsagePercent(storageStats.value))
const storageUsageBarWidth = computed(() => getStorageUsageBarWidth(storageUsagePercent.value))
const storageCardItems = computed(() => buildStorageCardItems(storageStats.value, totalSize.value))
const storageSummaryItems = computed(() => buildStorageSummaryItems(storageStats.value, counts.value, totalItems.value, totalSize.value))
const fileActions = useGalleryFileActions({
  resolveUrl: getFileUrl,
})
const copiedFileKey = fileActions.copiedFileKey
const galleryInteractions = useGalleryInteractionRuntime({
  toast,
  files,
  tagFilter,
  loadGallery,
  resetAndLoad,
})
const isTagSaving = galleryInteractions.isTagSaving
const previewFile = galleryInteractions.previewFile
const tagEditorFile = galleryInteractions.tagEditorFile
const tagDraft = galleryInteractions.tagDraft
const selectedPaths = galleryInteractions.selectedPaths
const selectedCount = galleryInteractions.selectedCount
const allVisibleSelected = galleryInteractions.allVisibleSelected
const someVisibleSelected = galleryInteractions.someVisibleSelected
const draftTags = galleryInteractions.draftTags
const openPreview = galleryInteractions.openPreview
const closePreview = galleryInteractions.closePreview
const closePreviewIfPath = galleryInteractions.closePreviewIfPath
const openTagEditor = galleryInteractions.openTagEditor
const closeTagEditor = galleryInteractions.closeTagEditor
const closeTagEditorIfPath = galleryInteractions.closeTagEditorIfPath
const saveTagEditor = galleryInteractions.saveTagEditor
const toggleDraftTag = galleryInteractions.toggleDraftTag
const setTagFilter = galleryInteractions.setTagFilter
const toggleSelect = galleryInteractions.toggleSelect
const toggleSelectAllVisible = galleryInteractions.toggleSelectAllVisible
const isSelected = galleryInteractions.isSelected
const clearSelection = galleryInteractions.clearSelection
const pruneSelection = galleryInteractions.pruneSelection
const canPreviewFile = galleryInteractions.canPreviewFile
const handleImageError = galleryInteractions.handleImageError
const clearBrokenImages = galleryInteractions.clearBrokenImages
const galleryOperations = useGalleryOperationsRuntime({
  runtime: pageRuntime,
  confirmDialog,
  toast,
  files,
  currentPage,
  storageStats,
  selectedPaths,
  loadGallery,
  closePreviewIfPath,
  closeTagEditorIfPath,
  clearSelection,
})
const {
  batchBusy,
  isStorageModalOpen,
  isStorageBusy,
  storageActionMessage,
  storageActionError,
  targetFreeMb,
  operationProgress,
  closeOperationProgress,
  refreshStorageStats,
  openStorageModal,
  closeStorageModal,
  handleCompressStorage,
  handleCleanupExpired,
  handleCleanupToTarget,
  handleDelete,
  handleDeleteSelected,
  handleBatchDownload,
  genboxPushBusyPath,
  handleGenBoxPush,
} = galleryOperations

function getFileUrl(url: string) {
  return resolveGalleryFileUrl(url)
}

function galleryCardImageUrl(file: GalleryFile) {
  return getFileUrl(file.thumbnail_url || file.url)
}

function galleryCardTimeRemaining(file: GalleryFile) {
  return file.expires_in_seconds !== null ? formatTimeRemaining(file.expires_in_seconds) : ''
}

function galleryCardSignature(file: GalleryFile) {
  return galleryFileCardSignature(file, {
    selected: isSelected(file.path),
    previewable: canPreviewFile(file),
    copied: copiedFileKey.value === file.path,
    imageUrl: galleryCardImageUrl(file),
    storageLabel: storageLabel(file),
    sizeLabel: formatSize(file.size_bytes),
    dimensions: formatDimensions(file),
    timeRemaining: galleryCardTimeRemaining(file),
    genboxBusy: genboxPushBusyPath.value === file.path,
  })
}

function handleCardSelect(file: GalleryFile, checked: boolean) {
  toggleSelect(file.path, checked)
}

function handleCardImageError(event: Event, file: GalleryFile) {
  handleImageError(event, file.path)
}

function handleGalleryApplied() {
  clearBrokenImages()
  pruneSelection()
  void refreshStorageStats({ lock: false, silent: true })
}

const downloadFile = fileActions.downloadFile
const copyFileLink = fileActions.copyFileLink

function clearGalleryTimers() {
  fileActions.clearCopyState()
  galleryQueryRuntime.clearTimers()
}

function activateGalleryView(refresh = false) {
  if (refresh) {
    void loadGallery()
  }
}

function deactivateGalleryView() {
  galleryQueryRuntime.invalidate()
  galleryOperations.deactivate()
  clearGalleryTimers()
}

pageRuntime.onActivate(({ initial }) => {
  activateGalleryView(!initial)
  if (initial) void loadGallery()
})

pageRuntime.onDeactivate(() => {
  deactivateGalleryView()
})

pageRuntime.onHide(() => {
  deactivateGalleryView()
})

pageRuntime.onShow(() => {
  activateGalleryView(true)
})
</script>

<style scoped>
.gallery-page {
  --gallery-radius: 16px;

  display: flex;
  flex-direction: column;
  gap: 16px;
}

@media (min-width: 1024px) {
  .gallery-page--contained {
    min-height: 0;
    flex: 1 1 auto;
    overflow: hidden;
  }
}

.gallery-hero {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 20px;
}

:deep(.gallery-filter-search) {
  flex: 1 1 15rem;
  min-width: min(100%, 14rem);
}

.gallery-filter-field {
  flex: 0 0 9rem;
  min-width: 8rem;
}

.gallery-filter-field--tag {
  flex-basis: 9rem;
}

.gallery-date-range {
  --date-range-flex: 0 1 17rem;
  --date-range-min-width: min(100%, 16rem);
  --date-range-input-min-width: 7.25rem;
}

@media (max-width: 640px) {
  .gallery-hero {
    padding: 14px;
  }

  :deep(.gallery-filter-search),
  .gallery-date-range,
  .gallery-filter-field {
    flex: 1 1 auto;
    min-width: 0;
    width: 100%;
  }
}

.gallery-content-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--card));
}

.gallery-results-panel {
  display: flex;
  flex-direction: column;
}

.gallery-results-panel--contained {
  min-height: 0;
  flex: 1 1 auto;
}

.gallery-results {
  padding: 16px;
}

.gallery-results--contained {
  min-height: 0;
  max-height: min(36rem, 60dvh);
  flex: 1 1 auto;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.gallery-pagination {
  flex: 0 0 auto;
  padding: 12px 16px 16px;
}

@media (min-width: 1024px) {
  .gallery-results {
    padding: 20px;
  }

  .gallery-results--contained {
    max-height: none;
  }

  .gallery-pagination {
    padding-inline: 20px;
  }
}

.gallery-state-block {
  min-height: 320px;
  border: 0;
  border-radius: 0;
}

.gallery-storage-modal {
  background: hsl(var(--card));
}

.gallery-storage-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid hsl(var(--border));
  padding: 16px 20px 14px;
}

.gallery-storage-header h3 {
  margin-top: 4px;
  color: hsl(var(--foreground));
  font-size: 1.05rem;
  font-weight: 700;
}

.gallery-storage-header p:last-child {
  margin-top: 4px;
  color: hsl(var(--muted-foreground));
  font-size: 0.8125rem;
}

.gallery-storage-alert {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 0.8125rem;
  line-height: 1.5;
}

.gallery-storage-alert.is-error {
  border: 1px solid rgb(244 63 94 / 0.28);
  background: rgb(244 63 94 / 0.08);
  color: rgb(190 18 60);
}

.gallery-storage-alert.is-success {
  border: 1px solid rgb(16 185 129 / 0.24);
  background: rgb(16 185 129 / 0.08);
  color: rgb(4 120 87);
}

.gallery-storage-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.gallery-storage-card {
  min-width: 0;
  border: 1px solid hsl(var(--border));
  border-radius: 14px;
  background: hsl(var(--muted) / 0.24);
  padding: 12px;
}

.gallery-storage-card span,
.gallery-storage-summary span {
  display: block;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
}

.gallery-storage-card strong,
.gallery-storage-summary strong {
  display: block;
  margin-top: 4px;
  color: hsl(var(--foreground));
  font-size: 1rem;
  font-weight: 700;
}

.gallery-storage-meter {
  margin-top: 14px;
  border: 1px solid hsl(var(--border));
  border-radius: 14px;
  padding: 12px;
}

.gallery-storage-meter__bar {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: hsl(var(--muted));
}

.gallery-storage-meter__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, hsl(var(--primary)), rgb(20 184 166));
  transition: width 0.2s ease;
}

.gallery-storage-meter__meta,
.gallery-storage-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.gallery-storage-meter__meta {
  margin-top: 8px;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
}

.gallery-storage-meter__meta strong {
  color: hsl(var(--foreground));
}

.gallery-storage-summary {
  margin-top: 12px;
  border-radius: 14px;
  background: hsl(var(--secondary) / 0.42);
  padding: 12px;
}

.gallery-storage-target {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 7.5rem auto;
  align-items: end;
  gap: 10px;
  margin-top: 12px;
  border: 1px dashed hsl(var(--border));
  border-radius: 14px;
  background: hsl(var(--muted) / 0.18);
  padding: 12px;
}

.gallery-storage-target span {
  display: block;
  color: hsl(var(--foreground));
  font-size: 0.8125rem;
  font-weight: 700;
}

.gallery-storage-target p {
  margin-top: 4px;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
  line-height: 1.45;
}

:deep(.gallery-storage-target-input) {
  min-width: 0;
}

.gallery-storage-target-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.gallery-storage-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 12px;
}

@media (min-width: 1280px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  }
}

@media (max-width: 640px) {
  .gallery-content-toolbar {
    align-items: stretch;
    border-radius: var(--gallery-radius);
  }

  .gallery-storage-grid {
    grid-template-columns: 1fr;
  }

  .gallery-storage-summary {
    flex-direction: column;
    align-items: stretch;
  }

  .gallery-storage-target {
    grid-template-columns: 1fr;
  }

  .gallery-storage-target-actions {
    justify-content: stretch;
  }

  .gallery-storage-target-actions > * {
    flex: 1 1 auto;
  }

  .gallery-storage-actions {
    width: 100%;
  }

  .gallery-storage-actions > * {
    flex: 1 1 auto;
  }

}

@media (max-width: 420px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(136px, 1fr));
  }
}
</style>
