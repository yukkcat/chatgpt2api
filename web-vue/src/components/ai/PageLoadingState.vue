<template>
  <LoadingState
    :title="title"
    :description="description"
    :compact="compact"
  />
</template>

<script setup lang="ts">
import { LoadingState } from 'nanocat-ui'

withDefaults(defineProps<{
  title?: string
  description?: string
  compact?: boolean
}>(), {
  title: '正在加载',
  description: '',
  compact: false,
})
</script>
