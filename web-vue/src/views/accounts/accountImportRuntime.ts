import { getCurrentScope, nextTick, onScopeDispose, ref } from 'vue'

import { accountsApi, type AccountImportPayload, type AccountSourceType } from '@/api/accounts'
import {
  accountImportsApi,
  type CPAImportJob,
  type RemoteAccountImportStarted,
} from '@/api/accountImports'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import type { useAccountBulkProgressRuntime } from './accountBulkProgressRuntime'

export const ACCOUNT_IMPORT_MODE_CATALOG = [
  { label: 'OAuth 登录已有账号', value: 'oauth_login' },
  { label: '导入完整备份文件', value: 'backup_json' },
  { label: '导入 Access Token', value: 'access_token' },
  { label: '导入 Session JSON', value: 'session_json' },
  { label: '导入 CPA JSON 文件', value: 'cpa_json' },
  { label: '从远程 CPA 服务器导入', value: 'remote_cpa' },
  { label: '从 Sub2API 服务器导入', value: 'sub2api' },
] as const

export type AccountImportMode = typeof ACCOUNT_IMPORT_MODE_CATALOG[number]['value']

const accountImportModes = new Set<string>(ACCOUNT_IMPORT_MODE_CATALOG.map((item) => item.value))

export function isAccountImportMode(value: string): value is AccountImportMode {
  return accountImportModes.has(value)
}

type AccountImportRuntimeOptions = {
  bulkProgress: ReturnType<typeof useAccountBulkProgressRuntime>
  normalizeErrorMessage: (error: unknown) => string
  setError: (prefix: string, error: unknown, notify?: boolean) => void
  loadData: (options?: { silentErrorToast?: boolean }) => Promise<void>
  trackingWindowMs?: (total: number) => number
}

function uniqueTokens(tokens: string[]) {
  return Array.from(new Set(tokens.map((token) => token.trim()).filter(Boolean)))
}

function parseTokenLines(text: string) {
  return uniqueTokens(
    text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#')),
  )
}

function parseSessionJsonTokens(rawText: string) {
  const text = rawText.trim()
  if (!text) throw new Error('请先粘贴 Session JSON')
  const parsed = JSON.parse(text)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Session JSON 格式不正确')
  }
  const source = parsed as Record<string, unknown>
  const token = String(source.accessToken || source.access_token || '').trim()
  if (!token) throw new Error('Session JSON 中没有找到 accessToken')
  return [token]
}

