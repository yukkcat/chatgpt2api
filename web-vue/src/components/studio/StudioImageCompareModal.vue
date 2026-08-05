<template>
  <Teleport to="body">
    <div v-if="compare" class="studio-compare-backdrop" @click.self="emit('close')">
      <section class="studio-compare-modal" role="dialog" aria-modal="true" aria-label="图片对比">
        <ModalHeader
          title="图片对比"
          :subtitle="`${compare.before.name} / ${compare.after.name}`"
          heading-tag="h3"
          compact
          @close="emit('close')"
        >
          <template #actions>
            <div class="studio-compare-mode" role="group" aria-label="对比模式">
              <Button
                size="sm"
                :variant="mode === 'slider' ? 'primary' : 'outline'"
                root-class="studio-compare-mode-button"
                :aria-pressed="mode === 'slider'"
                title="滑杆对比"
                @click="mode = 'slider'"
              >
                <Icon icon="lucide:sliders-horizontal" class="h-3.5 w-3.5" />
                <span>滑杆</span>
              </Button>
              <Button
                size="sm"
                :variant="mode === 'side-by-side' ? 'primary' : 'outline'"
                root-class="studio-compare-mode-button"
                :aria-pressed="mode === 'side-by-side'"
                title="并排对比"
                @click="mode = 'side-by-side'"
              >
                <Icon icon="lucide:columns-2" class="h-3.5 w-3.5" />
                <span>并排</span>
              </Button>
            </div>
          </template>
        </ModalHeader>

        <div class="studio-compare-body">
          <div
            v-if="mode === 'slider'"
            ref="stageRef"
            class="studio-compare-stage"
            :class="{ 'is-dragging': draggingPointerId !== null }"
            @pointerdown.prevent="handleStagePointerDown"
            @pointermove.prevent="handleStagePointerMove"
            @pointerup.prevent="handleStagePointerUp"
            @pointercancel.prevent="handleStagePointerCancel"
          >
            <img class="studio-compare-image" :src="compare.before.src" :alt="compare.before.name || '原图'" draggable="false" />
            <div class="studio-compare-after" :style="{ clipPath: `inset(0 ${100 - split}% 0 0)` }">
              <img class="studio-compare-image" :src="compare.after.src" :alt="compare.after.name || '新图'" draggable="false" />
            </div>
            <div
              class="studio-compare-divider"
              role="slider"
              tabindex="0"
              aria-label="对比位置"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuenow="split"
              :style="{ left: `${split}%` }"
              @keydown="handleDividerKeydown"
            >
              <span><Icon icon="lucide:columns-2" class="h-3.5 w-3.5" /></span>
            </div>
          </div>

          <div v-else class="studio-compare-side-by-side">
            <figure class="studio-compare-panel">
              <div class="studio-compare-panel-media">
                <img :src="compare.before.src" :alt="compare.before.name || '原图'" draggable="false" />
              </div>
              <figcaption>原图</figcaption>
            </figure>
            <figure class="studio-compare-panel">
              <div class="studio-compare-panel-media">
                <img :src="compare.after.src" :alt="compare.after.name || '新图'" draggable="false" />
              </div>
              <figcaption>新图</figcaption>
            </figure>
          </div>
        </div>

        <ModalFooter align="center" compact class="studio-compare-footer">
          <template v-if="mode === 'slider'">
            <span>原图</span>
            <input v-model.number="split" type="range" min="0" max="100" step="1" aria-label="对比位置" />
            <span>新图</span>
          </template>
          <template v-else>
            <span class="studio-compare-legend-item">
              <i aria-hidden="true"></i>
              原图
            </span>
            <span class="studio-compare-legend-item is-after">
              <i aria-hidden="true"></i>
              新图
            </span>
          </template>
        </ModalFooter>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { ref, watch } from 'vue'
import { Button } from 'nanocat-ui'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import type { StudioImageComparePreview } from './types'

type CompareMode = 'slider' | 'side-by-side'

const props = defineProps<{
  compare: StudioImageComparePreview | null
}>()

const emit = defineEmits<{
  close: []
}>()

const split = ref(50)
const mode = ref<CompareMode>('slider')
const stageRef = ref<HTMLElement | null>(null)
const draggingPointerId = ref<number | null>(null)

watch(() => props.compare, () => {
  split.value = 50
  mode.value = 'slider'
  draggingPointerId.value = null
})

function clampSplit(value: number) {
  return Math.min(100, Math.max(0, Math.round(value)))
}

function updateSplitFromEvent(event: PointerEvent) {
  const stage = stageRef.value
  if (!stage) return
  const rect = stage.getBoundingClientRect()
  if (!rect.width) return
  split.value = clampSplit(((event.clientX - rect.left) / rect.width) * 100)
}

