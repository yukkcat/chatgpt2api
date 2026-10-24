<template>
  <NanocatConfirmDialog
    :open="open"
    :title="title || 'Confirm action'"
    :message="message"
    :confirm-text="confirmText || 'Confirm'"
    :cancel-text="cancelText || 'Cancel'"
    @confirm="emit('confirm')"
    @cancel="emit('cancel')"
  />
</template>

<script setup lang="ts">
import { ConfirmDialog as NanocatConfirmDialog } from 'nanocat-ui'

defineProps<{
  open: boolean
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()
</script>
