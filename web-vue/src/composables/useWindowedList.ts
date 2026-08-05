import { computed, nextTick, onBeforeUnmount, ref, watch, type ComputedRef, type Ref } from 'vue'

export interface WindowedListEntry<T> {
  item: T
  index: number
}

interface WindowedListOptions<T> {
  items: Ref<readonly T[]> | ComputedRef<readonly T[]>
  itemHeight: number
  getItemHeight?: (item: T, index: number) => number
  overscan?: number
  disabled?: Ref<boolean> | ComputedRef<boolean>
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export function useWindowedList<T>(options: WindowedListOptions<T>) {
  const scrollTop = ref(0)
  const viewportHeight = ref(0)
  const overscan = Math.max(0, options.overscan ?? 6)
  let scrollElement: HTMLElement | null = null
  let resizeObserver: ResizeObserver | null = null
  let scrollFrameId: number | null = null

  const isDisabled = computed(() => Boolean(options.disabled?.value))
  const itemMetrics = computed(() => {
    const items = options.items.value
    const offsets = new Array<number>(items.length + 1)
    let total = 0
    offsets[0] = 0
    items.forEach((item, index) => {
      const rawHeight = options.getItemHeight?.(item, index) ?? options.itemHeight
      const height = Number.isFinite(rawHeight) && rawHeight > 0 ? rawHeight : options.itemHeight
      total += height
      offsets[index + 1] = total
    })
    return { offsets, total }
  })
  const totalHeight = computed(() => itemMetrics.value.total)
  const startIndex = computed(() => {
    if (isDisabled.value) return 0
    return clampNumber(findOffsetIndex(itemMetrics.value.offsets, scrollTop.value) - overscan, 0, options.items.value.length)
  })
  const endIndex = computed(() => {
    if (isDisabled.value) return options.items.value.length
    const viewportEnd = scrollTop.value + viewportHeight.value
    const visibleEnd = findOffsetIndex(itemMetrics.value.offsets, viewportEnd) + 1
    return clampNumber(visibleEnd + overscan, startIndex.value, options.items.value.length)
  })
  const topSpacerHeight = computed(() => isDisabled.value ? 0 : itemMetrics.value.offsets[startIndex.value] || 0)
  const bottomSpacerHeight = computed(() => {
    if (isDisabled.value) return 0
    return Math.max(0, totalHeight.value - (itemMetrics.value.offsets[endIndex.value] || 0))
  })
  const visibleItems = computed<WindowedListEntry<T>[]>(() => {
    const items = options.items.value
    if (isDisabled.value) return items.map((item, index) => ({ item, index }))
    return items.slice(startIndex.value, endIndex.value).map((item, offset) => ({
      item,
      index: startIndex.value + offset,
    }))
  })

  function updateFromElement(element = scrollElement) {
    if (!element) return
    scrollTop.value = element.scrollTop
    viewportHeight.value = element.clientHeight
  }

  function scheduleUpdateFromElement(element = scrollElement) {
    if (!element) return
    scrollElement = element
    if (scrollFrameId !== null) return
    scrollFrameId = window.requestAnimationFrame(() => {
      scrollFrameId = null
      updateFromElement()
    })
  }

  function handleScroll(event: Event) {
    scheduleUpdateFromElement(event.currentTarget as HTMLElement | null)
  }

  function setScrollElement(element: HTMLElement | null) {
    if (scrollElement === element) {
      updateFromElement(element)
      return
    }
    resizeObserver?.disconnect()
    resizeObserver = null
    scrollElement = element
    updateFromElement(element)
    if (element && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => updateFromElement(element))
      resizeObserver.observe(element)
    }
  }

  watch(() => options.items.value.length, () => {
    void nextTick(() => updateFromElement())
  }, { flush: 'post' })

  onBeforeUnmount(() => {
    if (scrollFrameId !== null) {
      window.cancelAnimationFrame(scrollFrameId)
      scrollFrameId = null
    }
    resizeObserver?.disconnect()
    resizeObserver = null
    scrollElement = null
  })

  return {
    visibleItems,
    topSpacerHeight,
    bottomSpacerHeight,
    handleScroll,
    setScrollElement,
    refreshWindow: updateFromElement,
  }
}

function findOffsetIndex(offsets: readonly number[], value: number) {
  if (offsets.length <= 1) return 0
  let low = 0
  let high = offsets.length - 1
  while (low < high) {
    const mid = Math.floor((low + high + 1) / 2)
    if ((offsets[mid] || 0) <= value) low = mid
    else high = mid - 1
  }
  return clampNumber(low, 0, offsets.length - 2)
}
