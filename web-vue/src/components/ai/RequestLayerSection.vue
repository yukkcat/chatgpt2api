<template>
  <div class="space-y-2">
    <div class="flex items-center gap-2 text-[11px]">
      <span :class="badgeClass">{{ label }}</span>
      <span class="text-muted-foreground">{{ count }} 条</span>
    </div>
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  badgeClass: string
  count: number
}>()
</script>
