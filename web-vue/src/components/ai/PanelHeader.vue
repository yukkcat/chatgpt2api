<template>
  <div class="panel-header" :class="`panel-header--align-${align}`">
    <div class="panel-header-copy">
      <p v-if="title" class="ui-section-title">{{ title }}</p>
      <slot name="copy" />
    </div>
    <div v-if="$slots.actions" class="panel-header-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  align?: 'center' | 'start'
}>(), {
  title: '',
  align: 'center',
})
</script>

<style scoped>
.panel-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-header--align-start {
  align-items: flex-start;
}

.panel-header-copy {
  min-width: 0;
  flex: var(--panel-header-copy-flex, 1 1 36rem);
}

.panel-header-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--panel-header-action-gap, 8px);
}

@media (max-width: 640px) {
  .panel-header-actions {
    width: 100%;
  }

  .panel-header-actions :slotted(*) {
    flex: 1 1 auto;
  }
}
</style>
