<template>
  <NanocatConfirmDialog
    :open="open"
    :title="title || '确认操作'"
    :message="message"
    :confirm-text="confirmText || '确定'"
    :cancel-text="cancelText || '取消'"
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
