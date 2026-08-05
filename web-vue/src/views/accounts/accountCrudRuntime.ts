import { computed, reactive, ref } from 'vue'

import {
  accountsApi,
  type Account,
  type AccountOperationProgress,
  type AccountProxyProjection,
  type AccountSourceType,
} from '@/api/accounts'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import type { useAccountBulkProgressRuntime } from './accountBulkProgressRuntime'

export type AccountForm = {
  id: string
  access_token: string
  type: string
  source_type: AccountSourceType
  group_id: string
  proxy: string
  quota: string
}

type AccountCrudRuntimeOptions = {
  bulkProgress: ReturnType<typeof useAccountBulkProgressRuntime>
  loadData: (options?: { silentErrorToast?: boolean }) => Promise<void>
  loadAccountGroups: (options?: { silentErrorToast?: boolean }) => Promise<void>
  normalizeErrorMessage: (error: unknown) => string
  setError: (prefix: string, error: unknown, notify?: boolean) => void
  isBatchBusy: () => boolean
}

function createDefaultForm(): AccountForm {
  return {
    id: '',
    access_token: '',
    type: '',
    source_type: 'web',
    group_id: '',
    proxy: '',
    quota: '',
  }
}

function normalizeQuota(value: unknown): number | undefined {
  const raw = String(value ?? '').trim()
  if (!raw) return undefined
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : undefined
}

function accountLabel(item: Pick<Account, 'id' | 'email' | 'display_name'>) {
  return item.email.trim() || item.display_name.trim() || item.id
}

