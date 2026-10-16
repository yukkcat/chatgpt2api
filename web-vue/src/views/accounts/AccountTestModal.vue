<template>
  <ModalShell
    :open="open"
    aria-label="Test account"
    :z-index="140"
    scrollable
    @close="emit('close')"
  >
    <ModalHeader
      title="Test account"
      :subtitle="account?.email || account?.display_name || account?.id || ''"
      :close-disabled="running"
      compact
      @close="emit('close')"
    />

    <ModalBody density="compact" class="space-y-4">
      <div v-if="account" class="grid grid-cols-2 gap-3">
        <SurfaceBox tone="muted" density="compact">
          <span class="ui-field-label">Source / plan</span>
          <p class="mt-1 truncate text-sm text-foreground">{{ account.source_plan_label }}</p>
        </SurfaceBox>
        <SurfaceBox tone="muted" density="compact">
          <span class="ui-field-label">Image quota</span>
          <p class="mt-1 text-sm tabular-nums text-foreground">{{ account.quota_label }}</p>
        </SurfaceBox>
      </div>

      <ConsoleSegmentedTabs
        :model-value="mode"
        :options="modeOptions"
        aria-label="Test type"
        @update:model-value="emit('update:mode', $event as AccountTestMode)"
      />

      <div class="grid grid-cols-1 gap-3 sm:grid-cols-[13rem_minmax(0,1fr)]">
        <div class="text-xs">
          <span class="ui-field-label">Model</span>
          <GroupedSelectMenu
            :model-value="model"
            :options="modelSelectOptions"
            :disabled="running || modelCatalogLoading"
            :placeholder="modelCatalogLoading ? 'Loading models…' : 'Select a model'"
            aria-label="Test model"
            selected-indicator="none"
            block
            @update:model-value="emit('update:model', String($event))"
          />
        </div>

        <label class="block text-xs">
          <span class="ui-field-label">Prompt</span>
          <textarea
            :value="prompt"
            rows="4"
            class="ui-textarea-sm resize-y"
            :disabled="running"
            @input="emit('update:prompt', ($event.target as HTMLTextAreaElement).value)"
          ></textarea>
        </label>
      </div>

      <p v-if="mode === 'image'" class="text-xs text-muted-foreground">
        This generates one real image. On success, one image quota unit is deducted according to the account's current rules.
      </p>

      <section class="account-test-result" aria-live="polite">
        <PageLoadingState
          v-if="running"
          title="Testing account"
          class="account-test-result__center"
          compact
        />
        <div v-else-if="result" class="space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex flex-wrap items-center gap-2">
              <StateBadge :tone="result.tone" size="sm">{{ result.status_label }}</StateBadge>
              <span v-if="result.mode === 'image'" class="text-xs text-muted-foreground">
                Image quota: {{ result.quota_before_label }} → {{ result.quota_after_label }}
              </span>
            </div>
            <span class="text-xs tabular-nums text-muted-foreground">
              {{ formatRequestDuration(result.duration_ms) }}
            </span>
          </div>

          <p v-if="result.error_message" class="text-sm text-rose-600">{{ result.error_message }}</p>
          <StudioMarkdownContent v-else-if="result.content" :content="result.content" />
        </div>
        <div v-else class="account-test-result__center text-sm text-muted-foreground">
          The test result will appear here.
        </div>
      </section>
    </ModalBody>

    <ModalFooter compact>
      <Button size="sm" variant="outline" :disabled="running" @click="emit('close')">Close</Button>
      <Button
        size="sm"
        variant="primary"
        :disabled="running || modelCatalogLoading || !model || !prompt.trim()"
        @click="emit('run')"
      >
        {{ running ? 'Testing…' : 'Start test' }}
      </Button>
    </ModalFooter>
  </ModalShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button, GroupedSelectMenu } from 'nanocat-ui'

import type { Account, AccountTestMode, AccountTestResult } from '@/api/accounts'
import ConsoleSegmentedTabs from '@/components/ai/ConsoleSegmentedTabs.vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import ModalBody from '@/components/ai/ModalBody.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import SurfaceBox from '@/components/ai/SurfaceBox.vue'
import StudioMarkdownContent from '@/components/studio/StudioMarkdownContent.vue'
import { formatRequestDuration } from '@/lib/requestDuration'

const props = defineProps<{
  open: boolean
  account: Account | null
  mode: AccountTestMode
  model: string
  prompt: string
  modelOptions: string[]
  modelCatalogLoading: boolean
  running: boolean
  result: AccountTestResult | null
}>()

const emit = defineEmits<{
  close: []
  run: []
  'update:mode': [value: AccountTestMode]
  'update:model': [value: string]
  'update:prompt': [value: string]
}>()

const modeOptions = [
  { label: 'Chat', value: 'chat' },
  { label: 'Image', value: 'image' },
] as const

const modelSelectOptions = computed(() => props.modelOptions.map((value) => ({
  label: value,
  value,
})))
</script>

<style scoped>
.account-test-result {
  min-height: 8rem;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  padding: 12px;
  background: hsl(var(--muted) / 0.18);
}

.account-test-result__center {
  display: grid;
  min-height: 6.5rem;
  place-items: center;
  text-align: center;
}
</style>
