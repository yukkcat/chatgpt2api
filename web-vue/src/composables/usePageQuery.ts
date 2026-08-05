import { computed, ref, toValue, watch, type ComputedRef, type MaybeRefOrGetter, type Ref } from 'vue'
import { errorMessage } from '@/lib/errorMessage'

import type { usePageRuntime } from '@/composables/usePageRuntime'

type PageRuntime = ReturnType<typeof usePageRuntime>
type PageQueryErrorMessage = string | ((error: unknown) => string)

type PageQueryOptions = {
  runtime: PageRuntime
  key: string
  loading?: Ref<boolean>
  error?: Ref<string>
  errorMessage?: PageQueryErrorMessage
  isEmpty?: () => boolean
  requireVisible?: boolean
}

type PageQueryRunOptions<T> = {
  before?: () => void
  apply?: (value: T) => void
  onError?: (message: string, error: unknown) => void
  onSettled?: (latest: boolean) => void
  requireVisible?: boolean
  silentError?: boolean
  silentLoading?: boolean
}

type PageDebouncedActionOptions = {
  runtime: PageRuntime
  key: string
  delayMs: number
  action: () => void | Promise<void>
  shouldRun?: () => boolean
  requireVisible?: boolean
}

type VisibilityPollingOptions = {
  runtime: PageRuntime
  key: string
  intervalMs: number | (() => number)
  action: () => void | Promise<void>
  enabled?: () => boolean
  requireVisible?: boolean
}

type SerialVisibilityPollingOptions = VisibilityPollingOptions & {
  immediate?: boolean
}

type PageVisibilityReloadOptions = {
  runtime: PageRuntime
  invalidate: () => void
  reload: () => Promise<void> | void
  shouldReload?: MaybeRefOrGetter<boolean>
}

type PagedQueryOptions<T> = PageQueryOptions & {
  pageSize: Ref<number>
  initialPage?: number
  total?: Ref<number>
  pageCount?: Ref<number>
  fetch: (context: { page: number; pageSize: number }) => Promise<T>
  apply: (value: T) => void
  resolvePage?: (value: T) => number | null | undefined
  resolvePageCount?: (value: T) => number | null | undefined
  resolveTotal?: (value: T) => number | null | undefined
  onError?: (message: string, error: unknown) => void
  onSettled?: (latest: boolean) => void
}

type PagedQueryLoadOptions = {
  silentError?: boolean
  silentLoading?: boolean
}

function resolveErrorMessage(error: unknown, message?: PageQueryErrorMessage): string {
  if (typeof message === 'function') return message(error)
  return errorMessage(error, message || '请求失败')
}

export function usePageQuery(options: PageQueryOptions) {
  const loading = options.loading ?? ref(false)
  const error = options.error ?? ref('')
  const hasResolved = ref(false)
  const hasSnapshot = ref(false)
  let loadingSeq = 0

  const isInitialLoading = computed(() => loading.value && !hasResolved.value)
  const isRefreshing = computed(() => loading.value && hasSnapshot.value)
  const isEmpty = computed(() => hasSnapshot.value && Boolean(options.isEmpty?.()))

  function isLatest(requestSeq: number, requireVisible = options.requireVisible) {
    return options.runtime.isLatestRequest(options.key, requestSeq, { requireVisible })
  }

  async function run<T>(
    task: () => Promise<T>,
    runOptions: PageQueryRunOptions<T> = {},
  ): Promise<T | undefined> {
    const requestSeq = options.runtime.nextRequest(options.key)
    if (runOptions.silentLoading) {
      if (loadingSeq !== 0) {
        loadingSeq = 0
        loading.value = false
      }
    } else {
      loadingSeq = requestSeq
      loading.value = true
    }
    error.value = ''
    runOptions.before?.()
    try {
      const value = await task()
      if (!isLatest(requestSeq, runOptions.requireVisible)) return undefined
      runOptions.apply?.(value)
      hasSnapshot.value = true
      return value
    } catch (caught) {
      if (!isLatest(requestSeq, runOptions.requireVisible)) return undefined
      const message = resolveErrorMessage(caught, options.errorMessage)
      if (!runOptions.silentError) {
        error.value = message
        runOptions.onError?.(message, caught)
      }
      return undefined
    } finally {
      const latest = isLatest(requestSeq, runOptions.requireVisible)
      if (latest && loadingSeq === requestSeq) {
        loading.value = false
        loadingSeq = 0
      }
      if (latest) hasResolved.value = true
      runOptions.onSettled?.(latest)
    }
  }

  function invalidate() {
    options.runtime.invalidateRequest(options.key)
    loadingSeq = 0
    loading.value = false
  }

  return {
    loading,
    error,
    hasResolved,
    isInitialLoading,
    isRefreshing,
    hasSnapshot,
    isEmpty,
    run,
    invalidate,
    isLatest,
  }
}

