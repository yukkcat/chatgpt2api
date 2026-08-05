<template>
  <div
    class="modal-footer"
    :class="[
      bordered ? 'modal-footer--bordered' : '',
      compact ? 'modal-footer--compact' : '',
      flush ? 'modal-footer--flush' : '',
      wrap ? 'modal-footer--wrap' : '',
      `modal-footer--align-${align}`,
    ]"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  align?: 'start' | 'center' | 'end' | 'between'
  bordered?: boolean
  compact?: boolean
  flush?: boolean
  wrap?: boolean
}>(), {
  align: 'end',
  bordered: true,
  compact: false,
  flush: false,
  wrap: true,
})
</script>

<style scoped>
.modal-footer {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
}

.modal-footer--compact {
  padding-block: 10px;
}

.modal-footer--flush {
  padding: 0;
}

.modal-footer--bordered {
  border-top: 1px solid hsl(var(--border));
}

.modal-footer--wrap {
  flex-wrap: wrap;
}

.modal-footer--align-start {
  justify-content: flex-start;
}

.modal-footer--align-center {
  justify-content: center;
}

.modal-footer--align-end {
  justify-content: flex-end;
}

.modal-footer--align-between {
  justify-content: space-between;
}
</style>