export function useAccountCrudRuntime(options: AccountCrudRuntimeOptions) {
  const saving = ref(false)
  const showModal = ref(false)
  const editingId = ref<string | null>(null)
  const syncingAccountIds = ref<Set<string>>(new Set())
  const refreshingAccessTokenAccountIds = ref<Set<string>>(new Set())
  const activeAccountOperationId = ref('')
  const accountOperationBusy = computed(() => (
    Boolean(activeAccountOperationId.value) || showModal.value || saving.value
  ))
  const form = reactive(createDefaultForm())
  const toast = useToast()
  const confirmDialog = useConfirmDialog()
  let syncProxyControlsFromProjection: (projection?: AccountProxyProjection) => void = () => {}

  function setAccountPending(target: { value: Set<string> }, accountId: string, pending: boolean) {
    const next = new Set(target.value)
    if (pending) next.add(accountId)
    else next.delete(accountId)
    target.value = next
  }

  function beginAccountOperation(accountId: string) {
    if (options.isBatchBusy() || accountOperationBusy.value) return false
    activeAccountOperationId.value = accountId
    return true
  }

  function endAccountOperation(accountId: string) {
    if (activeAccountOperationId.value === accountId) activeAccountOperationId.value = ''
  }

  function finishMutationTask(
    progress: AccountOperationProgress | null | undefined,
  ) {
    if (!progress) throw new Error('账号操作响应缺少进度投影')
    options.bulkProgress.finish(progress)
  }

  function failAccountTask(label: string, action: string, error: unknown) {
    options.bulkProgress.fail(
      1,
      Number(options.bulkProgress.refreshProgress.value?.processed || 0),
      `账号 ${label} ${action}失败：${options.normalizeErrorMessage(error)}`,
    )
  }

  function setProxyControlsSync(sync: (projection?: AccountProxyProjection) => void) {
    syncProxyControlsFromProjection = sync
    syncProxyControlsFromProjection()
  }

  function resetForm() {
    editingId.value = null
    Object.assign(form, createDefaultForm())
    syncProxyControlsFromProjection()
  }

  function openCreateModal() {
    if (options.isBatchBusy() || accountOperationBusy.value) return
    resetForm()
    void options.loadAccountGroups({ silentErrorToast: true })
    showModal.value = true
  }

  async function openEditModal(item: Account) {
    if (!beginAccountOperation(item.id)) return
    resetForm()
    editingId.value = item.id
    try {
      const [detail] = await Promise.all([
        accountsApi.get(item.id),
        options.loadAccountGroups({ silentErrorToast: true }),
      ])
      if (editingId.value !== item.id) return
      form.id = detail.id
      form.access_token = ''
      form.type = detail.configuration.type
      form.source_type = (detail.configuration.source_type || detail.source) as AccountSourceType
      form.group_id = detail.configuration.group_id
      form.proxy = detail.configuration.proxy
      form.quota = detail.quota_unknown ? '' : String(detail.configuration.quota)
      syncProxyControlsFromProjection(detail)
      showModal.value = true
    } catch (error) {
      if (editingId.value === item.id) resetForm()
      options.setError('加载账号详情失败', error)
    } finally {
      endAccountOperation(item.id)
    }
  }

  function closeModal() {
    showModal.value = false
    resetForm()
  }

  async function saveAccount() {
    if (!editingId.value && !form.access_token.trim()) {
      toast.warning('Access token 不能为空')
      return
    }

    saving.value = true
    const isEditing = Boolean(editingId.value)

    try {
      const payloadId = editingId.value || form.id || undefined
      const result = await accountsApi.upsert({
        id: payloadId,
        access_token: isEditing ? undefined : form.access_token.trim(),
        type: form.type.trim(),
        source_type: form.source_type,
        group_id: form.group_id.trim(),
        proxy: form.proxy.trim(),
        quota: normalizeQuota(form.quota),
      })
      const firstError = result.errors[0]
      const errorDetail = firstError
        ? [firstError.code, firstError.message].filter(Boolean).join(': ')
        : ''
      if (result.removed_ids.length > 0) {
        throw new Error(errorDetail || '账号校验失败并已自动移除')
      }
      if (result.errors.length > 0) {
        toast.warning(`账号已保存，但账号与额度同步失败${errorDetail ? `：${errorDetail}` : ''}`)
        closeModal()
        await options.loadData({ silentErrorToast: true })
        return
      }
      if (!result.account) throw new Error('后端未返回更新后的账号')
      toast.success(isEditing ? `账号 ${accountLabel(result.account)} 已更新` : '账号已添加')
      closeModal()
      await options.loadData({ silentErrorToast: true })
    } catch (error) {
      options.setError('保存失败', error)
      await options.loadData({ silentErrorToast: true })
    } finally {
      saving.value = false
    }
  }

  async function toggleEnabled(item: Account) {
    if (!beginAccountOperation(item.id)) return
    const label = accountLabel(item)
    const action = item.enabled_action
    const actionLabel = item.enabled_action_label
    let taskStarted = false
    try {
      const confirmed = await confirmDialog.ask({
        title: `确认${actionLabel}`,
        message: `即将对账号 ${label} 执行“${actionLabel}”。这会影响该账号是否参与后续请求分配，是否继续？`,
        confirmText: actionLabel,
        cancelText: '取消',
      })
      if (!confirmed) return

      await options.bulkProgress.start(actionLabel, 1, 'mutation')
      taskStarted = true
      const result = action === 'enable'
        ? await accountsApi.bulkEnable([item.id], undefined, 1)
        : await accountsApi.bulkDisable([item.id], undefined, 1)
      finishMutationTask(result.progress)
      await options.loadData({ silentErrorToast: true })
    } catch (error) {
      if (taskStarted) failAccountTask(label, actionLabel, error)
      options.setError(`${actionLabel}失败`, error, !taskStarted)
    } finally {
      if (taskStarted) options.bulkProgress.end()
      endAccountOperation(item.id)
    }
  }

  async function syncAccount(item: Account) {
    const accountId = item.id
    const label = accountLabel(item)
    if (!beginAccountOperation(accountId)) return
    let taskStarted = false
    try {
      const confirmed = await confirmDialog.ask({
        title: '同步账号与额度',
        message: `即将同步账号 ${label} 的远端信息和额度，是否继续？`,
        confirmText: '开始同步',
        cancelText: '取消',
      })
      if (!confirmed) return

      await options.bulkProgress.start('同步账号与额度', 1, 'sync')
      taskStarted = true
      setAccountPending(syncingAccountIds, accountId, true)
      const result = await accountsApi.syncAccountsWithProgress([accountId], (progress) => {
        options.bulkProgress.update({
          ...progress,
          total: 1,
          processed: Math.min(1, Number(progress.processed || 0)),
          done: false,
        })
      }, 1)
      if (!result.progress) throw new Error('账号操作响应缺少进度投影')
      options.bulkProgress.finish(result.progress)
      await options.loadData({ silentErrorToast: true })
    } catch (error) {
      if (taskStarted) failAccountTask(label, '同步', error)
      await options.loadData({ silentErrorToast: true })
    } finally {
      setAccountPending(syncingAccountIds, accountId, false)
      if (taskStarted) options.bulkProgress.end()
      endAccountOperation(accountId)
    }
  }

  async function refreshAccessToken(item: Account) {
    const accountId = item.id
    const label = accountLabel(item)
    if (!beginAccountOperation(accountId)) return
    let taskStarted = false
    try {
      const confirmed = await confirmDialog.ask({
        title: '刷新 AT',
        message: `即将使用账号 ${label} 的 RT 刷新 AT，是否继续？`,
        confirmText: '开始刷新',
        cancelText: '取消',
      })
      if (!confirmed) return

      await options.bulkProgress.start('刷新 AT', 1, 'credentials')
      taskStarted = true
      setAccountPending(refreshingAccessTokenAccountIds, accountId, true)
      const result = await accountsApi.refreshAccessTokensWithProgress([accountId], (progress) => {
        options.bulkProgress.update({
          ...progress,
          total: 1,
          processed: Math.min(1, Number(progress.processed || 0)),
          done: false,
        })
      }, 1)
      if (!result.progress) throw new Error('账号操作响应缺少进度投影')
      options.bulkProgress.finish(result.progress)
      await options.loadData({ silentErrorToast: true })
    } catch (error) {
      if (taskStarted) failAccountTask(label, '刷新 AT', error)
      await options.loadData({ silentErrorToast: true })
    } finally {
      setAccountPending(refreshingAccessTokenAccountIds, accountId, false)
      if (taskStarted) options.bulkProgress.end()
      endAccountOperation(accountId)
    }
  }

  return {
    saving,
    showModal,
    editingId,
    syncingAccountIds,
    refreshingAccessTokenAccountIds,
    accountOperationBusy,
    form,
    setProxyControlsSync,
    resetForm,
    openCreateModal,
    openEditModal,
    closeModal,
    saveAccount,
    toggleEnabled,
    syncAccount,
    refreshAccessToken,
  }
}
