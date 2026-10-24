import { getCurrentScope, onScopeDispose } from 'vue'

import {
  accountImportsApi,
  type CPAImportJob,
  type RemoteAccountImportStarted,
} from '@/api/accountImports'
import type { useAccountBulkProgressRuntime } from './accountBulkProgressRuntime'

export interface RemoteAccountImportProgress {
  title: string
  total: number
  job?: CPAImportJob | null
  error?: string
}

type RemoteAccountImportTrackingRuntimeOptions = {
  bulkProgress: ReturnType<typeof useAccountBulkProgressRuntime>
  onFinished?: () => Promise<void> | void
  trackingWindowMs?: (total: number) => number
}

const REMOTE_IMPORT_MIN_TRACKING_MS = 30 * 60 * 1000
const REMOTE_IMPORT_MAX_TRACKING_MS = 2 * 60 * 60 * 1000
const REMOTE_IMPORT_PER_ACCOUNT_TRACKING_MS = 30 * 1000

export function remoteImportTrackingWindowMs(total: number) {
  return Math.min(
    REMOTE_IMPORT_MAX_TRACKING_MS,
    Math.max(REMOTE_IMPORT_MIN_TRACKING_MS, Math.max(0, total) * REMOTE_IMPORT_PER_ACCOUNT_TRACKING_MS),
  )
}

export function remoteImportPollDelayMs(elapsedMs: number, consecutiveFailures = 0) {
  const normalDelay = elapsedMs < 60_000 ? 1_000 : elapsedMs < 5 * 60_000 ? 2_000 : 5_000
  if (consecutiveFailures <= 0) return normalDelay
  return Math.min(10_000, Math.max(normalDelay, 1_000 * (2 ** Math.min(3, consecutiveFailures - 1))))
}