export function usePageVisibilityReload(options: PageVisibilityReloadOptions) {
  let reloadPending = !options.runtime.isVisible.value

  function invalidateForHide() {
    reloadPending = true
    options.invalidate()
  }

  function reloadIfPending() {
    if (!reloadPending || !options.runtime.canRun.value) return false
    if (options.shouldReload !== undefined && !toValue(options.shouldReload)) return false
    reloadPending = false
    void options.reload()
    return true
  }

  options.runtime.onHide(invalidateForHide)
  options.runtime.onShow(reloadIfPending)
  if (options.shouldReload !== undefined) {
    watch(
      () => toValue(options.shouldReload as MaybeRefOrGetter<boolean>),
      (shouldReload) => {
        if (shouldReload) reloadIfPending()
      },
      { flush: 'sync' },
    )
  }

  return {
    invalidateForHide,
    reloadIfPending,
  }
}

export function usePagedQuery<T>(options: PagedQueryOptions<T>) {
  const query = usePageQuery(options)
  const currentPage = ref(Math.max(1, options.initialPage ?? 1))
  const total = options.total ?? ref(0)
  const pageCount = options.pageCount ?? ref(1)
  const paginationSummary: ComputedRef<{ page: number; pageCount: number; total: number }> = computed(() => ({
    page: currentPage.value,
    pageCount: pageCount.value,
    total: total.value,
  }))
  let suppressNextPageLoad = false

  function normalizePageCount(value: unknown) {
    const count = Math.max(1, Math.trunc(Number(value || 1)))
    return Number.isFinite(count) ? count : 1
  }

  function applyPageBounds() {
    const boundedPage = Math.min(Math.max(1, currentPage.value), pageCount.value)
    if (boundedPage === currentPage.value) return false
    suppressNextPageLoad = true
    currentPage.value = boundedPage
    return true
  }

  async function load(loadOptions: PagedQueryLoadOptions = {}) {
    if (!options.runtime.isActive.value) return undefined
    let shouldReloadBoundedPage = false
    return query.run(
      () => options.fetch({
        page: currentPage.value,
        pageSize: options.pageSize.value,
      }),
      {
        silentError: loadOptions.silentError,
        silentLoading: loadOptions.silentLoading,
        apply: (value) => {
          const nextTotal = options.resolveTotal?.(value)
          if (nextTotal !== undefined && nextTotal !== null) {
            total.value = Math.max(0, Number(nextTotal) || 0)
          }
          const nextPageCount = options.resolvePageCount?.(value)
          if (nextPageCount !== undefined && nextPageCount !== null) {
            pageCount.value = normalizePageCount(nextPageCount)
          }
          const nextPage = options.resolvePage?.(value)
          let responseMovedPage = false
          if (nextPage !== undefined && nextPage !== null) {
            const normalizedPage = Math.max(1, Math.trunc(Number(nextPage) || 1))
            if (normalizedPage !== currentPage.value) {
              suppressNextPageLoad = true
              currentPage.value = normalizedPage
              responseMovedPage = true
            }
          }
          shouldReloadBoundedPage = applyPageBounds() && !responseMovedPage
          options.apply(value)
        },
        onError: options.onError,
        onSettled: options.onSettled,
      },
    ).then((value) => {
      if (shouldReloadBoundedPage && options.runtime.canRun.value) {
        void load({
          silentError: loadOptions.silentError,
          silentLoading: true,
        })
      }
      return value
    })
  }

  function resetAndLoad(loadOptions?: PagedQueryLoadOptions) {
    if (!options.runtime.isActive.value) return
    if (currentPage.value !== 1) {
      currentPage.value = 1
      return
    }
    void load(loadOptions)
  }

  watch(currentPage, () => {
    if (suppressNextPageLoad) {
      suppressNextPageLoad = false
      return
    }
    if (options.runtime.canRun.value) void load()
  })

  watch(pageCount, () => {
    applyPageBounds()
  })

  return {
    ...query,
    currentPage,
    pageCount,
    total,
    paginationSummary,
    load,
    resetAndLoad,
  }
}

