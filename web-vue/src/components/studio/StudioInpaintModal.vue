<template>
  <Teleport to="body">
    <div v-if="source" class="studio-inpaint-backdrop" @click.self="emit('close')">
      <section class="studio-inpaint-modal" role="dialog" aria-modal="true" aria-label="局部修改">
        <ModalHeader
          title="局部修改"
          :subtitle="source.name || '生成图片'"
          heading-tag="h3"
          compact
          @close="emit('close')"
        />

        <div class="studio-inpaint-body">
          <aside class="studio-inpaint-tools">
            <div class="studio-inpaint-group">
              <span class="studio-inpaint-label">工具</span>
              <div class="studio-inpaint-segmented">
                <Button
                  size="sm"
                  :variant="tool === 'rect' ? 'primary' : 'outline'"
                  block
                  root-class="studio-inpaint-tool-button"
                  @click="tool = 'rect'"
                >
                  <Icon icon="lucide:square-dashed" class="h-3.5 w-3.5" />
                  <span>矩形</span>
                </Button>
                <Button
                  size="sm"
                  :variant="tool === 'brush' ? 'primary' : 'outline'"
                  block
                  root-class="studio-inpaint-tool-button"
                  @click="tool = 'brush'"
                >
                  <Icon icon="lucide:brush" class="h-3.5 w-3.5" />
                  <span>画笔</span>
                </Button>
              </div>
            </div>

            <div class="studio-inpaint-group">
              <label class="studio-inpaint-range">
                <span>画笔 <strong>{{ brushSize }}px</strong></span>
                <input v-model.number="brushSize" type="range" min="8" max="160" step="2" />
              </label>
              <label class="studio-inpaint-range">
                <span>羽化 <strong>{{ feather }}px</strong></span>
                <input v-model.number="feather" type="range" min="0" max="96" step="2" />
              </label>
            </div>

            <div class="studio-inpaint-tool-grid">
              <Button
                size="sm"
                :variant="invertSelection ? 'primary' : 'outline'"
                block
                root-class="studio-inpaint-tool-button"
                title="反选区域"
                @click="invertSelection = !invertSelection"
              >
                <Icon icon="lucide:flip-horizontal-2" class="h-3.5 w-3.5" />
                <span>反选</span>
              </Button>
              <Button
                size="sm"
                variant="outline"
                block
                root-class="studio-inpaint-tool-button"
                :disabled="!marks.length"
                title="撤销上一步"
                @click="undoMark"
              >
                <Icon icon="lucide:undo-2" class="h-3.5 w-3.5" />
                <span>撤销</span>
              </Button>
              <Button
                size="sm"
                variant="outline"
                block
                root-class="studio-inpaint-tool-button"
                :disabled="!marks.length"
                title="清空选区"
                @click="clearMarks"
              >
                <Icon icon="lucide:eraser" class="h-3.5 w-3.5" />
                <span>清空</span>
              </Button>
              <Button
                size="sm"
                :variant="showOverlay ? 'primary' : 'outline'"
                block
                root-class="studio-inpaint-tool-button"
                title="显示或隐藏选区"
                @click="showOverlay = !showOverlay"
              >
                <Icon icon="lucide:scan-eye" class="h-3.5 w-3.5" />
                <span>{{ showOverlay ? '隐藏' : '显示' }}</span>
              </Button>
            </div>
          </aside>

          <main class="studio-inpaint-stage-pane">
            <div class="studio-inpaint-stage custom-scrollbar">
              <div class="studio-inpaint-frame">
                <img
                  ref="imageRef"
                  :src="source.src"
                  :alt="source.name || '原图'"
                  crossorigin="anonymous"
                  draggable="false"
                  @load="handleImageLoad"
                />
                <canvas
                  ref="canvasRef"
                  class="studio-inpaint-canvas"
                  :class="{ 'is-hidden': !showOverlay }"
                  @pointerdown.prevent="handlePointerDown"
                  @pointermove.prevent="handlePointerMove"
                  @pointerup.prevent="handlePointerUp"
                  @pointercancel.prevent="handlePointerCancel"
                ></canvas>
              </div>
            </div>
          </main>
        </div>

        <ModalFooter align="between" compact :wrap="false" class="studio-inpaint-footer">
          <Input
            v-model="prompt"
            type="text"
            placeholder="描述局部修改要求"
            root-class="studio-inpaint-prompt-input"
            @keydown.enter.prevent="submit"
          />
          <div class="studio-inpaint-footer-actions">
            <Button
              size="sm"
              variant="outline"
              root-class="studio-inpaint-footer-button"
              :disabled="!marks.length"
              @click="clearMarks"
            >
              清空选区
            </Button>
            <Button
              size="sm"
              variant="primary"
              root-class="studio-inpaint-footer-button"
              :disabled="!canSubmit || submitting"
              @click="submit"
            >
              <Icon :icon="submitting ? 'lucide:loader-circle' : 'lucide:wand-sparkles'" class="h-3.5 w-3.5" :class="{ 'animate-spin': submitting }" />
              <span>提交修改</span>
            </Button>
          </div>
        </ModalFooter>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Button, Input } from 'nanocat-ui'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import type { StudioImageCompareSource } from './types'

