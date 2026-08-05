<template>
  <div class="inline-flex min-w-0 items-center">
    <HoverCard card-class="w-72" focusable>
      <span class="inline-flex items-center gap-1.5" aria-label="凭据状态">
        <MetaChip :tone="item.access_token_tone" size="xs" strong>
          {{ item.access_token_label }}
        </MetaChip>
        <MetaChip :tone="item.refresh_token_tone" size="xs" strong>
          {{ item.refresh_token_label }}
        </MetaChip>
      </span>

      <template #content>
        <div class="space-y-3 text-xs leading-5">
          <section>
            <div class="mb-1.5 flex items-center justify-between gap-3">
              <div class="ui-status-title">Access Token</div>
              <Button
                size="xs"
                variant="outline"
                root-class="h-6 px-2 text-[11px] font-normal"
                @click.stop="emit('copy-credential', 'access')"
              >
                复制 AT
              </Button>
            </div>
            <dl class="space-y-1">
              <div class="flex items-start justify-between gap-4">
                <dt class="text-muted-foreground">状态</dt>
                <dd class="text-right font-medium text-foreground">{{ item.access_token_label }}</dd>
              </div>
              <div v-if="hasAccessIssuedAt" class="flex items-start justify-between gap-4">
                <dt class="text-muted-foreground">签发时间</dt>
                <dd class="text-right tabular-nums text-foreground">{{ accessIssuedAt }}</dd>
              </div>
              <div v-if="hasAccessExpiresAt" class="flex items-start justify-between gap-4">
                <dt class="text-muted-foreground">到期时间</dt>
                <dd class="text-right tabular-nums text-foreground">{{ accessExpiresAt }}</dd>
              </div>
            </dl>
          </section>

          <section class="border-t border-border/70 pt-2.5">
            <div class="mb-1.5 flex items-center justify-between gap-3">
              <div class="ui-status-title">Refresh Token</div>
              <Button
                size="xs"
                variant="outline"
                root-class="h-6 px-2 text-[11px] font-normal"
                :disabled="refreshTokenMissing"
                @click.stop="emit('copy-credential', 'refresh')"
              >
                复制 RT
              </Button>
            </div>
            <dl class="space-y-1">
              <div class="flex items-start justify-between gap-4">
                <dt class="text-muted-foreground">状态</dt>
                <dd class="text-right font-medium text-foreground">{{ item.refresh_token_label }}</dd>
              </div>
              <div v-if="hasLastTokenRefreshAt" class="flex items-start justify-between gap-4">
                <dt class="text-muted-foreground">最近成功刷新 AT</dt>
                <dd class="text-right tabular-nums text-foreground">{{ lastTokenRefreshAt }}</dd>
              </div>
              <div v-if="hasRefreshTokenInvalidAt" class="flex items-start justify-between gap-4">
                <dt class="text-muted-foreground">失效时间</dt>
                <dd class="text-right tabular-nums text-foreground">{{ refreshTokenInvalidAt }}</dd>
              </div>
              <div v-if="hasLastTokenRefreshErrorAt" class="flex items-start justify-between gap-4">
                <dt class="text-muted-foreground">失败时间</dt>
                <dd class="text-right tabular-nums text-foreground">{{ lastTokenRefreshErrorAt }}</dd>
              </div>
              <div v-if="item.last_token_refresh_error" class="flex items-start justify-between gap-4">
                <dt class="shrink-0 text-muted-foreground">失败原因</dt>
                <dd class="break-words text-right text-foreground">{{ item.last_token_refresh_error }}</dd>
              </div>
            </dl>
          </section>
        </div>
      </template>
    </HoverCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button, HoverCard, MetaChip } from 'nanocat-ui'

import type { Account } from '@/api/accounts'
import { formatAccountDate } from './viewUtils'

const props = defineProps<{
  item: Account
}>()

const emit = defineEmits<{
  (e: 'copy-credential', kind: 'access' | 'refresh'): void
}>()

const refreshTokenMissing = computed(() => props.item.refresh_token_status === 'missing')
const hasAccessIssuedAt = computed(() => Number(props.item.access_token_issued_at || 0) > 0)
const hasAccessExpiresAt = computed(() => Number(props.item.access_token_expires_at || 0) > 0)
const hasLastTokenRefreshAt = computed(() => Number(props.item.last_token_refresh_at || 0) > 0)
const hasRefreshTokenInvalidAt = computed(() => Number(props.item.refresh_token_invalid_at || 0) > 0)
const hasLastTokenRefreshErrorAt = computed(() => Number(props.item.last_token_refresh_error_at || 0) > 0)
const accessIssuedAt = computed(() => formatAccountDate(props.item.access_token_issued_at))
const accessExpiresAt = computed(() => formatAccountDate(props.item.access_token_expires_at))
const lastTokenRefreshAt = computed(() => formatAccountDate(props.item.last_token_refresh_at))
const refreshTokenInvalidAt = computed(() => formatAccountDate(props.item.refresh_token_invalid_at))
const lastTokenRefreshErrorAt = computed(() => formatAccountDate(props.item.last_token_refresh_error_at))
</script>