function handleStagePointerDown(event: PointerEvent) {
  if (draggingPointerId.value !== null) return
  draggingPointerId.value = event.pointerId
  stageRef.value?.setPointerCapture(event.pointerId)
  updateSplitFromEvent(event)
}

function handleStagePointerMove(event: PointerEvent) {
  if (event.pointerId !== draggingPointerId.value) return
  updateSplitFromEvent(event)
}

function finishStageDrag(event: PointerEvent) {
  if (event.pointerId !== draggingPointerId.value) return
  stageRef.value?.releasePointerCapture(event.pointerId)
  draggingPointerId.value = null
}

function handleStagePointerUp(event: PointerEvent) {
  finishStageDrag(event)
}

function handleStagePointerCancel(event: PointerEvent) {
  finishStageDrag(event)
}

function handleDividerKeydown(event: KeyboardEvent) {
  const largeStep = event.shiftKey ? 10 : 1
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    split.value = clampSplit(split.value - largeStep)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    split.value = clampSplit(split.value + largeStep)
  } else if (event.key === 'Home') {
    event.preventDefault()
    split.value = 0
  } else if (event.key === 'End') {
    event.preventDefault()
    split.value = 100
  }
}
</script>

<style scoped>
.studio-compare-backdrop {
  position: fixed;
  inset: 0;
  z-index: 221;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(0 0 0 / 0.4);
  padding: clamp(0.75rem, 2vw, 1.25rem);
}

.studio-compare-modal {
  display: flex;
  width: min(100%, 64rem);
  height: min(100%, 44rem);
  min-height: 28rem;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 0.82);
  border-radius: 16px;
  background: hsl(var(--card));
  box-shadow: 0 36px 120px -45px rgb(16 24 40 / 0.4);
}

.studio-compare-mode {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.studio-compare-mode-button {
  min-width: 0;
}

.studio-compare-body {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  align-items: center;
  justify-content: center;
  overflow: auto;
  background: hsl(var(--background));
  padding: 0.75rem;
}

.studio-compare-stage {
  position: relative;
  width: min(100%, 54rem);
  height: min(100%, 34rem);
  min-height: 18rem;
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 0.72);
  border-radius: 0.9rem;
  background: hsl(var(--background));
  cursor: ew-resize;
  touch-action: none;
  user-select: none;
}

.studio-compare-stage.is-dragging {
  cursor: grabbing;
}

.studio-compare-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.studio-compare-after {
  position: absolute;
  inset: 0;
}

.studio-compare-divider {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  transform: translateX(-1px);
  background: hsl(var(--background));
  box-shadow: 0 0 0 1px rgb(15 23 42 / 0.25);
  cursor: ew-resize;
  outline: none;
  touch-action: none;
}

.studio-compare-divider:focus-visible span {
  border-color: hsl(var(--foreground) / 0.32);
  box-shadow: 0 0 0 3px hsl(var(--foreground) / 0.08), 0 10px 28px rgb(15 23 42 / 0.28);
}

.studio-compare-divider span {
  position: absolute;
  top: 50%;
  left: 50%;
  display: inline-flex;
  width: 2rem;
  height: 2rem;
  transform: translate(-50%, -50%);
  align-items: center;
  justify-content: center;
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
  background: hsl(var(--background));
  color: hsl(var(--foreground));
  box-shadow: 0 10px 28px rgb(15 23 42 / 0.28);
}

.studio-compare-side-by-side {
  display: grid;
  width: min(100%, 58rem);
  height: min(100%, 34rem);
  min-height: 18rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.studio-compare-panel {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  gap: 0.45rem;
  margin: 0;
}

.studio-compare-panel-media {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 0.72);
  border-radius: 0.9rem;
  background: hsl(var(--background));
}

.studio-compare-panel-media img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.studio-compare-panel figcaption {
  flex: 0 0 auto;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
  font-weight: 750;
  text-align: center;
}

.studio-compare-footer {
  min-height: 3.1rem;
  background: hsl(var(--card));
  color: hsl(var(--muted-foreground));
  font-size: 0.78rem;
  font-weight: 700;
}

.studio-compare-footer input {
  min-width: 0;
  flex: 1 1 auto;
  accent-color: hsl(var(--foreground));
}

.studio-compare-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.studio-compare-legend-item i {
  display: inline-block;
  width: 0.55rem;
  height: 0.55rem;
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
  background: hsl(var(--background));
}

.studio-compare-legend-item.is-after i {
  background: hsl(var(--foreground));
}

@media (max-width: 760px) {
  .studio-compare-modal {
    min-height: 24rem;
  }

  .studio-compare-mode-button span {
    display: none;
  }

  .studio-compare-stage {
    min-height: 16rem;
  }

  .studio-compare-side-by-side {
    min-height: 18rem;
    grid-template-columns: 1fr;
  }
}
</style>
