<template>
  <NanocatActionMenu
    :label="label"
    :items="items"
    :disabled="disabled"
    :align="align"
    :placement="placement"
    :size="size"
    :trigger-variant="triggerVariant"
    :trigger-class="triggerClass"
    :menu-class="menuClass"
    :menu-min-width="menuMinWidth"
    :trigger-min-width="triggerMinWidth"
    :trigger-width="triggerWidth"
    @select="emit('select', $event)"
  />
</template>

<script setup lang="ts">
import { ActionMenu as NanocatActionMenu } from 'nanocat-ui'
import type { ActionMenuItem, ButtonSize, MenuPlacement } from 'nanocat-ui'

type FloatingMenuTriggerVariant = 'button' | 'input'

withDefaults(defineProps<{
  label: string
  items: ActionMenuItem[]
  disabled?: boolean
  align?: 'left' | 'right'
  placement?: MenuPlacement
  size?: ButtonSize
  triggerVariant?: FloatingMenuTriggerVariant
  triggerClass?: string
  menuClass?: string
  menuMinWidth?: number
  triggerMinWidth?: number
  triggerWidth?: number
}>(), {
  disabled: false,
  align: 'right',
  placement: 'auto',
  size: 'sm',
  triggerVariant: 'button',
  triggerClass: '',
  menuClass: 'min-w-max',
  menuMinWidth: 0,
  triggerMinWidth: 0,
  triggerWidth: 0,
})

const emit = defineEmits<{
  (e: 'select', key: string): void
}>()
</script>