type InpaintTool = 'rect' | 'brush'
type Point = { x: number; y: number }
type RectMark = { id: string; type: 'rect'; x: number; y: number; width: number; height: number }
type BrushMark = { id: string; type: 'brush'; points: Point[]; size: number }
type InpaintMark = RectMark | BrushMark

const props = defineProps<{
  source: StudioImageCompareSource | null
}>()

const emit = defineEmits<{
  close: []
  submit: [payload: { prompt: string; markedImage: File }]
}>()

const imageRef = ref<HTMLImageElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const tool = ref<InpaintTool>('rect')
const brushSize = ref(44)
const feather = ref(12)
const invertSelection = ref(false)
const showOverlay = ref(true)
const prompt = ref('')
const marks = ref<InpaintMark[]>([])
const imageWidth = ref(0)
const imageHeight = ref(0)
const submitting = ref(false)

let activePointerId: number | null = null
let startPoint: Point | null = null
let draftRect: RectMark | null = null
let draftBrush: BrushMark | null = null
let overlayRenderFrame = 0

const canSubmit = computed(() => {
  return Boolean(prompt.value.trim() && marks.value.length && imageWidth.value && imageHeight.value)
})

watch(() => props.source?.src, () => {
  resetState()
  void nextTick(() => {
    if (imageRef.value?.complete) handleImageLoad()
  })
})

watch([marks, invertSelection, feather, showOverlay], () => renderOverlay())

function resetState() {
  prompt.value = ''
  marks.value = []
  invertSelection.value = false
  showOverlay.value = true
  activePointerId = null
  startPoint = null
  draftRect = null
  draftBrush = null
}

