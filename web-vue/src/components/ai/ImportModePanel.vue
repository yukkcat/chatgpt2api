<template>
  <section class="import-mode-panel">
    <p class="import-mode-panel__title">{{ title }}</p>
    <slot name="description">
      <p v-if="description" class="import-mode-panel__description">{{ description }}</p>
    </slot>
    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<style scoped>
.import-mode-panel {
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  background: hsl(var(--card));
  padding: 12px;
}

.import-mode-panel__title {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.35;
  color: hsl(var(--foreground));
}

.import-mode-panel__description {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}
</style>