export function usePageDebouncedAction(options: PageDebouncedActionOptions) {
  function canRun() {
    return options.runtime.canRun.value && (options.shouldRun?.() ?? true)
  }

  function schedule(delayMs = options.delayMs) {
    if (!canRun()) return
    options.runtime.setTimer(options.key, delayMs, () => {
      if (!canRun()) return
      void options.action()
    }, { requireVisible: options.requireVisible })
  }

  function clear() {
    options.runtime.clearTimer(options.key)
  }

  return {
    schedule,
    clear,
  }
}

export function useVisibilityPolling(options: VisibilityPollingOptions) {
  function intervalMs() {
    const value = typeof options.intervalMs === 'function' ? options.intervalMs() : options.intervalMs
    return Math.max(1, Math.round(Number(value || 1)))
  }

  function canRun() {
    return options.runtime.canRun.value && (options.enabled?.() ?? true)
  }

  function start() {
    stop()
    if (!canRun()) return
    options.runtime.setInterval(options.key, intervalMs(), () => {
      if (!canRun()) {
        stop()
        return
      }
      void options.action()
    }, { requireVisible: options.requireVisible })
  }

  function stop() {
    options.runtime.clearInterval(options.key)
  }

  function restart() {
    start()
  }

  return {
    start,
    stop,
    restart,
    canRun,
  }
}

export function useSerialVisibilityPolling(options: SerialVisibilityPollingOptions) {
  let active = false
  let generation = 0
  let runningGeneration: number | null = null

  function intervalMs() {
    const value = typeof options.intervalMs === 'function' ? options.intervalMs() : options.intervalMs
    return Math.max(1, Math.round(Number(value || 1)))
  }

  function canRun() {
    return active && options.runtime.canRun.value && (options.enabled?.() ?? true)
  }

  async function tick(expectedGeneration = generation) {
    options.runtime.clearTimer(options.key)
    if (!canRun() || expectedGeneration !== generation || runningGeneration === expectedGeneration) return
    runningGeneration = expectedGeneration
    try {
      await options.action()
    } finally {
      if (runningGeneration === expectedGeneration) runningGeneration = null
      if (expectedGeneration === generation) schedule()
    }
  }

  function schedule(delayMs = intervalMs()) {
    options.runtime.clearTimer(options.key)
    if (!canRun()) return
    options.runtime.setTimer(options.key, delayMs, () => {
      void tick()
    }, { requireVisible: options.requireVisible })
  }

  function start() {
    generation += 1
    active = true
    options.runtime.clearTimer(options.key)
    if (!canRun()) return
    if (options.immediate) {
      void tick()
      return
    }
    schedule()
  }

  function stop() {
    generation += 1
    active = false
    options.runtime.clearTimer(options.key)
  }

  return {
    start,
    stop,
    restart: start,
    schedule,
    canRun,
  }
}
