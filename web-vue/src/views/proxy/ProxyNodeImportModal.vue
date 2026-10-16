<template>
  <ModalShell
    :open="formOpen"
    aria-label="Add proxy nodes in bulk"
    :z-index="140"
    close-on-escape
    scrollable
    @close="requestClose"
  >
    <ModalHeader
      title="Add proxy nodes in bulk"
      :subtitle="groupName || 'Current proxy group draft'"
      compact
      @close="requestClose"
    />

    <ModalBody class="space-y-4">
      <label class="block text-xs">
        <span class="ui-field-label">Proxy nodes</span>
        <textarea
          v-model="sourceText"
          rows="12"
          class="ui-textarea-sm min-h-[17rem] w-full resize-y font-mono"
          placeholder="http://127.0.0.1:7890 30&#10;http://user:password@host:7890 20&#10;socks5://127.0.0.1:1080"
          aria-label="One proxy address per line; optionally add image concurrency after the address"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
        ></textarea>
      </label>

      <div class="space-y-1 text-xs leading-5 text-muted-foreground">
        <p>Format per line: proxy address image concurrency</p>
        <p>Image concurrency defaults to 30 when omitted; enter 0 for unlimited. Duplicate addresses are skipped automatically.</p>
      </div>

      <section v-if="invalidItems.length" class="space-y-2" aria-label="Invalid format">
        <p class="text-xs font-medium text-rose-600">Fix these {{ invalidItems.length }} lines</p>
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
      <span class="text-xs text-muted-foreground">Added to the draft; changes take effect after saving the proxy group</span>
      <div class="flex items-center gap-2">
        <Button size="xs" variant="outline" :disabled="submitting" @click="requestClose">Cancel</Button>
        <Button
          size="xs"
          variant="primary"
          :disabled="submitting || !sourceText.trim()"
          @click="submitImport"
        >
          {{ submitting ? 'Adding...' : 'Add in bulk' }}
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
  formatError: (error) => errorMessage(error, 'Failed to add proxy nodes in bulk'),
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
