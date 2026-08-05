<template>
  <ModalShell
    :open="open"
    aria-label="提示词库"
    max-width="72rem"
    :z-index="220"
    panel-class="studio-prompt-picker-modal"
    close-on-backdrop
    @close="emit('close')"
  >
    <ModalHeader
      title="提示词库"
      :subtitle="headerSubtitle"
      compact
      @close="emit('close')"
    />

    <ModalBody density="compact" class="prompt-picker-body">
      <section class="prompt-picker-filter">
        <FilterToolbar class="prompt-picker-toolbar" :bordered="false" gap="tight" mobile-mode="stack">
          <Input
            v-model.trim="keyword"
            type="text"
            placeholder="搜索标题、分类、词源或提示词"
            block
            root-class="prompt-picker-search-input"
          />

          <div v-if="sourceOptions.length > 1" class="prompt-picker-filter-select">
            <GroupedSelectMenu
              v-model="sourceFilter"
              :options="sourceOptions"
              aria-label="提示词来源"
              placement="bottom"
              selected-indicator="none"
              block
            />
          </div>

          <div v-if="categorySelectOptions.length > 1" class="prompt-picker-filter-select prompt-picker-filter-select--category">
            <GroupedSelectMenu
              v-model="categoryFilter"
              :options="categorySelectOptions"
              aria-label="提示词分类"
              placement="bottom"
              selected-indicator="none"
              block
            />
          </div>
        </FilterToolbar>
      </section>

      <PageLoadingState
        v-if="loading && prompts.length === 0"
        compact
        title="正在读取本地提示词"
        description="优先读取后端本地快照，不等待云端词源。"
      />

      <StateBlock v-else-if="loadError && prompts.length === 0">
        <EmptyState plain title="提示词加载失败" :description="loadError" />
        <div class="prompt-picker-state-actions">
          <Button size="sm" variant="outline" :disabled="loading" @click="loadPrompts(true)">
            {{ loading ? '重试中...' : '重新加载' }}
          </Button>
        </div>
      </StateBlock>

      <StateBlock v-else-if="filteredPrompts.length === 0">
        <EmptyState
          plain
          :title="prompts.length === 0 ? '暂无本地提示词' : '没有匹配的提示词'"
          :description="prompts.length === 0 ? '请到系统设置的提示词源里更新一次词源。' : '换一个关键词、来源或分类再试。'"
        />
      </StateBlock>

      <div v-else class="prompt-picker-grid">
        <article
          v-for="item in visiblePrompts"
          :key="item.id"
          class="prompt-card"
          @click="selectPrompt(item)"
        >
          <div class="prompt-card-media" :class="{ 'is-empty': !promptPreviewUrl(item) }">
            <img
              v-if="promptPreviewUrl(item)"
              :src="promptPreviewUrl(item)"
              :alt="item.title"
              loading="lazy"
              decoding="async"
              @error="handlePreviewError($event, item)"
            />
            <Icon v-else icon="lucide:image-off" class="h-5 w-5" />
          </div>

          <div class="prompt-card-body">
            <div class="prompt-card-meta">
              <MetaChip v-if="promptCategoryLabel(item)" size="xs" tone="muted">{{ promptCategoryLabel(item) }}</MetaChip>
              <MetaChip v-if="item.source_name" size="xs" tone="muted">{{ item.source_name }}</MetaChip>
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ promptDisplaySummary(item) }}</p>
            <div class="prompt-card-footer">
              <span>{{ compactPromptLength(item.prompt) }}</span>
              <Button size="xs" variant="primary" root-class="prompt-card-use-button" @click.stop="selectPrompt(item)">使用</Button>
            </div>
          </div>
        </article>
      </div>
    </ModalBody>

    <ModalFooter align="between" compact>
      <div class="prompt-picker-count">
        已显示 {{ visiblePrompts.length }} / {{ filteredPrompts.length }} 条，库内 {{ prompts.length }} 条
      </div>
      <div class="prompt-picker-footer-actions">
        <Button v-if="hasMorePrompts" size="xs" variant="outline" root-class="min-w-20 justify-center" @click="showAllPrompts">
          加载全部
        </Button>
      </div>
    </ModalFooter>
  </ModalShell>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { Button, EmptyState, Input } from 'nanocat-ui'
import type { PromptLibraryItem } from '@/api/prompts'
import FilterToolbar from '@/components/ai/FilterToolbar.vue'
import MetaChip from '@/components/ai/MetaChip.vue'
import ModalBody from '@/components/ai/ModalBody.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import StateBlock from '@/components/ai/StateBlock.vue'
import { GroupedSelectMenu } from 'nanocat-ui'
import { usePromptLibraryRuntime } from '@/composables/usePromptLibraryRuntime'
import { promptCategoryLabel, promptDisplaySummary } from '@/lib/promptLibrary'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  select: [prompt: PromptLibraryItem]
}>()

