<template>
  <MetaChip
    :tone="props.tone"
    variant="soft"
    :size="props.size"
    :radius="props.shape"
    :bordered="props.bordered"
    :chip-class="chipClass"
  >
    <slot />
  </MetaChip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MetaChip from './MetaChip.vue'

const props = withDefaults(defineProps<{
  tone?: 'success' | 'danger' | 'warning' | 'info' | 'muted'
  size?: 'xs' | 'sm'
  shape?: 'pill' | 'rounded'
  bordered?: boolean
}>(), {
  tone: 'muted',
  size: 'sm',
  shape: 'pill',
  bordered: true,
})

const chipClass = computed(() => [
  'state-badge',
  `state-badge--size-${props.size}`,
].filter(Boolean).join(' '))
</script>

<style scoped>
.state-badge {
  justify-content: center;
}

.state-badge--size-sm {
  min-width: 3rem;
}

</style>
