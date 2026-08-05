<template>
  <component
    :is="tag"
    class="state-block"
    :class="{
      'state-block--compact': compact,
      'state-block--dashed': dashed,
      'state-block--plain': plain,
    }"
  >
    <div v-if="$slots.media" class="state-block__media">
      <slot name="media" />
    </div>
    <p v-if="title" class="state-block__title">{{ title }}</p>
    <p v-if="description" class="state-block__description">{{ description }}</p>
    <slot />
  </component>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  tag?: 'div' | 'p'
  title?: string
  description?: string
  compact?: boolean
  dashed?: boolean
  plain?: boolean
}>(), {
  tag: 'div',
  title: '',
  description: '',
  compact: false,
  dashed: false,
  plain: false,
})
</script>

<style scoped>
.state-block {
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  background: hsl(var(--card));
  padding: 32px 16px;
  text-align: center;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.state-block--compact {
  padding: 24px 12px;
  font-size: 12px;
}

.state-block--dashed {
  border-style: dashed;
}

.state-block--plain {
  min-height: 7rem;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.state-block--plain.state-block--compact {
  min-height: 5rem;
}

.state-block__media {
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
  color: hsl(var(--muted-foreground));
}

.state-block__title {
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.state-block__description {
  margin-top: 8px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}
</style>