const {
  loading,
  loadError,
  prompts,
  sources,
  keyword,
  sourceFilter,
  categoryFilter,
  sourceOptions,
  categoryOptions,
  filteredPrompts,
  promptPreviewUrl,
  handlePreviewError,
  loadPrompts,
} = usePromptLibraryRuntime()

const PROMPT_PAGE_SIZE = 24
const visibleLimit = ref(PROMPT_PAGE_SIZE)

const visiblePrompts = computed(() => filteredPrompts.value.slice(0, visibleLimit.value))
const hasMorePrompts = computed(() => visiblePrompts.value.length < filteredPrompts.value.length)
const categorySelectOptions = computed(() => categoryOptions.value.map((category) => ({
  label: category,
  value: category,
})))

const headerSubtitle = computed(() => {
  if (loading.value && prompts.value.length === 0) return '正在读取本地快照'
  const sourceCount = sources.value.filter((source) => source.enabled).length
  return `${prompts.value.length} 条提示词，${sourceCount || 0} 个启用词源`
})

function compactPromptLength(value: string) {
  const length = Array.from(String(value || '')).length
  return length > 0 ? `${length} 字` : ''
}

function selectPrompt(item: PromptLibraryItem) {
  emit('select', item)
}

function showAllPrompts() {
  visibleLimit.value = filteredPrompts.value.length
}

function ensureLoaded() {
  if (props.open && !loading.value && (prompts.value.length === 0 || sources.value.length === 0)) {
    void loadPrompts(true)
  }
}

onMounted(ensureLoaded)

watch(
  () => props.open,
  () => ensureLoaded(),
  { immediate: true },
)

watch([keyword, sourceFilter, categoryFilter], () => {
  visibleLimit.value = PROMPT_PAGE_SIZE
})
</script>

<style scoped>
:global(.studio-prompt-picker-modal) {
  display: flex;
  height: min(90vh, 62rem);
  min-height: 34rem;
  flex-direction: column;
}

.prompt-picker-body {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 0.75rem;
  overflow-y: auto;
  background: hsl(var(--secondary) / 0.12);
}

.prompt-picker-filter {
  flex: 0 0 auto;
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  background: hsl(var(--card));
  padding: 0.58rem;
}

.prompt-picker-toolbar {
  width: 100%;
}

.prompt-picker-toolbar :deep(.prompt-picker-search-input) {
  flex: 1 1 22rem;
  min-width: min(100%, 16rem);
}

.prompt-picker-filter-select {
  width: min(13rem, 100%);
  min-width: 0;
}

.prompt-picker-filter-select--category {
  width: min(15rem, 100%);
}

.prompt-picker-state-actions {
  margin-top: 0.8rem;
  display: flex;
  justify-content: center;
}

.prompt-picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr));
  gap: 0.8rem;
}

.prompt-card {
  display: flex;
  min-width: 0;
  overflow: hidden;
  flex-direction: column;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
  cursor: pointer;
  transition: border-color 0.16s ease, transform 0.16s ease;
}

.prompt-card:hover {
  border-color: hsl(var(--foreground) / 0.2);
  transform: translateY(-1px);
}

.prompt-card-media {
  display: flex;
  aspect-ratio: 4 / 3;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: hsl(var(--secondary) / 0.58);
  color: hsl(var(--muted-foreground));
}

.prompt-card-media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.prompt-card-media.is-empty {
  border-bottom: 1px solid hsl(var(--border));
}

.prompt-card-body {
  display: flex;
  min-height: 9.25rem;
  flex: 1;
  flex-direction: column;
  gap: 0.55rem;
  padding: 0.78rem 0.85rem 0.85rem;
}

.prompt-card-meta {
  display: flex;
  min-height: 1.3rem;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.prompt-card h3 {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  color: hsl(var(--foreground));
  font-size: 0.92rem;
  font-weight: 680;
  line-height: 1.45;
}

.prompt-card p {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  color: hsl(var(--muted-foreground));
  font-size: 0.8rem;
  line-height: 1.55;
}

.prompt-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: auto;
  color: hsl(var(--muted-foreground));
  font-size: 0.76rem;
}

:global(.prompt-card-use-button) {
  min-width: 3rem;
  justify-content: center;
}

.prompt-picker-count {
  min-width: 0;
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-size: 0.78rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.prompt-picker-footer-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 0.45rem;
}

@media (max-width: 900px) {
  .prompt-picker-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  :global(.studio-prompt-picker-modal) {
    height: min(92vh, 58rem);
    min-height: 0;
  }

  .prompt-picker-filter-select {
    width: 100%;
  }

  .prompt-picker-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
