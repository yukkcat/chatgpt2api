<template>
  <tr
    class="border-t border-border"
    :class="group.enabled ? '' : 'bg-muted/30'"
    v-memo="[signature]"
  >
    <td class="py-3 pr-4 align-top">
      <p class="truncate font-medium">{{ group.name || group.id }}</p>
      <p class="mt-1 text-xs text-muted-foreground">多出口 · {{ group.nodes.length }} 个节点</p>
      <p class="mt-1 truncate font-mono text-[11px] text-muted-foreground" :title="group.id">ID：{{ group.id }}</p>
      <p v-if="group.notes" class="mt-1 truncate text-xs text-muted-foreground" :title="group.notes">{{ group.notes }}</p>
    </td>
    <td class="py-3 pr-4 align-top">
      <StateBadge :tone="group.enabled ? 'success' : 'muted'" size="sm">
        {{ group.enabled ? '启用' : '停用' }}
      </StateBadge>
    </td>
    <td class="py-3 pr-4 align-top">
      <div class="space-y-2">
        <ProxyNodeSummaryCard
          v-for="node in group.nodes"
          :key="node.id"
          :node="node"
        />
      </div>
    </td>
    <td class="py-3 pr-4 align-top">
      <button
        type="button"
        class="max-w-full truncate rounded-md border border-border bg-muted/20 px-2 py-1 text-left font-mono text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-foreground"
        :title="`点击复制 ${reference}`"
        @click="emitWithGroup('copy-reference')"
      >
        {{ reference }}
      </button>
    </td>
    <td class="py-3 pr-4 align-top">
      <div class="space-y-1.5">
        <p
          v-for="node in group.nodes"
          :key="`${group.id}-${node.id}-health`"
          class="truncate text-xs"
          :class="nodeTestClass(group, node)"
          :title="node.health.error || node.health.checked_at || ''"
        >
          {{ node.name || node.id }} · {{ nodeTestSummary(group, node) }}
        </p>
      </div>
    </td>
    <td class="py-3 text-right align-top">
      <div class="flex items-center justify-end gap-2">
        <Button size="xs" variant="outline" root-class="w-14 justify-center" @click="emitWithGroup('edit')">
          编辑
        </Button>
        <FloatingActionMenu
          label="更多"
          :items="actionItems"
          align="right"
          size="sm"
          trigger-class="h-7 justify-center px-2 text-[11px]"
          :trigger-width="64"
          @select="handleAction"
        />
      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button } from 'nanocat-ui'
import type { ProxyGroup, ProxyNode } from '@/api/proxy'
import FloatingActionMenu from '@/components/ai/FloatingActionMenu.vue'
import ProxyNodeSummaryCard from '@/components/ai/ProxyNodeSummaryCard.vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import {
  proxyGroupActionItems,
  proxyGroupReference,
  proxyGroupRowSignature,
} from './proxyView'

const props = defineProps<{
  group: ProxyGroup
  testingKey: string
  savingGroupId: string
  deletingGroupId: string
  nodeTestSummary: (group: ProxyGroup, node: ProxyNode) => string
  nodeTestClass: (group: ProxyGroup, node: ProxyNode) => string
}>()

const emit = defineEmits<{
  (e: 'copy-reference', group: ProxyGroup): void
  (e: 'edit', group: ProxyGroup): void
  (e: 'action', group: ProxyGroup, action: string): void
}>()

const signature = computed(() => proxyGroupRowSignature(
  props.group,
  props.testingKey,
  props.savingGroupId,
  props.deletingGroupId,
))

const reference = computed(() => proxyGroupReference(props.group))

const actionItems = computed(() => proxyGroupActionItems(
  props.group,
  props.testingKey,
  props.savingGroupId,
  props.deletingGroupId,
))

function emitWithGroup(event: 'copy-reference' | 'edit') {
  emit(event, props.group)
}

function handleAction(action: string) {
  emit('action', props.group, action)
}
</script>
