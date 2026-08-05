<template>
  <div class="selectable-list-panel" :class="`selectable-list-panel--density-${density}`">
    <div v-if="hasItems" class="selectable-list-panel__items">
      <slot />
    </div>
    <div v-else class="selectable-list-panel__empty">
      <slot name="empty">
        {{ emptyText }}
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  hasItems?: boolean
  emptyText?: string
  density?: 'compact' | 'normal'
}>(), {
  hasItems: false,
  emptyText: '暂无数据',
  density: 'normal',
})
</script>

<style scoped>
.selectable-list-panel {
  max-height: 16rem;
  min-width: 0;
  overflow-y: auto;
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  background: hsl(var(--card));
}

.selectable-list-panel__items {
  min-width: 0;
}

.selectable-list-panel__items :deep(.selectable-list-panel-row) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid hsl(var(--border));
  padding: 8px 12px;
  transition: background-color 0.15s ease;
}

.selectable-list-panel__items :deep(.selectable-list-panel-row:hover) {
  background: hsl(var(--muted) / 0.24);
}

.selectable-list-panel__items :deep(.selectable-list-panel-row:last-child) {
  border-bottom: 0;
}

.selectable-list-panel--density-compact .selectable-list-panel__items :deep(.selectable-list-panel-row) {
  padding: 7px 10px;
}

.selectable-list-panel__empty {
  padding: 32px 12px;
  text-align: center;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}
</style>
