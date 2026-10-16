<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="ui-section-title">User key management</p>
        <p class="mt-1 text-xs text-muted-foreground">
          Create API keys for regular users. After signing in, they can access Chat Studio only.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" :disabled="userKeysLoading" @click="$emit('load')">
          {{ userKeysLoading ? 'Refreshing…' : 'Refresh keys' }}
        </Button>
        <Button size="sm" variant="primary" :disabled="userKeyBusy === 'create'" @click="$emit('create')">
          Create user key
        </Button>
      </div>
    </div>

    <div
      v-if="newUserKey"
      class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="font-medium">This key is shown only once. Copy and save it now.</p>
          <p class="mt-2 break-all font-mono text-xs">{{ newUserKey }}</p>
        </div>
        <Button
          size="xs"
          variant="outline"
          root-class="shrink-0 border-emerald-200 bg-white text-emerald-700"
          @click="$emit('copy', newUserKey)"
        >
          Copy
        </Button>
      </div>
    </div>

    <PageLoadingState
      v-if="userKeysLoading"
      compact
      title="Loading user keys"
      description="Loading the list of regular user keys."
    />
    <StateBlock v-else-if="userKeys.length === 0" compact dashed>
      No regular user keys yet. Create one for users who only need access to Chat Studio.
    </StateBlock>
    <div v-else class="space-y-2">
      <div
        v-for="item in userKeys"
        :key="item.id"
        class="flex flex-col gap-3 rounded-xl border border-border bg-card px-4 py-3 md:flex-row md:items-center md:justify-between"
      >
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <p class="truncate text-sm font-medium text-foreground">{{ item.name || 'Regular user' }}</p>
            <StateBadge
              :tone="item.enabled ? 'success' : 'muted'"
              size="xs"
              shape="rounded"
            >
              {{ item.enabled ? 'Enabled' : 'Disabled' }}
            </StateBadge>
          </div>
          <p class="mt-1 text-xs text-muted-foreground">
            Created {{ formatDateTime(item.created_at) }} · Last used {{ formatDateTime(item.last_used_at) }}
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="xs"
            variant="outline"
            :disabled="userKeyBusy === item.id"
            @click="$emit('edit', item)"
          >
            Edit
          </Button>
          <Button
            size="xs"
            variant="outline"
            :disabled="userKeyBusy === item.id"
            @click="$emit('toggle', item)"
          >
            {{ item.enabled ? 'Disable' : 'Enable' }}
          </Button>
          <Button
            size="xs"
            variant="outline"
            root-class="text-rose-600"
            :disabled="userKeyBusy === item.id"
            @click="$emit('delete', item)"
          >
            Delete
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Button } from 'nanocat-ui'
import type { UserKey } from '@/api/userKeys'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import StateBlock from '@/components/ai/StateBlock.vue'
import { formatDateTime } from '@/views/settings/settingsView'

defineProps<{
  userKeys: UserKey[]
  userKeysLoading: boolean
  userKeyBusy: string
  newUserKey: string
}>()

defineEmits<{
  load: []
  create: []
  copy: [value: string]
  edit: [item: UserKey]
  toggle: [item: UserKey]
  delete: [item: UserKey]
}>()
</script>