export interface RemoteAccountImportProgress {
  title: string
  total: number
  job?: CPAImportJob | null
  error?: string
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

export function parseAccountArchive(rawText: string, label: string) {
  const text = rawText.trim()
  if (!text) throw new Error(`${label} 是空文件`)
  const parsed = JSON.parse(text)
  const wrapper = parsed && typeof parsed === 'object' && !Array.isArray(parsed)
    ? parsed as Record<string, unknown>
    : null
  const candidates: unknown[] = []
  if (Array.isArray(parsed)) {
    candidates.push(...parsed)
  } else if (tokenFromCPAAccount(parsed)) {
    candidates.push(parsed)
  } else if (wrapper) {
    for (const key of ['accounts', 'items', 'data', 'results']) {
      const rows = wrapper[key]
      if (Array.isArray(rows)) candidates.push(...rows)
    }
  }
  const accounts = candidates.filter(
    (item): item is AccountImportPayload => Boolean(tokenFromCPAAccount(item)),
  )
  if (!accounts.length) throw new Error(`${label} 中没有找到 access_token`)
  return accounts
}

function tokenFromCPAAccount(value: unknown): string {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return ''
  const source = value as Record<string, unknown>
  return String(source.access_token || source.accessToken || '').trim()
}

export function useAccountImportRuntime(options: AccountImportRuntimeOptions) {
  const importBusy = ref(false)
  const showImportModal = ref(false)
  const importMode = ref<AccountImportMode>('access_token')
  const oauthEmailHint = ref('')
  const oauthCallbackText = ref('')
  const oauthSessionId = ref('')
  const oauthAuthorizeUrl = ref('')
  const oauthRedirectUriPrefix = ref('')
  const manualTokenText = ref('')
  const sessionJsonText = ref('')
  const toast = useToast()
  const confirmDialog = useConfirmDialog()
  let remoteImportJobId = ''
  let remoteImportTrackingKey = ''
  let remoteImportTrackingRevision = 0
  let lastRemoteImportRequest: RemoteAccountImportStarted | null = null

  const importModeOptions = ACCOUNT_IMPORT_MODE_CATALOG

  function setImportMode(mode: AccountImportMode) {
    importMode.value = mode
  }

  async function openImportModal(mode: AccountImportMode = 'access_token') {
    if (options.bulkProgress.batchBusy.value) {
      toast.warning('请等待当前账号任务完成')
      return
    }
    options.bulkProgress.close()
    showImportModal.value = true
    setImportMode(mode)
  }

  function closeImportModal() {
    if (importBusy.value) return
    showImportModal.value = false
  }

  function waitForRemoteImportPoll(delayMs: number) {
    return new Promise<void>((resolve) => window.setTimeout(resolve, delayMs))
  }

  function refreshAccountListInBackground() {
    void options.loadData({ silentErrorToast: true }).catch(() => {})
  }

  async function promptRemoveImportedAbnormalAccounts(importedAccountIds: string[], errorCount: number) {
    if (
      errorCount <= 0
      || importedAccountIds.length === 0
    ) return

    let preview: Awaited<ReturnType<typeof accountsApi.cleanupImportedAbnormalAccounts>>
    try {
      preview = await accountsApi.cleanupImportedAbnormalAccounts(importedAccountIds, false)
    } catch (error) {
      options.setError('检查本次确认失效账号失败，已先保留', error)
      return
    }

    if (!preview.abnormal) {
      toast.info('本次导入有同步失败，但没有确认失效账号；暂时检测失败的账号会保留')
      return
    }

    const confirmed = await confirmDialog.ask({
      title: '移除本次确认失效账号？',
      message: `本次导入同步失败 ${errorCount} 个。\n后端确认其中 ${preview.abnormal} 个账号鉴权已经失效，是否直接删除？\n\n只会删除本次导入且已确认失效的账号；正常、限流、暂时检测失败和历史账号都会保留。`,
      confirmText: `删除 ${preview.abnormal} 个`,
      cancelText: '先保留',
    })

    if (!confirmed) return

    try {
      const result = await accountsApi.cleanupImportedAbnormalAccounts(importedAccountIds, true)
      options.bulkProgress.appendEvents(result.events || [])
    } catch (error) {
      options.setError('移除本次确认失效账号失败', error, false)
    } finally {
      await options.loadData({ silentErrorToast: true })
    }
  }

  async function importTokenBatch(tokens: string[], sourceType: AccountSourceType, title: string) {
    const normalizedTokens = uniqueTokens(tokens)
    if (!normalizedTokens.length) {
      toast.warning('没有可导入的 access token')
      return
    }
    const result = await importAccountPayloadBatch(
      normalizedTokens.map((accessToken) => ({
        access_token: accessToken,
        source_type: sourceType,
      })),
      sourceType,
      title,
      true,
    )
    if (!result) return
    if (result.added + result.skipped + result.synced > 0) {
      manualTokenText.value = ''
      sessionJsonText.value = ''
    }
    if (result.errors.length > 0) {
      await promptRemoveImportedAbnormalAccounts(result.importedAccountIds, result.errors.length)
    }
  }

  function operationErrorText(value: unknown) {
    if (typeof value === 'string') return value.trim()
    if (!value || typeof value !== 'object') return ''
    const item = value as { id?: unknown; code?: unknown; message?: unknown }
    return [item.id, item.code, item.message]
      .map((part) => String(part || '').trim())
      .filter(Boolean)
      .join(': ')
  }

  async function importAccountPayloadBatch(
    accountPayloads: AccountImportPayload[],
    sourceType: AccountSourceType,
    title: string,
    syncAfterImport = false,
    restore = false,
    alreadyConfirmed = false,
    progressAlreadyStarted = false,
  ) {
    const behavior = restore
      ? '完整备份会恢复凭据、配置与状态；已存在账号会覆盖更新。'
      : syncAfterImport
        ? '已存在账号会更新凭据；导入后同步账号与额度。'
        : '已存在账号会更新凭据和配置。'
    if (!alreadyConfirmed) {
      const confirmed = await confirmDialog.ask({
        title,
        message: `即将导入 ${accountPayloads.length} 个账号。${behavior}是否继续？`,
        confirmText: '确认导入',
        cancelText: '取消',
      })
      if (!confirmed) return
    }

    importBusy.value = true
    showImportModal.value = false
    const total = accountPayloads.length
    if (!progressAlreadyStarted) {
      await options.bulkProgress.start(title, total, 'import')
    }
    options.bulkProgress.update({
      total,
      processed: 0,
      stage: 'read_credentials',
      stage_label: '读取凭据',
    })
    let added = 0
    let skipped = 0
    let synced = 0
    let importedAccountIds: string[] = []
    const errors: string[] = []
    let accountsSaved = false
    try {
      options.bulkProgress.update({
        total,
        processed: 0,
        stage: 'save_accounts',
        stage_label: '保存账号',
      })
      const result = await accountsApi.importAccounts(accountPayloads, sourceType, {
        syncAfterImport: false,
        restore,
        returnItems: false,
      })
      accountsSaved = true
      added = Math.max(0, Number(result.added || 0))
      skipped = Math.max(0, Number(result.skipped || 0))
      importedAccountIds = Array.from(new Set(result.updated_ids || []))
      errors.push(...(Array.isArray(result.errors) ? result.errors.filter(Boolean) : []))
      options.bulkProgress.appendEvents(result.events || [])

      if (syncAfterImport && importedAccountIds.length > 0) {
        options.bulkProgress.update({
          total,
          processed: 0,
          stage: 'sync_accounts',
          stage_label: '同步账号与额度',
        })
        const syncResult = await accountsApi.syncAccountsWithProgress(
          importedAccountIds,
          (progress) => {
            options.bulkProgress.update({
              ...progress,
              total,
              processed: Math.min(total, Number(progress.processed || 0)),
              done: false,
              stage: 'sync_accounts',
              stage_label: '同步账号与额度',
            })
          },
          importedAccountIds.length,
        )
        synced = Math.max(0, Number(syncResult.progress?.result?.synced || 0))
        errors.push(
          ...(syncResult.progress?.result?.errors || [])
            .map(operationErrorText)
            .filter(Boolean),
        )
      }

      const importResult = { added, skipped, synced, failed: errors.length }
      options.bulkProgress.finish({
        total,
        processed: total,
        stage: 'completed',
        stage_label: '完成',
        import_result: importResult,
      })
      refreshAccountListInBackground()
      return { ...importResult, errors, importedAccountIds }
    } catch (error) {
      const message = options.normalizeErrorMessage(error)
      if (accountsSaved) {
        errors.push(message)
      }
      options.bulkProgress.finish({
        total,
        processed: accountsSaved
          ? Math.max(0, Number(options.bulkProgress.refreshProgress.value?.processed || 0))
          : 0,
        stage: 'completed',
        stage_label: '完成',
        error: accountsSaved ? `账号已保存，后续同步未完成：${message}` : message,
        import_result: {
          added,
          skipped,
          synced,
          failed: Math.max(1, errors.length),
        },
      })
      options.setError(accountsSaved ? `${title}已保存，但同步失败` : `${title}失败`, error, false)
      if (accountsSaved) {
        refreshAccountListInBackground()
        return {
          added,
          skipped,
          synced,
          failed: Math.max(1, errors.length),
          errors,
          importedAccountIds,
        }
      }
    } finally {
      importBusy.value = false
      options.bulkProgress.end()
    }
  }

  async function importManualTokenText() {
    await importTokenBatch(parseTokenLines(manualTokenText.value), 'web', '导入 Access Token')
  }

  async function importTokenTextFile(file: File | null | undefined) {
    if (!file) return
    importBusy.value = true
    try {
      const text = await file.text()
      manualTokenText.value = text
    } catch (error) {
      options.setError('读取 Access Token 文件失败', error)
      return
    } finally {
      importBusy.value = false
    }
    await importManualTokenText()
  }

  async function importSessionJson() {
    try {
      await importTokenBatch(parseSessionJsonTokens(sessionJsonText.value), 'web', '导入 Session JSON')
    } catch (error) {
      options.setError('解析 Session JSON 失败', error)
    }
  }

  async function startOAuthLogin() {
    importBusy.value = true
    try {
      const result = await accountImportsApi.startOAuthLogin(oauthEmailHint.value)
      oauthSessionId.value = String(result.session_id || '')
      oauthAuthorizeUrl.value = String(result.authorize_url || '')
      oauthRedirectUriPrefix.value = String(result.redirect_uri_prefix || '')
      oauthCallbackText.value = ''
      if (!oauthSessionId.value || !oauthAuthorizeUrl.value) {
        throw new Error('后端没有返回完整的 OAuth 授权会话')
      }
      window.open(oauthAuthorizeUrl.value, '_blank', 'noopener,noreferrer')
      toast.success('OAuth 授权链接已生成')
    } catch (error) {
      options.setError('生成 OAuth 授权链接失败', error)
    } finally {
      importBusy.value = false
    }
  }

  function openOAuthAuthorizeUrl() {
    if (!oauthAuthorizeUrl.value) {
      void startOAuthLogin()
      return
    }
    window.open(oauthAuthorizeUrl.value, '_blank', 'noopener,noreferrer')
  }

  async function copyOAuthAuthorizeUrl() {
    const value = oauthAuthorizeUrl.value.trim()
    if (!value) {
      toast.warning('请先生成 OAuth 授权链接')
      return
    }
    try {
      await navigator.clipboard.writeText(value)
      toast.success('授权链接已复制')
    } catch (error) {
      options.setError('复制 OAuth 授权链接失败', error)
    }
  }

  async function finishOAuthLogin() {
    const sessionId = oauthSessionId.value.trim()
    const callback = oauthCallbackText.value.trim()
    if (!sessionId) {
      toast.warning('请先生成 OAuth 授权链接')
      return
    }
    if (!callback) {
      toast.warning('请先粘贴 callback URL 或 code')
      return
    }

    importBusy.value = true
    showImportModal.value = false
    await options.bulkProgress.start('OAuth 登录导入', 1, 'import')
    options.bulkProgress.update({
      total: 1,
      processed: 0,
      stage: 'read_credentials',
      stage_label: '读取凭据',
    })
    let added = 0
    let skipped = 0
    let synced = 0
    let accountIds: string[] = []
    const errors: string[] = []
    let credentialsSaved = false
    try {
      options.bulkProgress.update({
        total: 1,
        processed: 0,
        stage: 'save_accounts',
        stage_label: '保存账号',
      })
      const result = await accountImportsApi.finishOAuthLogin(sessionId, callback)
      credentialsSaved = true
      added = Math.max(0, Number(result.added || 0))
      skipped = Math.max(0, Number(result.skipped || 0))
      accountIds = Array.from(new Set(result.updated_ids || []))
      options.bulkProgress.appendEvents(result.events || [])
      errors.push(
        ...(result.errors || [])
          .map(operationErrorText)
          .filter(Boolean),
      )

      if (accountIds.length > 0) {
        options.bulkProgress.update({
          total: 1,
          processed: 0,
          stage: 'sync_accounts',
          stage_label: '同步账号与额度',
        })
        const syncResult = await accountsApi.syncAccountsWithProgress(
          accountIds,
          (progress) => {
            options.bulkProgress.update({
              ...progress,
              total: 1,
              processed: Math.min(1, Number(progress.processed || 0)),
              done: false,
              stage: 'sync_accounts',
              stage_label: '同步账号与额度',
            })
          },
          accountIds.length,
        )
        synced = Math.max(0, Number(syncResult.progress?.result?.synced || 0))
        errors.push(
          ...(syncResult.progress?.result?.errors || [])
            .map(operationErrorText)
            .filter(Boolean),
        )
      }

      options.bulkProgress.finish({
        total: 1,
        processed: 1,
        stage: 'completed',
        stage_label: '完成',
        import_result: { added, skipped, synced, failed: errors.length },
      })
      oauthEmailHint.value = ''
      oauthCallbackText.value = ''
      oauthSessionId.value = ''
      oauthAuthorizeUrl.value = ''
      oauthRedirectUriPrefix.value = ''
      refreshAccountListInBackground()
    } catch (error) {
      const message = options.normalizeErrorMessage(error)
      if (credentialsSaved) {
        errors.push(message)
      }
      options.bulkProgress.finish({
        total: 1,
        processed: credentialsSaved ? 1 : 0,
        stage: 'completed',
        stage_label: '完成',
        error: credentialsSaved ? `凭据已保存，后续同步未完成：${message}` : message,
        import_result: {
          added,
          skipped,
          synced,
          failed: Math.max(1, errors.length),
        },
      })
      options.setError(credentialsSaved ? 'OAuth 凭据已保存，但同步失败' : 'OAuth 登录导入失败', error, false)
      if (credentialsSaved) {
        oauthEmailHint.value = ''
        oauthCallbackText.value = ''
        oauthSessionId.value = ''
        oauthAuthorizeUrl.value = ''
        oauthRedirectUriPrefix.value = ''
        refreshAccountListInBackground()
      }
    } finally {
      importBusy.value = false
      options.bulkProgress.end()
    }
  }

  async function updateRemoteImportProgress(value: RemoteAccountImportProgress) {
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
        stage_label: '完成',
        status_label: '失败',
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
        stage_label: '正在创建任务',
        status_label: '正在创建任务',
        tone: 'info',
      })
      return false
    }

    const importResult = {
      added: job.added,
      skipped: job.skipped,
      synced: job.synced,
      failed: job.failed_total,
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
      import_result: importResult,
    }
    if (job.terminal) {
      options.bulkProgress.finish({
        ...progress,
      })
      options.bulkProgress.end()
      return true
    }

    options.bulkProgress.update({
      ...progress,
    })
    return false
  }

  function remoteImportRequest(
    mode: RemoteAccountImportStarted['mode'],
    sourceId: string,
  ) {
    return mode === 'cpa'
      ? accountImportsApi.getCPAImportJob(sourceId)
      : accountImportsApi.getSub2APIImportJob(sourceId)
  }

  async function finishRemoteImportTracking(
    request: RemoteAccountImportStarted,
    job: CPAImportJob,
    revision: number,
  ) {
    if (revision !== remoteImportTrackingRevision) return
    remoteImportTrackingKey = ''
    lastRemoteImportRequest = null
    await updateRemoteImportProgress({ ...request, job })
    refreshAccountListInBackground()
  }

  async function pollRemoteImportJob(
    request: RemoteAccountImportStarted,
    revision: number,
  ) {
    const startedAt = Date.now()
    const deadline = startedAt + (options.trackingWindowMs || remoteImportTrackingWindowMs)(request.total)
    let consecutiveFailures = 0

    while (revision === remoteImportTrackingRevision && Date.now() < deadline) {
      try {
        const response = await remoteImportRequest(request.mode, request.source_id)
        if (revision !== remoteImportTrackingRevision) return
        consecutiveFailures = 0
        const job = response.import_job || null
        if (job?.terminal) {
          await finishRemoteImportTracking(request, job, revision)
          return
        }
        await updateRemoteImportProgress({ ...request, job })
      } catch {
        if (revision !== remoteImportTrackingRevision) return
        consecutiveFailures += 1
        const current = options.bulkProgress.refreshProgress.value
        options.bulkProgress.update({
          ...(current || {}),
          total: Math.max(0, Number(current?.total || request.total)),
          processed: Math.max(0, Number(current?.processed || 0)),
          done: false,
          stage_label: '连接中断，正在重试',
          status_label: '连接中断，正在重试',
          tone: 'warning',
        })
      }

      await waitForRemoteImportPoll(
        remoteImportPollDelayMs(Date.now() - startedAt, consecutiveFailures),
      )
    }

    if (revision !== remoteImportTrackingRevision) return
    remoteImportTrackingKey = ''
    const current = options.bulkProgress.refreshProgress.value
    options.bulkProgress.update({
      ...(current || {}),
      total: Math.max(0, Number(current?.total || request.total)),
      processed: Math.max(0, Number(current?.processed || 0)),
      done: false,
      stage_label: '后台继续执行',
      status_label: '后台继续执行',
      tone: 'info',
    })
    options.bulkProgress.end()
  }

  async function startRemoteImportTracking(request: RemoteAccountImportStarted) {
    const sourceId = request.source_id.trim()
    if (!sourceId) return
    const jobId = String(request.job?.job_id || '').trim()
    const trackingKey = `${request.mode}:${sourceId}:${jobId}`
    if (trackingKey === remoteImportTrackingKey) return

    remoteImportTrackingRevision += 1
    const revision = remoteImportTrackingRevision
    remoteImportTrackingKey = trackingKey
    showImportModal.value = false
    const normalizedRequest = { ...request, source_id: sourceId }
    lastRemoteImportRequest = normalizedRequest
    const terminal = await updateRemoteImportProgress(normalizedRequest)
    if (terminal && request.job) {
      remoteImportTrackingKey = ''
      lastRemoteImportRequest = null
      refreshAccountListInBackground()
      return
    }
    void pollRemoteImportJob(normalizedRequest, revision)
  }

  function stopRemoteImportTracking() {
    remoteImportTrackingRevision += 1
    remoteImportTrackingKey = ''
  }

  async function resumeRemoteImportTracking() {
    if (remoteImportTrackingKey) return
    if (lastRemoteImportRequest) {
      await startRemoteImportTracking(lastRemoteImportRequest)
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
            title: '导入远程 CPA',
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
            title: '导入 Sub2API 账号',
            total: job.total,
            job,
            updatedAt: Date.parse(job.updated_at || job.created_at || '') || 0,
          })
        }
      }
      const latest = candidates.sort((left, right) => right.updatedAt - left.updatedAt)[0]
      if (latest) await startRemoteImportTracking(latest)
    } catch {
      // The account list remains usable when persisted import progress is temporarily unavailable.
    }
  }

  async function importLocalCPAFiles(files: FileList | File[] | null | undefined) {
    const fileList = Array.from(files || [])
    if (!fileList.length) return
    const restoringBackup = importMode.value === 'backup_json'
    const title = restoringBackup ? '导入完整备份文件' : '导入 CPA JSON 文件'
    const confirmed = await confirmDialog.ask({
      title,
      message: restoringBackup
        ? `即将读取 ${fileList.length} 个备份文件并恢复其中的账号凭据、配置与状态。是否继续？`
        : `即将读取 ${fileList.length} 个 CPA JSON 文件，保存账号后同步账号与额度。是否继续？`,
      confirmText: '确认导入',
      cancelText: '取消',
    })
    if (!confirmed) return

    importBusy.value = true
    showImportModal.value = false
    await options.bulkProgress.start(title, fileList.length, 'import')
    options.bulkProgress.update({
      total: fileList.length,
      processed: 0,
      stage: 'read_credentials',
      stage_label: '读取凭据',
    })
    await nextTick()
    try {
      const accountPayloads: AccountImportPayload[] = []
      for (const [index, file] of fileList.entries()) {
        const text = await file.text()
        accountPayloads.push(...parseAccountArchive(text, file.name))
        options.bulkProgress.update({
          total: fileList.length,
          processed: index + 1,
          stage: 'read_credentials',
          stage_label: '读取凭据',
        })
        await nextTick()
      }
      if (restoringBackup) {
        await importAccountPayloadBatch(
          accountPayloads,
          'codex',
          title,
          false,
          true,
          true,
          true,
        )
      } else {
        await importAccountPayloadBatch(accountPayloads, 'codex', title, true, false, true, true)
      }
    } catch (error) {
      const message = options.normalizeErrorMessage(error)
      options.bulkProgress.finish({
        total: fileList.length,
        processed: Math.max(0, Number(options.bulkProgress.refreshProgress.value?.processed || 0)),
        stage: 'completed',
        stage_label: '完成',
        error: message,
        import_result: { added: 0, skipped: 0, synced: 0, failed: 1 },
      })
      options.bulkProgress.end()
      options.setError(`${title}失败`, error, false)
    } finally {
      importBusy.value = false
    }
  }

  if (getCurrentScope()) {
    onScopeDispose(stopRemoteImportTracking)
  }

  return {
    importBusy,
    showImportModal,
    importMode,
    importModeOptions,
    oauthEmailHint,
    oauthCallbackText,
    oauthSessionId,
    oauthAuthorizeUrl,
    oauthRedirectUriPrefix,
    manualTokenText,
    sessionJsonText,
    setImportMode,
    openImportModal,
    closeImportModal,
    importManualTokenText,
    importTokenTextFile,
    importSessionJson,
    startOAuthLogin,
    openOAuthAuthorizeUrl,
    copyOAuthAuthorizeUrl,
    finishOAuthLogin,
    importLocalCPAFiles,
    updateRemoteImportProgress,
    startRemoteImportTracking,
    stopRemoteImportTracking,
    resumeRemoteImportTracking,
  }
}
