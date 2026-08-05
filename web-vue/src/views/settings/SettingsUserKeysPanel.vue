<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="ui-section-title">用户密钥管理</p>
        <p class="mt-1 text-xs text-muted-foreground">
          创建给普通用户使用的调用密钥；普通用户登录后只进入对话画图页。
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" :disabled="userKeysLoading" @click="$emit('load')">
          {{ userKeysLoading ? '刷新中...' : '刷新密钥' }}
        </Button>
        <Button size="sm" variant="primary" :disabled="userKeyBusy === 'create'" @click="$emit('create')">
          创建用户密钥
        </Button>
      </div>
    </div>

    <div
      v-if="newUserKey"
      class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="font-medium">新密钥只展示一次，请现在复制保存。</p>
          <p class="mt-2 break-all font-mono text-xs">{{ newUserKey }}</p>
        </div>
        <Button
          size="xs"
          variant="outline"
          root-class="shrink-0 border-emerald-200 bg-white text-emerald-700"
          @click="$emit('copy', newUserKey)"
        >
          复制
        </Button>
      </div>
    </div>

    <PageLoadingState
      v-if="userKeysLoading"
      compact
      title="正在加载用户密钥"
      description="读取普通用户密钥列表。"
    />
    <StateBlock v-else-if="userKeys.length === 0" compact dashed>
      暂无普通用户密钥。创建后可以分发给只需要画图入口的用户。
    </StateBlock>
    <div v-else class="space-y-2">
      <div
        v-for="item in userKeys"
        :key="item.id"
        class="flex flex-col gap-3 rounded-xl border border-border bg-card px-4 py-3 md:flex-row md:items-center md:justify-between"
      >
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <p class="truncate text-sm font-medium text-foreground">{{ item.name || '普通用户' }}</p>
            <StateBadge
              :tone="item.enabled ? 'success' : 'muted'"
              size="xs"
              shape="rounded"
            >
              {{ item.enabled ? '已启用' : '已禁用' }}
            </StateBadge>
          </div>
          <p class="mt-1 text-xs text-muted-foreground">
            创建 {{ formatDateTime(item.created_at) }} · 最近使用 {{ formatDateTime(item.last_used_at) }}
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="xs"
            variant="outline"
            :disabled="userKeyBusy === item.id"
            @click="$emit('edit', item)"
          >
            编辑
          </Button>
          <Button
            size="xs"
            variant="outline"
            :disabled="userKeyBusy === item.id"
            @click="$emit('toggle', item)"
          >
            {{ item.enabled ? '禁用' : '启用' }}
          </Button>
          <Button
            size="xs"
            variant="outline"
            root-class="text-rose-600"
            :disabled="userKeyBusy === item.id"
            @click="$emit('delete', item)"
          >
            删除
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
