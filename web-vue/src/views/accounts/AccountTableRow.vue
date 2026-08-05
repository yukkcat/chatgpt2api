<template>
  <tr
    class="border-b border-border transition-colors"
    :class="accountSurfaceClass(item, selected, 'row')"
    :aria-selected="selected || undefined"
  >
    <td class="py-3 pr-4 align-middle">
      <Checkbox
        :model-value="selected"
        :aria-label="`选择账号 ${accountPrimaryText(item)}`"
        @update:model-value="emit('toggle-select', item.id, $event)"
      />
    </td>
    <td class="py-3 pr-5 align-middle">
      <AccountCredentialStatus
        :item="item"
        @copy-credential="emit('copy-credential', item, $event)"
      />
    </td>
    <td class="py-3 pr-5 align-middle">
      <div class="space-y-1 text-xs">
        <p class="font-medium text-foreground">{{ accountSourceText(item) }}</p>
      </div>
    </td>
    <td class="py-3 pr-5 align-middle">
      <StatusDetailPill
        :label="statusText(item)"
        :tone="item.status_tone"
        title="状态详情"
        detail-label="状态说明"
        raw-error-label="原始报错"
        :card-class="statusDetailCardClass"
        :detail="statusDetailText(item)"
        :raw-error="statusRawError(item)"
      />
    </td>
    <td class="py-3 pr-5 align-middle">
      <p class="max-w-[16rem] truncate text-sm font-medium text-foreground">{{ accountPrimaryText(item) }}</p>
      <p class="mt-1 max-w-[16rem] truncate font-mono text-xs text-muted-foreground">{{ accountSecondaryText(item) }}</p>
    </td>
    <td class="py-3 pr-5 align-middle text-xs text-muted-foreground">
      {{ accountCreatedText(item) }}
    </td>
    <td class="py-3 pr-5 align-middle">
      <QuotaBadge :account="item" />
    </td>
    <td class="py-3 pr-5 align-middle text-xs text-muted-foreground">
      {{ accountRestoreText(item) }}
    </td>
    <td class="py-3 pr-5 align-middle">
      <div class="font-mono text-sm tabular-nums">
        <span class="text-emerald-600">{{ item.success_count || 0 }}</span>
        <span class="mx-1 text-muted-foreground/60">/</span>
        <span class="text-rose-600">{{ item.failure_count || 0 }}</span>
      </div>
    </td>
    <td class="py-3 pr-3 text-right align-middle">
      <AccountActionButtons
        :item="item"
        :syncing="syncing"
        :refreshing-access-token="refreshingAccessToken"
        :busy="busy"
        align="end"
        @edit="emit('edit', item)"
        @test="emit('test', item)"
        @toggle-enabled="emit('toggle-enabled', item)"
        @sync-account="emit('sync-account', item)"
        @refresh-access-token="emit('refresh-access-token', item)"
        @remove="emit('remove', item)"
      />
    </td>
  </tr>
</template>

<script setup lang="ts">
import { Checkbox, StatusDetailPill } from 'nanocat-ui'

import AccountActionButtons from '@/components/ai/AccountActionButtons.vue'
import QuotaBadge from '@/components/ai/QuotaBadge.vue'
import type { Account } from '@/api/accounts'
import AccountCredentialStatus from './AccountCredentialStatus.vue'
import {
  accountCreatedText,
  accountPrimaryText,
  accountRestoreText,
  accountSecondaryText,
  accountSourceText,
  accountSurfaceClass,
  statusRawError,
  statusText,
} from './viewUtils'

const props = withDefaults(defineProps<{
  item: Account
  selected: boolean
  syncing?: boolean
  refreshingAccessToken?: boolean
  busy?: boolean
  statusDetailCardClass?: string
  statusDetailText: (item: Account) => string
}>(), {
  syncing: false,
  refreshingAccessToken: false,
  busy: false,
  statusDetailCardClass: '',
})

const emit = defineEmits<{
  (e: 'toggle-select', id: string, checked: unknown): void
  (e: 'copy-credential', item: Account, kind: 'access' | 'refresh'): void
  (e: 'edit', item: Account): void
  (e: 'test', item: Account): void
  (e: 'toggle-enabled', item: Account): void
  (e: 'sync-account', item: Account): void
  (e: 'refresh-access-token', item: Account): void
  (e: 'remove', item: Account): void
}>()
</script>
