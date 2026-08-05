import type { Ref } from 'vue'

import {
  accountsApi,
  type AccountGroup,
  type AccountOperationProgress,
  type AccountSelectionScope,
  type AccountSelectionTarget,
} from '@/api/accounts'
import type { ProxyGroup } from '@/api/proxy'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import type { useAccountBulkProgressRuntime } from './accountBulkProgressRuntime'

export type AccountBulkAction = 'sync' | 'refresh-access-token' | 'enable' | 'disable' | 'delete'
type AccountCredentialAction = Extract<AccountBulkAction, 'sync' | 'refresh-access-token'>
type AccountMutationAction = Exclude<AccountBulkAction, AccountCredentialAction>

type AccountSelectionAdapter = {
  selectedIds: Ref<string[]>
  selectedCount: Readonly<Ref<number>>
  scopedSelectionActive: Readonly<Ref<boolean>>
  selectionScope: Readonly<Ref<AccountSelectionScope>>
  clearSelection: () => void
  removeSelectedIds: (ids: readonly string[]) => void
}

type AccountBulkMutationResponse = {
  progress: AccountOperationProgress | null
}

type AccountBulkActionsRuntimeOptions = {
  bulkProgress: ReturnType<typeof useAccountBulkProgressRuntime>
  accountSelection: AccountSelectionAdapter
  accountGroups: Ref<AccountGroup[]>
  proxyGroups: Ref<ProxyGroup[]>
  selectedBindGroupId: Ref<string>
  normalizeErrorMessage: (error: unknown) => string
  setError: (prefix: string, error: unknown, notify?: boolean) => void
  loadData: (options?: { silentErrorToast?: boolean }) => Promise<void>
  reconcileSelection: () => Promise<boolean>
  applyAccountGroupsPayload: (response: { groups?: AccountGroup[]; proxy_groups?: ProxyGroup[] }) => void
}

function uniqueIds(ids: readonly string[]) {
  return Array.from(new Set(ids.map((id) => String(id || '').trim()).filter(Boolean)))
}

function bulkActionMeta(action: AccountMutationAction) {
  return {
    enable: { title: '批量启用账号', confirmText: '确认启用' },
    disable: { title: '批量禁用账号', confirmText: '确认禁用' },
    delete: { title: '批量删除账号', confirmText: '确认删除' },
  }[action]
}

function accountLabel(accountId: string, labels?: Readonly<Record<string, string>>) {
  return String(labels?.[accountId] || '').trim() || accountId
}

function credentialActionMeta(action: AccountCredentialAction) {
  return action === 'sync'
    ? { title: '批量同步账号与额度', verb: '同步', kind: 'sync' as const }
    : { title: '批量刷新 AT', verb: '刷新 AT', kind: 'credentials' as const }
}

