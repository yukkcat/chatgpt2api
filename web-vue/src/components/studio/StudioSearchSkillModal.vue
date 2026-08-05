<template>
  <ModalShell
    :open="open"
    aria-label="搜索 Skill"
    panel-class="studio-search-skill-modal"
    close-on-backdrop
    @close="emit('close')"
  >
    <ModalHeader
      title="搜索 Skill"
      subtitle="将当前搜索接口安装为本地 Skill"
      compact
      @close="emit('close')"
    />

    <ModalBody density="compact" class="search-skill-body">
      <div class="search-skill-meta">
        <span class="search-skill-meta-label">接口</span>
        <code>{{ endpoint }}</code>
        <span class="search-skill-auth">
          <Icon icon="lucide:shield-check" class="h-3.5 w-3.5" />
          密钥由环境变量提供
        </span>
      </div>

      <ConsoleSegmentedTabs
        v-model="language"
        :options="languageOptions"
        aria-label="安装指令语言"
        fit="content"
      />

      <div class="search-skill-code">
        <CodeBlock :content="installPrompt" />
      </div>
    </ModalBody>

    <ModalFooter align="between" compact>
      <span class="search-skill-warning">
        <Icon icon="lucide:shield-check" class="h-3.5 w-3.5" />
        安装指令不包含当前密钥；运行前设置 CHATGPT2API_API_KEY
      </span>
      <Button
        size="sm"
        variant="primary"
        :disabled="isCopying"
        @click="handleCopy"
      >
        {{ copyButtonText }}
      </Button>
    </ModalFooter>
  </ModalShell>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { Button } from 'nanocat-ui'
import { computed, ref, watch } from 'vue'
import CodeBlock from '@/components/ai/CodeBlock.vue'
import ConsoleSegmentedTabs from '@/components/ai/ConsoleSegmentedTabs.vue'
import ModalBody from '@/components/ai/ModalBody.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import { usePublicRuntimeConfig } from '@/composables/usePublicRuntimeConfig'
import {
  buildSearchSkillInstallPrompt,
  loadSearchSkillInstallPrompt,
  searchSkillEndpoint,
  type SearchSkillLanguage,
} from '@/views/studio/studioSearchSkill'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  copy: [value: string]
}>()

const language = ref<SearchSkillLanguage>('zh')
const isCopying = ref(false)
const languageOptions = [
  { label: '中文', value: 'zh' },
  { label: 'English', value: 'en' },
]
const { apiBaseUrl, loadPublicRuntimeConfig } = usePublicRuntimeConfig()
const endpoint = computed(() => searchSkillEndpoint(apiBaseUrl.value))
const installPrompt = computed(() => buildSearchSkillInstallPrompt({
  baseUrl: apiBaseUrl.value,
  language: language.value,
}))
const copyButtonText = computed(() => {
  if (isCopying.value) return language.value === 'zh' ? '正在读取接口' : 'Loading endpoint'
  return language.value === 'zh' ? '复制安装指令' : 'Copy install prompt'
})

async function handleCopy() {
  if (isCopying.value) return
  isCopying.value = true
  try {
    const prompt = await loadSearchSkillInstallPrompt({
      language: language.value,
      getBaseUrl: () => apiBaseUrl.value,
      loadRuntimeConfig: loadPublicRuntimeConfig,
    })
    emit('copy', prompt)
  } finally {
    isCopying.value = false
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) void loadPublicRuntimeConfig()
  },
  { immediate: true },
)
</script>

<style scoped>
.search-skill-body {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: 12px;
}

.search-skill-meta {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

.search-skill-meta-label {
  font-weight: 650;
}

.search-skill-meta code {
  min-width: 0;
  overflow: hidden;
  color: hsl(var(--foreground));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-skill-auth,
.search-skill-warning {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

.search-skill-code {
  min-height: 0;
}

.search-skill-code :deep(.code-block) {
  max-height: min(28rem, calc(100dvh - 17rem));
  overflow: auto;
  margin-top: 0;
}

@media (max-width: 640px) {
  .search-skill-meta {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .search-skill-auth {
    grid-column: 1 / -1;
  }

  .search-skill-warning {
    width: 100%;
  }
}
</style>