function markId() {
  return `mark-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function handleImageLoad() {
  const image = imageRef.value
  if (!image) return
  imageWidth.value = image.naturalWidth || image.width
  imageHeight.value = image.naturalHeight || image.height
  syncCanvas()
}

function syncCanvas() {
  const canvas = canvasRef.value
  if (!canvas || !imageWidth.value || !imageHeight.value) return
  canvas.width = imageWidth.value
  canvas.height = imageHeight.value
  renderOverlay()
}

function pointFromEvent(event: PointerEvent): Point | null {
  const canvas = canvasRef.value
  if (!canvas || !imageWidth.value || !imageHeight.value) return null
  const rect = canvas.getBoundingClientRect()
  if (!rect.width || !rect.height) return null
  return {
    x: clamp(((event.clientX - rect.left) / rect.width) * imageWidth.value, 0, imageWidth.value),
    y: clamp(((event.clientY - rect.top) / rect.height) * imageHeight.value, 0, imageHeight.value),
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function handlePointerDown(event: PointerEvent) {
  const point = pointFromEvent(event)
  if (!point || activePointerId !== null) return
  activePointerId = event.pointerId
  startPoint = point
  canvasRef.value?.setPointerCapture(event.pointerId)
  if (tool.value === 'brush') {
    draftBrush = { id: markId(), type: 'brush', points: [point], size: brushSize.value }
  } else {
    draftRect = { id: markId(), type: 'rect', x: point.x, y: point.y, width: 0, height: 0 }
  }
  renderOverlay()
}

function handlePointerMove(event: PointerEvent) {
  if (event.pointerId !== activePointerId) return
  const point = pointFromEvent(event)
  if (!point || !startPoint) return
  if (draftBrush) {
    const previous = draftBrush.points[draftBrush.points.length - 1]
    if (!previous || Math.hypot(point.x - previous.x, point.y - previous.y) >= 2) {
      draftBrush = { ...draftBrush, points: [...draftBrush.points, point] }
    }
  } else if (draftRect) {
    draftRect = rectFromPoints(draftRect.id, startPoint, point)
  }
  renderOverlay()
}

function handlePointerUp(event: PointerEvent) {
  if (event.pointerId !== activePointerId) return
  commitDraft()
  canvasRef.value?.releasePointerCapture(event.pointerId)
  activePointerId = null
  startPoint = null
}

function handlePointerCancel(event: PointerEvent) {
  if (event.pointerId !== activePointerId) return
  draftRect = null
  draftBrush = null
  canvasRef.value?.releasePointerCapture(event.pointerId)
  activePointerId = null
  startPoint = null
  renderOverlay()
}

function rectFromPoints(id: string, start: Point, end: Point): RectMark {
  const x = clamp(Math.min(start.x, end.x), 0, imageWidth.value)
  const y = clamp(Math.min(start.y, end.y), 0, imageHeight.value)
  return {
    id,
    type: 'rect',
    x,
    y,
    width: clamp(Math.abs(end.x - start.x), 0, imageWidth.value - x),
    height: clamp(Math.abs(end.y - start.y), 0, imageHeight.value - y),
  }
}

function commitDraft() {
  if (draftBrush) {
    if (draftBrush.points.length > 1) marks.value = [...marks.value, draftBrush]
    draftBrush = null
  }
  if (draftRect) {
    if (draftRect.width >= 8 && draftRect.height >= 8) marks.value = [...marks.value, draftRect]
    draftRect = null
  }
  renderOverlay()
}

function undoMark() {
  marks.value = marks.value.slice(0, -1)
}

function clearMarks() {
  marks.value = []
  draftRect = null
  draftBrush = null
  renderOverlay()
}

function drawMark(ctx: CanvasRenderingContext2D, mark: InpaintMark) {
  ctx.save()
  ctx.fillStyle = '#fff'
  ctx.strokeStyle = '#fff'
  if (mark.type === 'rect') {
    ctx.fillRect(mark.x, mark.y, mark.width, mark.height)
  } else {
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.lineWidth = mark.size
    ctx.beginPath()
    mark.points.forEach((point, index) => {
      if (index === 0) ctx.moveTo(point.x, point.y)
      else ctx.lineTo(point.x, point.y)
    })
    ctx.stroke()
  }
  ctx.restore()
}

function selectionCanvas(options: { includeDraft?: boolean; blur?: boolean; invert?: boolean } = {}) {
  const base = document.createElement('canvas')
  base.width = imageWidth.value
  base.height = imageHeight.value
  const baseCtx = base.getContext('2d')
  if (!baseCtx) return base

  marks.value.forEach((mark) => drawMark(baseCtx, mark))
  if (options.includeDraft && draftRect) drawMark(baseCtx, draftRect)
  if (options.includeDraft && draftBrush) drawMark(baseCtx, draftBrush)

  let result = base
  if (options.blur && feather.value > 0) {
    const blurred = document.createElement('canvas')
    blurred.width = imageWidth.value
    blurred.height = imageHeight.value
    const blurredCtx = blurred.getContext('2d')
    if (blurredCtx) {
      blurredCtx.filter = `blur(${feather.value}px)`
      blurredCtx.drawImage(base, 0, 0)
      blurredCtx.filter = 'none'
      result = blurred
    }
  }

  if (options.invert && invertSelection.value) {
    const inverted = document.createElement('canvas')
    inverted.width = imageWidth.value
    inverted.height = imageHeight.value
    const invertedCtx = inverted.getContext('2d')
    if (invertedCtx) {
      invertedCtx.fillStyle = '#fff'
      invertedCtx.fillRect(0, 0, imageWidth.value, imageHeight.value)
      invertedCtx.globalCompositeOperation = 'destination-out'
      invertedCtx.drawImage(result, 0, 0)
      invertedCtx.globalCompositeOperation = 'source-over'
      result = inverted
    }
  }

  return result
}

function renderOverlay() {
  if (typeof window === 'undefined') {
    renderOverlayNow()
    return
  }
  if (overlayRenderFrame) return
  overlayRenderFrame = window.requestAnimationFrame(() => {
    overlayRenderFrame = 0
    renderOverlayNow()
  })
}

function renderOverlayNow() {
  const canvas = canvasRef.value
  if (!canvas || !imageWidth.value || !imageHeight.value) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  if (!showOverlay.value) return

  const selection = selectionCanvas({ includeDraft: true, blur: true, invert: true })
  ctx.save()
  ctx.fillStyle = 'rgba(14, 165, 233, 0.38)'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.globalCompositeOperation = 'destination-in'
  ctx.drawImage(selection, 0, 0)
  ctx.restore()

  ctx.save()
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)'
  ctx.lineWidth = Math.max(2, Math.min(imageWidth.value, imageHeight.value) / 640)
  for (const mark of marks.value) {
    if (mark.type === 'rect') ctx.strokeRect(mark.x, mark.y, mark.width, mark.height)
  }
  if (draftRect) ctx.strokeRect(draftRect.x, draftRect.y, draftRect.width, draftRect.height)
  ctx.restore()
}

function canvasBlob(canvas: HTMLCanvasElement) {
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob)
      else reject(new Error('标记图生成失败'))
    }, 'image/png')
  })
}

function paintSelectionMarker(ctx: CanvasRenderingContext2D) {
  const selected = selectionCanvas({ blur: true, invert: true })
  ctx.save()
  ctx.fillStyle = 'rgba(14, 165, 233, 0.48)'
  ctx.fillRect(0, 0, imageWidth.value, imageHeight.value)
  ctx.globalCompositeOperation = 'destination-in'
  ctx.drawImage(selected, 0, 0)
  ctx.restore()

  ctx.save()
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.96)'
  ctx.lineWidth = Math.max(3, Math.min(imageWidth.value, imageHeight.value) / 480)
  for (const mark of marks.value) {
    if (mark.type === 'rect') ctx.strokeRect(mark.x, mark.y, mark.width, mark.height)
  }
  ctx.restore()
}

async function createMarkedImageFile() {
  const image = imageRef.value
  if (!image) throw new Error('原图未加载')
  const output = document.createElement('canvas')
  output.width = imageWidth.value
  output.height = imageHeight.value
  const ctx = output.getContext('2d')
  if (!ctx) throw new Error('浏览器不支持标记画布')
  ctx.drawImage(image, 0, 0, output.width, output.height)
  paintSelectionMarker(ctx)
  const blob = await canvasBlob(output)
  return new File([blob], 'marked-edit-region.png', { type: 'image/png' })
}

async function submit() {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  try {
    const markedImage = await createMarkedImageFile()
    emit('submit', { prompt: prompt.value.trim(), markedImage })
  } finally {
    submitting.value = false
  }
}

onBeforeUnmount(() => {
  if (overlayRenderFrame && typeof window !== 'undefined') {
    window.cancelAnimationFrame(overlayRenderFrame)
    overlayRenderFrame = 0
  }
})
</script>

<style scoped>
.studio-inpaint-backdrop {
  position: fixed;
  inset: 0;
  z-index: 220;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(0 0 0 / 0.4);
  padding: clamp(0.75rem, 2vw, 1.25rem);
}

.studio-inpaint-modal {
  display: flex;
  width: min(100%, 64rem);
  height: min(100%, 44rem);
  min-height: 31rem;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 0.82);
  border-radius: 16px;
  background: hsl(var(--card));
  box-shadow: 0 36px 120px -45px rgb(16 24 40 / 0.4);
}

.studio-inpaint-body {
  display: grid;
  min-height: 0;
  flex: 1 1 auto;
  grid-template-columns: 14rem minmax(0, 1fr);
  background: hsl(var(--background));
}

.studio-inpaint-tools {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: 0.85rem;
  overflow-y: auto;
  border-right: 1px solid hsl(var(--border) / 0.72);
  background: hsl(var(--card));
  padding: 0.85rem;
}

.studio-inpaint-group {
  display: grid;
  gap: 0.5rem;
}

.studio-inpaint-label {
  color: hsl(var(--muted-foreground));
  font-size: 0.72rem;
  font-weight: 750;
}

.studio-inpaint-segmented,
.studio-inpaint-tool-grid {
  display: grid;
  gap: 0.4rem;
}

.studio-inpaint-segmented,
.studio-inpaint-tool-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.studio-inpaint-tool-button {
  min-width: 0;
}

.studio-inpaint-range {
  display: grid;
  gap: 0.3rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.72rem;
  font-weight: 650;
}

.studio-inpaint-range span {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}

.studio-inpaint-range strong {
  color: hsl(var(--foreground));
}

.studio-inpaint-range input {
  width: 100%;
  accent-color: hsl(var(--foreground));
}

.studio-inpaint-stage-pane {
  min-width: 0;
  min-height: 0;
  padding: 0.75rem;
}

.studio-inpaint-stage {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  align-items: center;
  justify-content: center;
  overflow: auto;
  border: 1px solid hsl(var(--border) / 0.72);
  border-radius: 0.9rem;
  background: hsl(var(--muted) / 0.24);
  padding: 0.75rem;
}

.studio-inpaint-frame {
  position: relative;
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 0.72);
  border-radius: 0.9rem;
  background: hsl(var(--background));
  line-height: 0;
}

.studio-inpaint-frame img {
  display: block;
  max-width: min(100%, 44rem);
  max-height: min(58vh, 31rem);
  user-select: none;
}

.studio-inpaint-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  cursor: crosshair;
  touch-action: none;
}

.studio-inpaint-canvas.is-hidden {
  opacity: 0;
}

.studio-inpaint-footer {
  min-height: 3.1rem;
  flex-wrap: nowrap;
  background: hsl(var(--card));
}

.studio-inpaint-prompt-input {
  width: auto;
  min-width: 0;
  flex: 1 1 16rem;
}

.studio-inpaint-footer-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.studio-inpaint-footer-button {
  white-space: nowrap;
}

@media (max-width: 760px) {
  .studio-inpaint-modal {
    height: min(100%, 56rem);
  }

  .studio-inpaint-body {
    grid-template-columns: 1fr;
  }

  .studio-inpaint-tools {
    max-height: 12.5rem;
    border-right: 0;
    border-bottom: 1px solid hsl(var(--border));
  }

  .studio-inpaint-footer {
    flex-wrap: wrap;
  }

  .studio-inpaint-prompt-input {
    width: 100%;
    flex-basis: 100%;
  }

  .studio-inpaint-footer-actions {
    width: 100%;
  }
}
</style>
