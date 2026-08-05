<template>
  <Teleport to="body">
    <transition :name="transitionName">
      <div
        v-if="selectedCount > 0"
        class="selection-bulk-bar-host"
        :style="{ zIndex }"
      >
        <div
          class="selection-bulk-bar"
          :class="`selection-bulk-bar--${density}`"
          :style="{ maxWidth }"
        >
          <div class="selection-bulk-bar__summary">
            <slot name="summary">
              <p class="selection-bulk-bar__title">{{ resolvedSummary }}</p>
            </slot>
          </div>
          <ActionRow
            class="selection-bulk-bar__actions"
            justify="end"
            gap="tight"
            mobile-justify="start"
          >
            <slot />
          </ActionRow>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ActionRow from './ActionRow.vue'

const props = withDefaults(defineProps<{
  selectedCount: number
  summaryText?: string
  maxWidth?: string
  transitionName?: string
  density?: 'compact' | 'normal'
  zIndex?: number
}>(), {
  summaryText: '',
  maxWidth: '34rem',
  transitionName: 'selection-bulk-bar',
  density: 'normal',
  zIndex: 130,
})

const resolvedSummary = computed(() => props.summaryText || `已选择 ${props.selectedCount} 项`)
</script>

<style scoped>
.selection-bulk-bar-host {
  position: fixed;
  inset-inline: 0;
  bottom: 20px;
  display: flex;
  justify-content: center;
  padding-inline: 16px;
  pointer-events: none;
}

.selection-bulk-bar {
  display: flex;
  width: 100%;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
  background: hsl(var(--card) / 0.96);
  padding: 10px 12px 10px 16px;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.18);
  backdrop-filter: blur(10px);
  pointer-events: auto;
}

.selection-bulk-bar--compact {
  gap: 10px;
  padding-block: 9px;
}

.selection-bulk-bar__summary {
  min-width: 0;
}

.selection-bulk-bar__title {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 600;
}

.selection-bulk-bar__actions {
  min-width: 0;
  flex-wrap: nowrap;
}

.selection-bulk-bar-enter-active,
.selection-bulk-bar-leave-active {
  transition: opacity 0.16s ease;
}

.selection-bulk-bar-enter-from,
.selection-bulk-bar-leave-to {
  opacity: 0;
}

@media (max-width: 640px) {
  .selection-bulk-bar-host {
    bottom: 12px;
    padding-inline: 12px;
  }

  .selection-bulk-bar {
    flex-wrap: wrap;
    align-items: stretch;
    border-radius: var(--radius, 12px);
    padding: 12px;
  }

  .selection-bulk-bar__actions {
    width: 100%;
    flex-wrap: wrap;
  }
}
</style>