export function useAccountBulkActionsRuntime(options: AccountBulkActionsRuntimeOptions) {
  const toast = useToast()
  const confirmDialog = useConfirmDialog()

  async function runCredentialActionWithProgress(
    action: AccountCredentialAction,
    target: AccountSelectionTarget,
    targetCount: number,
    useSelectionScope: boolean,
  ) {
    const meta = credentialActionMeta(action)
    const confirmed = await confirmDialog.ask({
      title: meta.title,
      message: useSelectionScope
        ? `即将${meta.verb}当前筛选条件下选中的 ${targetCount} 个账号，是否继续？`
        : `即将${meta.verb} ${targetCount} 个账号，后端会按账号批量任务并发执行。是否继续？`,
      confirmText: `开始${meta.verb}`,
      cancelText: '取消',
    })
    if (!confirmed) return

    await options.bulkProgress.start(meta.title, targetCount, meta.kind)

    try {
      const request = action === 'sync'
        ? accountsApi.syncAccountsWithProgress
        : accountsApi.refreshAccessTokensWithProgress
      const result = await request(target, (progress) => {
        options.bulkProgress.update({
          ...progress,
          total: Number(progress.total || targetCount),
          processed: Math.min(targetCount, Number(progress.processed || 0)),
          done: false,
        })
      }, targetCount)

      const progress = result.progress
      const operationResult = progress?.result
      const updatedIds = uniqueIds(operationResult?.updated_ids || [])
      const removedIds = uniqueIds(operationResult?.removed_ids || [])
      if (!progress) throw new Error('账号操作响应缺少进度投影')
      options.bulkProgress.finish({
        ...progress,
        total: Number(progress?.total || targetCount),
        processed: Number(progress?.processed || progress?.total || targetCount),
      })
      const completedIds = uniqueIds([...updatedIds, ...removedIds])
      if (useSelectionScope) options.accountSelection.clearSelection()
      else options.accountSelection.removeSelectedIds(completedIds)
      await options.loadData({ silentErrorToast: true })
    } catch (error) {
      options.bulkProgress.fail(
        targetCount,
        Number(options.bulkProgress.refreshProgress.value?.processed || 0),
        options.normalizeErrorMessage(error),
      )
      options.setError(`${meta.title}失败`, error, false)
      await options.loadData({ silentErrorToast: true })
    } finally {
      options.bulkProgress.end()
    }
  }

  async function runBulkAction(
    action: AccountBulkAction,
    ids?: readonly string[],
    labels?: Readonly<Record<string, string>>,
  ) {
    const useSelectionScope = !ids && options.accountSelection.scopedSelectionActive.value
    if (useSelectionScope && !await options.reconcileSelection()) return
    const targetIds = uniqueIds(ids || options.accountSelection.selectedIds.value)
    const targetCount = useSelectionScope ? options.accountSelection.selectedCount.value : targetIds.length
    const target: AccountSelectionTarget = useSelectionScope
      ? options.accountSelection.selectionScope.value
      : targetIds
    if (!targetCount) {
      toast.warning('请先选择账号')
      return
    }

    if (action === 'sync' || action === 'refresh-access-token') {
      await runCredentialActionWithProgress(action, target, targetCount, useSelectionScope)
      return
    }

    const actionMeta = bulkActionMeta(action)
    const isSingleDelete = action === 'delete' && !useSelectionScope && targetCount === 1
    const confirmed = await confirmDialog.ask({
      title: isSingleDelete ? '删除账号' : actionMeta.title,
      message: isSingleDelete
        ? `确认删除账号 ${accountLabel(targetIds[0], labels)} 吗？此操作不可恢复。`
        : `确认对选中的 ${targetCount} 个账号执行该操作吗？`,
      confirmText: actionMeta.confirmText,
      cancelText: '取消',
    })
    if (!confirmed) return

    await options.bulkProgress.start(isSingleDelete ? '删除账号' : actionMeta.title, targetCount, 'mutation')
    try {
      const request = action === 'disable'
        ? accountsApi.bulkDisable
        : action === 'delete'
          ? accountsApi.bulkDelete
          : accountsApi.bulkEnable
      const response: AccountBulkMutationResponse = await request(
        target,
        (progress) => options.bulkProgress.update(progress),
        targetCount,
      )
      const progress = response.progress
      const operationResult = progress?.result
      const updatedIds = uniqueIds(operationResult?.updated_ids || [])
      const removedIds = uniqueIds(operationResult?.removed_ids || [])
      const completedIds = uniqueIds([...updatedIds, ...removedIds])
      if (!progress) throw new Error('账号操作响应缺少进度投影')
      options.bulkProgress.finish(progress)
      if (useSelectionScope) options.accountSelection.clearSelection()
      else options.accountSelection.removeSelectedIds(completedIds)
      await options.loadData({ silentErrorToast: true })
    } catch (error) {
      options.bulkProgress.fail(
        targetCount,
        Number(options.bulkProgress.refreshProgress.value?.processed || 0),
        options.normalizeErrorMessage(error),
      )
      options.setError(`${actionMeta.title}失败`, error, false)
      await options.loadData({ silentErrorToast: true })
    } finally {
      options.bulkProgress.end()
    }
  }

  async function bindSelectedAccountsToGroup() {
    const useSelectionScope = options.accountSelection.scopedSelectionActive.value
    if (useSelectionScope && !await options.reconcileSelection()) return
    const targetIds = uniqueIds(options.accountSelection.selectedIds.value)
    const targetCount = useSelectionScope ? options.accountSelection.selectedCount.value : targetIds.length
    const target: AccountSelectionTarget = useSelectionScope
      ? options.accountSelection.selectionScope.value
      : targetIds
    if (!targetCount) {
      toast.warning('请先选择账号')
      return
    }
    const nextGroupId = options.selectedBindGroupId.value === '__ungrouped__' ? '' : options.selectedBindGroupId.value.trim()
    if (options.selectedBindGroupId.value !== '__ungrouped__' && !nextGroupId) {
      toast.warning('请先选择要绑定的账号组')
      return
    }
    const groupName = nextGroupId
      ? options.accountGroups.value.find((group) => group.id === nextGroupId)?.name || nextGroupId
      : '未分组'
    const confirmed = await confirmDialog.ask({
      title: '批量绑定账号组',
      message: `确认把选中的 ${targetCount} 个账号绑定到 ${groupName} 吗？`,
      confirmText: '确认绑定',
      cancelText: '取消',
    })
    if (!confirmed) return

    await options.bulkProgress.start('批量绑定账号组', targetCount, 'mutation')
    try {
      const result = await accountsApi.bindGroup(target, nextGroupId)
      const updatedIds = uniqueIds(result.updated_ids || [])
      const removedIds = uniqueIds(result.removed_ids || [])
      const completedIds = uniqueIds([...updatedIds, ...removedIds])
      options.applyAccountGroupsPayload({ groups: result.groups, proxy_groups: options.proxyGroups.value })
      if (!result.progress) throw new Error('账号操作响应缺少进度投影')
      options.bulkProgress.finish(result.progress)
      if (useSelectionScope) options.accountSelection.clearSelection()
      else options.accountSelection.removeSelectedIds(completedIds)
      await options.loadData({ silentErrorToast: true })
    } catch (error) {
      options.bulkProgress.fail(targetCount, 0, options.normalizeErrorMessage(error))
      options.setError('批量绑定账号组失败', error, false)
    } finally {
      options.bulkProgress.end()
    }
  }

  function requestStopRefreshProgress() {
    options.bulkProgress.requestStop()
  }

  return {
    requestStopRefreshProgress,
    runBulkAction,
    bindSelectedAccountsToGroup,
  }
}
