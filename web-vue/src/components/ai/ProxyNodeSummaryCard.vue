<template>
  <article class="proxy-node-summary-card" :class="{ 'proxy-node-summary-card--disabled': !isEnabled }">
    <div class="proxy-node-summary-card__header">
      <p class="proxy-node-summary-card__name">{{ displayName }}</p>
      <span
        class="proxy-node-summary-card__status"
        :class="isEnabled ? 'proxy-node-summary-card__status--enabled' : 'proxy-node-summary-card__status--disabled'"
      >
        {{ isEnabled ? '启用' : '停用' }}
      </span>
    </div>
    <p class="proxy-node-summary-card__url">{{ maskedUrl || emptyText }}</p>
    <p class="proxy-node-summary-card__meta">图片并发 {{ imageLimit > 0 ? imageLimit : '不限' }}</p>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProxyNode } from '@/api/proxy'

const props = withDefaults(defineProps<{
  node: Pick<ProxyNode, 'id' | 'name' | 'url' | 'enabled' | 'image_concurrency_limit'>
  emptyText?: string
}>(), {
  emptyText: '未设置',
})

const isEnabled = computed(() => props.node.enabled !== false)
const displayName = computed(() => props.node.name || props.node.id)
const imageLimit = computed(() => Math.max(0, Number(props.node.image_concurrency_limit || 0)))
const maskedUrl = computed(() => maskProxy(props.node.url))

function maskProxy(value: unknown) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  return raw.replace(/:\/\/([^/@:]+):([^/@]+)@/, (_match, user) => `://${user}:***@`)
}
</script>

<style scoped>
.proxy-node-summary-card {
  min-width: 0;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
  padding: 8px 10px;
}

.proxy-node-summary-card--disabled {
  background: hsl(var(--muted) / 0.2);
}

.proxy-node-summary-card__header {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.proxy-node-summary-card__name {
  min-width: 0;
  overflow: hidden;
  color: hsl(var(--foreground));
  font-size: 12px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.proxy-node-summary-card__status {
  flex: 0 0 auto;
  font-size: 11px;
}

.proxy-node-summary-card__status--enabled {
  color: hsl(var(--success, 142 71% 45%));
}

.proxy-node-summary-card__status--disabled {
  color: hsl(var(--muted-foreground));
}

.proxy-node-summary-card__url {
  margin-top: 4px;
  overflow-wrap: anywhere;
  color: hsl(var(--muted-foreground));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 11px;
  line-height: 1.35;
}

.proxy-node-summary-card__meta {
  margin-top: 4px;
  color: hsl(var(--muted-foreground));
  font-size: 11px;
  line-height: 1.35;
}
</style>
