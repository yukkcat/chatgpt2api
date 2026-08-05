<template>
  <ModalShell
    :open="formOpen"
    aria-label="批量添加代理节点"
    :z-index="140"
    close-on-escape
    scrollable
    @close="requestClose"
  >
    <ModalHeader
      title="批量添加代理节点"
      :subtitle="groupName || '当前代理组草稿'"
      compact
      @close="requestClose"
    />

    <ModalBody class="space-y-4">
      <label class="block text-xs">
        <span class="ui-field-label">代理节点</span>
        <textarea
          v-model="sourceText"
          rows="12"
          class="ui-textarea-sm min-h-[17rem] w-full resize-y font-mono"
          placeholder="http://127.0.0.1:7890 30&#10;http://user:password@host:7890 20&#10;socks5://127.0.0.1:1080"
          aria-label="每行一个代理地址，可在地址后填写图片并发"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
        ></textarea>
      </label>

      <div class="space-y-1 text-xs leading-5 text-muted-foreground">
        <p>每行格式：代理地址 图片并发</p>
        <p>图片并发省略时默认 30，填写 0 表示不限；重复地址会自动跳过。</p>
      </div>

      <section v-if="invalidItems.length" class="space-y-2" aria-label="格式错误">
        <p class="text-xs font-medium text-rose-600">请修正以下 {{ invalidItems.length }} 行</p>
        <div class="max-h-40 overflow-y-auto border-y border-border">
          <div
            v-for="item in invalidItems"
            :key="`${item.line}:${item.raw}`"
            class="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-2 border-b border-border/70 py-2 text-xs last:border-b-0"
          >
            <span class="text-right font-mono text-muted-foreground">{{ item.line }}</span>
            <div class="min-w-0">
              <p class="break-all font-mono text-foreground">{{ item.raw }}</p>
              <p class="mt-0.5 text-rose-600">{{ item.reason }}</p>
            </div>
          </div>
        </div>
      </section>

      <p v-if="submitError" class="text-xs text-rose-600">{{ submitError }}</p>
    </ModalBody>

    <ModalFooter align="between">
      <span class="text-xs text-muted-foreground">添加到草稿，保存代理组后生效</span>
      <div class="flex items-center gap-2">
        <Button size="xs" variant="outline" :disabled="submitting" @click="requestClose">取消</Button>
        <Button
          size="xs"
          variant="primary"
          :disabled="submitting || !sourceText.trim()"
          @click="submitImport"
        >
          {{ submitting ? '添加中...' : '批量添加' }}
        </Button>
      </div>
    </ModalFooter>
  </ModalShell>

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
    @close="requestProgressClose"
  />
</template>

<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { Button } from 'nanocat-ui'

import {
  proxyApi,
  type ProxyNodeImportResult,
} from '@/api/proxy'
import ModalBody from '@/components/ai/ModalBody.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import OperationProgressDrawer from '@/components/ai/OperationProgressDrawer.vue'
import { errorMessage } from '@/lib/errorMessage'
import { useProxyNodeImportRuntime } from '@/views/proxy/proxyNodeImportRuntime'

const props = withDefaults(defineProps<{
  open: boolean
  groupName?: string
  existingUrls?: string[]
}>(), {
  groupName: '',
  existingUrls: () => [],
})

const emit = defineEmits<{
  close: []
  apply: [result: ProxyNodeImportResult]
}>()

const {
  sourceText,
  formOpen,
  submitting,
  invalidItems,
  submitError,
  operationProgress,
  activate,
  deactivate,
  submit,
  closeProgress,
} = useProxyNodeImportRuntime({
  importNodes: proxyApi.importNodes,
  onApply: (result) => emit('apply', result),
  formatError: (error) => errorMessage(error, '批量添加代理节点失败'),
})

watch(() => props.open, (open) => {
  if (open) activate()
  else deactivate()
}, { immediate: true })

onBeforeUnmount(deactivate)

function requestClose() {
  deactivate()
  emit('close')
}

function submitImport() {
  return submit(props.existingUrls)
}

function requestProgressClose() {
  if (closeProgress() === 'done') emit('close')
}
</script>
