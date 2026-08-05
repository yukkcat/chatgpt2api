<template>
  <div class="flex items-center gap-2" :class="alignClass">
    <Button
      size="xs"
      variant="outline"
      root-class="w-14 justify-center"
      :disabled="busy"
      @click="emit('edit')"
    >
      编辑
    </Button>
    <FloatingActionMenu
      label="更多"
      :items="menuItems"
      align="right"
      size="sm"
      trigger-class="h-7 justify-center px-2 text-[11px]"
      :trigger-width="64"
      :disabled="busy"
      @select="handleSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button } from 'nanocat-ui'
import type { ActionMenuItem } from 'nanocat-ui'
import type { Account } from '@/api/accounts'
import FloatingActionMenu from './FloatingActionMenu.vue'
import { actionMenuGroups } from './menuItems'

const props = withDefaults(defineProps<{
  item: Account
  syncing?: boolean
  refreshingAccessToken?: boolean
  busy?: boolean
  align?: 'start' | 'end'
}>(), {
  syncing: false,
  refreshingAccessToken: false,
  busy: false,
  align: 'start',
})

const emit = defineEmits<{
  (e: 'edit'): void
  (e: 'test'): void
  (e: 'toggle-enabled'): void
  (e: 'sync-account'): void
  (e: 'refresh-access-token'): void
  (e: 'remove'): void
}>()

const alignClass = computed(() => (
  props.align === 'end' ? 'justify-end' : 'justify-start'
))

const refreshAccessTokenLabel = computed(() => {
  if (props.refreshingAccessToken) return '刷新 AT 中...'
  return '刷新 AT'
})

const menuItems = computed<ActionMenuItem[]>(() => actionMenuGroups(
  [
    {
      key: 'test',
      label: '测试',
      disabled: props.busy,
    },
    {
      key: 'refresh-access-token',
      label: refreshAccessTokenLabel.value,
      disabled: props.busy || !props.item.can_refresh_access_token,
    },
    {
      key: 'sync-account',
      label: props.syncing ? '同步中...' : '同步账号与额度',
      disabled: props.busy,
    },
  ],
  [
    {
      key: 'toggle-enabled',
      label: props.item.enabled_action_label,
      disabled: props.busy,
    },
  ],
  [
    {
      key: 'remove',
      label: '删除账号',
      danger: true,
      disabled: props.busy,
    },
  ],
))

function handleSelect(key: string) {
  if (key === 'test') emit('test')
  if (key === 'toggle-enabled') emit('toggle-enabled')
  if (key === 'sync-account') emit('sync-account')
  if (key === 'refresh-access-token') emit('refresh-access-token')
  if (key === 'remove') emit('remove')
}
</script>
