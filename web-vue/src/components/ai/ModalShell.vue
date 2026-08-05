<template>
  <NanocatModalShell
    :open="open"
    :max-width="maxWidth"
    :z-index="zIndex"
    :align="align"
    :placement="placement"
    :root-class="resolvedPanelClass"
    :aria-label="ariaLabel"
    :close-on-overlay="closeOnBackdrop"
    :close-on-escape="closeOnEscape"
    bare
    @close="emit('close')"
  >
    <slot />
  </NanocatModalShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ModalShell as NanocatModalShell, OVERLAY_LAYER } from 'nanocat-ui'

const props = withDefaults(defineProps<{
  open: boolean
  maxWidth?: string
  zIndex?: number
  closeOnBackdrop?: boolean
  closeOnEscape?: boolean
  ariaLabel?: string
  align?: 'center' | 'start'
  placement?: 'center' | 'end'
  panelClass?: string
  scrollable?: boolean
}>(), {
  maxWidth: 'clamp(44rem, 50vw, 60rem)',
  zIndex: OVERLAY_LAYER.modal,
  closeOnBackdrop: false,
  closeOnEscape: undefined,
  ariaLabel: '',
  align: 'center',
  placement: 'center',
  panelClass: '',
  scrollable: false,
})

const emit = defineEmits<{
  close: []
}>()

const resolvedPanelClass = computed(() => [
  props.panelClass,
  props.scrollable
    ? 'flex min-h-0 max-h-[calc(100dvh-1rem)] flex-col overflow-hidden sm:max-h-[calc(100dvh-2rem)]'
    : '',
].filter(Boolean).join(' '))
</script>
