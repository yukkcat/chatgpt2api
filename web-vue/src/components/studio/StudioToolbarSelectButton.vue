<template>
  <button
    type="button"
    class="ui-input-sm ui-select-trigger studio-toolbar-select-button text-left"
    :aria-expanded="expanded"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
defineProps<{
  disabled?: boolean
  expanded?: boolean
}>()
</script>

<style scoped>
.studio-toolbar-select-button {
  flex: 0 0 auto;
  white-space: nowrap;
}
</style>
