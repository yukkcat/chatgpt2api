<template>
  <section
    class="form-section"
    :class="[
      `form-section--density-${density}`,
      muted ? 'form-section--surface-muted' : `form-section--surface-${surface}`,
    ]"
  >
    <div v-if="title || subtitle || $slots.actions" class="form-section__header">
      <div class="min-w-0">
        <p v-if="title" class="form-section__title">{{ title }}</p>
        <p v-if="subtitle" class="form-section__subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="form-section__actions">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </section>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  subtitle?: string
  density?: 'compact' | 'normal' | 'roomy'
  surface?: 'card' | 'background' | 'muted' | 'plain'
  muted?: boolean
}>(), {
  title: '',
  subtitle: '',
  density: 'normal',
  surface: 'card',
  muted: false,
})
</script>

<style scoped>
.form-section {
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.form-section--surface-card {
  background: hsl(var(--card));
}

.form-section--surface-background {
  background: hsl(var(--background));
}

.form-section--surface-muted {
  background: hsl(var(--muted) / 0.18);
}

.form-section--surface-plain {
  border-color: transparent;
  background: transparent;
}

.form-section--density-compact {
  padding: 10px;
}

.form-section--density-normal {
  padding: 12px;
}

.form-section--density-roomy {
  padding: 16px;
}

.form-section--surface-plain.form-section--density-compact,
.form-section--surface-plain.form-section--density-normal,
.form-section--surface-plain.form-section--density-roomy {
  padding: 0;
}

.form-section__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.form-section__title {
  font-size: 11px;
  line-height: 1.25;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: hsl(var(--muted-foreground));
}

.form-section__subtitle {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.45;
  color: hsl(var(--muted-foreground));
}

.form-section__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
</style>