export function useRemoteAccountImportTrackingRuntime(
  options: RemoteAccountImportTrackingRuntimeOptions,
) {
  let remoteImportJobId = ''
  let remoteImportTrackingKey = ''
  let remoteImportTrackingRevision = 0
  let lastRemoteImportRequest: RemoteAccountImportStarted | null = null

  function waitForPoll(delayMs: number) {
    return new Promise<void>((resolve) => window.setTimeout(resolve, delayMs))
  }

  function notifyFinished() {
    void Promise.resolve(options.onFinished?.()).catch(() => {})
  }

  async function updateProgress(value: RemoteAccountImportProgress) {
    const total = Math.max(0, Number(value.total || value.job?.total || 0))
    const jobId = String(value.job?.job_id || '').trim()
    if (!options.bulkProgress.batchBusy.value || (jobId && remoteImportJobId && jobId !== remoteImportJobId)) {
      remoteImportJobId = jobId
      await options.bulkProgress.start(value.title, total, 'import')
    } else if (jobId) {
      remoteImportJobId = jobId
    }

    if (value.error) {
      options.bulkProgress.finish({
        total,
        processed: Number(options.bulkProgress.refreshProgress.value?.processed || 0),
        stage: 'completed',
        stage_label: 'Completed',
        status_label: 'Failed',
        tone: 'danger',
        error: value.error,
        import_result: { added: 0, skipped: 0, synced: 0, failed: 1 },
      })
      options.bulkProgress.end()
      return true
    }

    const job = value.job
    if (!job) {
      options.bulkProgress.update({
        total,
        processed: 0,
        stage: 'read_credentials',
        stage_label: 'Creating job',
        status_label: 'Creating job',
        tone: 'info',
      })
      return false
    }

    const progress = {
      total: job.progress_total,
      processed: job.progress_completed,
      stage: job.stage,
      stage_label: job.stage_label,
      status_label: job.status_label,
      tone: job.tone,
      message: job.result_message,
      error: job.error || null,
      summary_items: job.summary_items,
      events: job.events || [],
      import_result: {
        added: job.added,
        skipped: job.skipped,
        synced: job.synced,
        failed: job.failed_total,
      },
    }
    if (job.terminal) {
      options.bulkProgress.finish(progress)
      options.bulkProgress.end()
      return true
    }

    options.bulkProgress.update(progress)
    return false
  }

  function requestImportJob(mode: RemoteAccountImportStarted['mode'], sourceId: string) {
    return mode === 'cpa'
      ? accountImportsApi.getCPAImportJob(sourceId)
      : accountImportsApi.getSub2APIImportJob(sourceId)
  }

  async function finishTracking(
    request: RemoteAccountImportStarted,
    job: CPAImportJob,
    revision: number,
  ) {
    if (revision !== remoteImportTrackingRevision) return
    remoteImportTrackingKey = ''
    lastRemoteImportRequest = null
    await updateProgress({ ...request, job })
    notifyFinished()
  }

  async function pollImportJob(request: RemoteAccountImportStarted, revision: number) {
    const startedAt = Date.now()
    const deadline = startedAt + (options.trackingWindowMs || remoteImportTrackingWindowMs)(request.total)
    let consecutiveFailures = 0

    while (revision === remoteImportTrackingRevision && Date.now() < deadline) {
      try {
        const response = await requestImportJob(request.mode, request.source_id)
        if (revision !== remoteImportTrackingRevision) return
        consecutiveFailures = 0
        const job = response.import_job || null
        if (job?.terminal) {
          await finishTracking(request, job, revision)
          return
        }
        await updateProgress({ ...request, job })
      } catch {
        if (revision !== remoteImportTrackingRevision) return
        consecutiveFailures += 1
        const current = options.bulkProgress.refreshProgress.value
        options.bulkProgress.update({
          ...(current || {}),
          total: Math.max(0, Number(current?.total || request.total)),
          processed: Math.max(0, Number(current?.processed || 0)),
          done: false,
          stage_label: 'Connection interrupted; retrying',
          status_label: 'Connection interrupted; retrying',
          tone: 'warning',
        })
      }

      await waitForPoll(remoteImportPollDelayMs(Date.now() - startedAt, consecutiveFailures))
    }

    if (revision !== remoteImportTrackingRevision) return
    remoteImportTrackingKey = ''
    const current = options.bulkProgress.refreshProgress.value
    options.bulkProgress.update({
      ...(current || {}),
      total: Math.max(0, Number(current?.total || request.total)),
      processed: Math.max(0, Number(current?.processed || 0)),
      done: false,
      stage_label: 'Continuing in the background',
      status_label: 'Continuing in the background',
      tone: 'info',
    })
    options.bulkProgress.end()
  }

  async function start(request: RemoteAccountImportStarted) {
    const sourceId = request.source_id.trim()
    if (!sourceId) return
    const jobId = String(request.job?.job_id || '').trim()
    const trackingKey = `${request.mode}:${sourceId}:${jobId}`
    if (trackingKey === remoteImportTrackingKey) return

    remoteImportTrackingRevision += 1
    const revision = remoteImportTrackingRevision
    remoteImportTrackingKey = trackingKey
    const normalizedRequest = { ...request, source_id: sourceId }
    lastRemoteImportRequest = normalizedRequest
    const terminal = await updateProgress(normalizedRequest)
    if (terminal && request.job) {
      remoteImportTrackingKey = ''
      lastRemoteImportRequest = null
      notifyFinished()
      return
    }
    void pollImportJob(normalizedRequest, revision)
  }

  function stop() {
    remoteImportTrackingRevision += 1
    remoteImportTrackingKey = ''
  }

  async function resume() {
    if (remoteImportTrackingKey) return
    if (lastRemoteImportRequest) {
      await start(lastRemoteImportRequest)
      return
    }
    try {
      const [poolsResult, serversResult] = await Promise.allSettled([
        accountImportsApi.listCPAPools(),
        accountImportsApi.listSub2APIServers(),
      ])
      const candidates: Array<RemoteAccountImportStarted & { updatedAt: number }> = []
      if (poolsResult.status === 'fulfilled') {
        for (const pool of poolsResult.value.pools || []) {
          const job = pool.import_job
          if (!job || (!['pending', 'running'].includes(job.status) && job.job_id !== remoteImportJobId)) continue
          candidates.push({
            mode: 'cpa',
            source_id: pool.id,
            title: 'Import remote CPA',
            total: job.total,
            job,
            updatedAt: Date.parse(job.updated_at || job.created_at || '') || 0,
          })
        }
      }
      if (serversResult.status === 'fulfilled') {
        for (const server of serversResult.value.servers || []) {
          const job = server.import_job
          if (!job || (!['pending', 'running'].includes(job.status) && job.job_id !== remoteImportJobId)) continue
          candidates.push({
            mode: 'sub2api',
            source_id: server.id,
            title: 'Import Sub2API accounts',
            total: job.total,
            job,
            updatedAt: Date.parse(job.updated_at || job.created_at || '') || 0,
          })
        }
      }
      const latest = candidates.sort((left, right) => right.updatedAt - left.updatedAt)[0]
      if (latest) await start(latest)
    } catch {
      // Account and settings pages remain usable when persisted progress is unavailable.
    }
  }

  if (getCurrentScope()) onScopeDispose(stop)

  return {
    updateProgress,
    start,
    stop,
    resume,
  }
}
