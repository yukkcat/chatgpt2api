import { nextTick, reactive } from 'vue'

export type OperationProgressTone = 'info' | 'success' | 'warning' | 'danger'

export interface OperationTimelineEvent {
  key: string
  timestamp: string
  label: string
  message: string
  tone: OperationProgressTone
}

export interface OperationTimelineEventInput {
  timestamp?: string
  label?: string
  message: string
  tone?: OperationProgressTone
}

export interface OperationSummaryItem {
  key: string
  label: string
  value: string | number
  tone?: Exclude<OperationProgressTone, 'info'>
}

export interface OperationProgressState {
  open: boolean
  title: string
  subtitle: string
  total: number
  current: number
  statusLabel: string
  message: string
  error: string
  busy: boolean
  tone: OperationProgressTone
  events: OperationTimelineEvent[]
}

export interface OperationProgressStart {
  title: string
  subtitle?: string
  total?: number
  message?: string
}

export function useOperationProgressRuntime() {
  let operationRevision = 0
  let eventSequence = 0

  const state = reactive<OperationProgressState>({
    open: false,
    title: '',
    subtitle: '',
    total: 0,
    current: 0,
    statusLabel: '已处理',
    message: '',
    error: '',
    busy: false,
    tone: 'info',
    events: [],
  })

  function record(input: OperationTimelineEventInput) {
    const message = String(input.message || '').trim()
    if (!message) return null
    eventSequence += 1
    const rawTimestamp = String(input.timestamp || '').trim()
    const timestamp = rawTimestamp && !Number.isNaN(Date.parse(rawTimestamp))
      ? rawTimestamp
      : new Date().toISOString()
    const event: OperationTimelineEvent = {
      key: `operation:${operationRevision}:${eventSequence}`,
      timestamp,
      label: String(input.label || '任务').trim() || '任务',
      message,
      tone: input.tone || 'info',
    }
    state.events.push(event)
    if (state.events.length > 200) state.events.splice(0, state.events.length - 200)
    return event
  }

  async function waitForPresentation() {
    await nextTick()
    if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') return
    await new Promise<void>((resolve) => {
      let settled = false
      const finish = () => {
        if (settled) return
        settled = true
        window.clearTimeout(fallbackTimer)
        resolve()
      }
      const fallbackTimer = window.setTimeout(finish, 80)
      window.requestAnimationFrame(() => window.requestAnimationFrame(finish))
    })
  }

  async function start(input: OperationProgressStart) {
    operationRevision += 1
    eventSequence = 0
    state.open = true
    state.title = input.title
    state.subtitle = input.subtitle || ''
    state.total = input.total === undefined ? 1 : Math.max(0, Number(input.total || 0))
    state.current = 0
    state.statusLabel = '处理中'
    state.message = input.message || ''
    state.error = ''
    state.busy = true
    state.tone = 'info'
    state.events = []
    record({
      label: '开始处理',
      message: input.message || `${input.title}已开始`,
      tone: 'info',
    })
    await waitForPresentation()
  }

  function succeed(message: string, current = state.total) {
    state.current = Math.max(0, Number(current || 0))
    state.statusLabel = '已完成'
    state.message = message
    state.error = ''
    state.busy = false
    state.tone = 'success'
    record({ label: '已完成', message, tone: 'success' })
  }

  function warn(message: string, current = state.total) {
    state.current = Math.max(0, Number(current || 0))
    state.statusLabel = '部分完成'
    state.message = message
    state.error = ''
    state.busy = false
    state.tone = 'warning'
    record({ label: '部分完成', message, tone: 'warning' })
  }

  function fail(error: string, current = state.current) {
    state.current = Math.max(0, Number(current || 0))
    state.statusLabel = '失败'
    state.error = error
    state.busy = false
    state.tone = 'danger'
    record({ label: '失败', message: error, tone: 'danger' })
  }

  function close() {
    if (state.busy) return false
    state.open = false
    return true
  }

  function reset() {
    state.open = false
    state.busy = false
    state.events = []
  }

  return {
    state,
    start,
    succeed,
    warn,
    fail,
    record,
    close,
    reset,
  }
}
