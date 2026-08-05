<template>
  <component
    :is="tag"
    class="info-card"
    :class="[
      `info-card--tone-${tone}`,
      `info-card--density-${density}`,
    ]"
  >
    <div v-if="title || description || $slots.actions" class="info-card__header">
      <div class="min-w-0">
        <p v-if="title" class="info-card__title">{{ title }}</p>
        <p v-if="description" class="info-card__description">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="info-card__actions">
        <slot name="actions" />
      </div>
    </div>
    <div v-if="$slots.default" class="info-card__body">
      <slot />
    </div>
  </component>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  tag?: 'article' | 'div' | 'section'
  title?: string
  description?: string
  tone?: 'card' | 'muted'
  density?: 'compact' | 'normal' | 'roomy'
}>(), {
  tag: 'section',
  title: '',
  description: '',
  tone: 'card',
  density: 'normal',
})
</script>

<style scoped>
.info-card {
  border: 1px solid hsl(var(--border));
  border-radius: 16px;
}

.info-card--tone-card {
  background: hsl(var(--card));
}

.info-card--tone-muted {
  background: hsl(var(--muted) / 0.24);
}

.info-card--density-compact {
  padding: 12px;
}

.info-card--density-normal {
  padding: 16px;
}

.info-card--density-roomy {
  padding: 20px;
}

.info-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.info-card__title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  color: hsl(var(--foreground));
}

.info-card__description {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.55;
  color: hsl(var(--muted-foreground));
}

.info-card__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.info-card__header + .info-card__body {
  margin-top: 12px;
}
</style>
