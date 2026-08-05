<template>
  <DrawerShell
    :open="open && !minimized"
    :title="title"
    :max-width="maxWidth"
    :root-class="rootClass"
    :z-index="zIndex"
    bare
    :show-backdrop="!detached"
    :close-on-overlay="!detached"
    :close-on-escape="!detached"
    @close="emit('close')"
  >
    <ModalHeader :title="title" @close="emit('close')">
      <template v-if="minimizable" #actions>
        <CloseButton
          icon="lucide:minus"
          label="收起详情面板"
          @click="minimized = true"
        />
      </template>
    </ModalHeader>

    <div class="request-detail-drawer">
      <div v-if="loading" class="request-detail-drawer__state">
        <LoadingState
          :title="loadingTitle"
          :description="loadingDescription"
          compact
          align="center"
        />
      </div>
      <div v-else-if="error" class="request-detail-drawer__state">
        <StateBlock :title="errorTitle" :description="error" compact />
      </div>
      <div v-else class="scrollbar-slim request-detail-drawer__content">
        <slot />
      </div>
    </div>
  </DrawerShell>

  <SideDock
    :open="open && minimizable && minimized"
    aria-label="展开详情面板"
    :z-index="zIndex"
    width="10rem"
    @click="minimized = false"
  >
    <span class="request-detail-dock__title">{{ title }}</span>
    <small class="request-detail-dock__hint">点击展开</small>
  </SideDock>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { CloseButton, DrawerShell, LoadingState, SideDock } from 'nanocat-ui'

import ModalHeader from '@/components/ai/ModalHeader.vue'
import StateBlock from '@/components/ai/StateBlock.vue'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  loading: boolean
  error: string
  loadingTitle: string
  loadingDescription: string
  errorTitle: string
  maxWidth?: string
  rootClass?: string
  zIndex?: number
  detached?: boolean
  minimizable?: boolean
}>(), {
  maxWidth: '54rem',
  rootClass: '',
  zIndex: 130,
  detached: false,
  minimizable: false,
})

const minimized = ref(false)

const emit = defineEmits<{
  (e: 'close'): void
}>()

watch(
  () => props.open,
  (open) => {
    if (!open) minimized.value = false
  },
)
</script>

<style scoped>
.request-detail-drawer {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  overflow: hidden;
}

.request-detail-drawer__state {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.request-detail-drawer__state > * {
  width: 100%;
}

.request-detail-drawer__content {
  min-height: 0;
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 16px 20px 24px;
}

.request-detail-drawer__content > * + * {
  margin-top: 20px;
}

.request-detail-dock__title,
.request-detail-dock__hint {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.request-detail-dock__title {
  font-size: 12px;
  font-weight: 650;
}

.request-detail-dock__hint {
  color: hsl(var(--muted-foreground));
  font-size: 10px;
}
</style>
