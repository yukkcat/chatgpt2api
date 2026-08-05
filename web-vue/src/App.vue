<template>
  <RouterView />
  <Toast :toasts="toastState.toasts" @remove="removeToast" />
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'
import { Toast } from 'nanocat-ui'
import { removeToast, toastState } from '@/composables/useToast'
</script>
