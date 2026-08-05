<template>
  <div
    class="action-row"
    :class="[
      `action-row--justify-${justify}`,
      `action-row--gap-${gap}`,
      mobileStretch ? 'action-row--mobile-stretch' : '',
      mobileJustify ? `action-row--mobile-justify-${mobileJustify}` : '',
    ]"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  justify?: 'start' | 'end' | 'between'
  gap?: 'tight' | 'normal'
  mobileStretch?: boolean
  mobileJustify?: 'start' | 'end' | 'between'
}>(), {
  justify: 'start',
  gap: 'normal',
  mobileStretch: false,
  mobileJustify: undefined,
})
</script>

<style scoped>
.action-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.action-row--gap-tight {
  gap: 8px;
}

.action-row--gap-normal {
  gap: 10px;
}

.action-row--justify-start {
  justify-content: flex-start;
}

.action-row--justify-end {
  justify-content: flex-end;
}

.action-row--justify-between {
  justify-content: space-between;
}

@media (max-width: 640px) {
  .action-row--mobile-stretch {
    width: 100%;
  }

  .action-row--mobile-stretch :slotted(*) {
    flex: 1 1 auto;
  }

  .action-row--mobile-justify-start {
    justify-content: flex-start;
  }

  .action-row--mobile-justify-end {
    justify-content: flex-end;
  }

  .action-row--mobile-justify-between {
    justify-content: space-between;
  }
}
</style>
