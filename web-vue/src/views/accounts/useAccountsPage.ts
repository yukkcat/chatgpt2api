import { computed, ref, toRef } from 'vue'
import { accountsApi } from '@/api/accounts'
import type {
  Account,
} from '@/api/accounts'
import { usePageRuntime } from '@/composables/usePageRuntime'
import { usePagedQuery } from '@/composables/usePageQuery'
import { useToast } from '@/composables/useToast'
import { errorMessage } from '@/lib/errorMessage'
import { useAccountBulkActionsRuntime } from './accountBulkActionsRuntime'
import { useAccountBulkProgressRuntime } from './accountBulkProgressRuntime'
import { useAccountCrudRuntime } from './accountCrudRuntime'
import { useAccountExportRuntime } from './accountExportRuntime'
import { useAccountGroupsRuntime } from './accountGroupsRuntime'
import { useAccountImportRuntime } from './accountImportRuntime'
import { useAccountPageLifecycleRuntime } from './accountPageLifecycleRuntime'
import { useAccountProxyRuntime } from './accountProxyRuntime'
import { useAccountSelectionRuntime } from './accountSelectionRuntime'
import { useAccountTestRuntime } from './accountTestRuntime'
import type { AccountStatusFilter } from './viewUtils'

type AccountsViewMode = 'list' | 'cards'
export type { AccountImportMode } from './accountImportRuntime'

const ACCOUNT_PAGE_SIZE_OPTIONS = [20, 50, 100]
const DEFAULT_PAGE_SIZE = 20
const ACCOUNT_LIST_REQUEST_KEY = 'accounts:list'
const ACCOUNT_GROUPS_REQUEST_KEY = 'accounts:groups'
const LIST_RELOAD_TIMER_KEY = 'accounts:list-reload'

function normalizeErrorMessage(error: unknown): string {
  return errorMessage(error)
}

export function useAccountsPage() {
  const loading = ref(false)
  const keyword = ref('')
  const statusFilter = ref<AccountStatusFilter>('all')
  const groupFilter = ref('all')
  const pageSize = ref(DEFAULT_PAGE_SIZE)
  const accounts = ref<Account[]>([])
  const accountAllTotal = ref(0)
  const viewMode = ref<AccountsViewMode>('list')
  const bulkProgress = useAccountBulkProgressRuntime()
  const toast = useToast()
  const pageRuntime = usePageRuntime('accounts')
  const accountListQuery = usePagedQuery({
    runtime: pageRuntime,
    key: ACCOUNT_LIST_REQUEST_KEY,
    pageSize,
    loading,
    errorMessage: '加载失败',
    fetch: ({ page, pageSize: size }) => accountsApi.list({
      page,
      page_size: size,
      keyword: keyword.value.trim(),
      status: statusFilter.value,
      group_id: groupFilter.value,
    }),
    resolvePage: (res) => res.page,
    resolvePageCount: (res) => {
      const total = Number(res.total ?? res.accounts?.length ?? 0)
      const size = Number(res.page_size ?? pageSize.value)
      if (!Number.isFinite(total) || !Number.isFinite(size) || size <= 0) return 1
      return Math.max(1, Math.ceil(total / size))
    },
    resolveTotal: (res) => res.total ?? res.accounts?.length ?? 0,
    apply: (res) => {
      accountAllTotal.value = Number(res.all_total ?? 0)
      accounts.value = res.accounts || []
      accountSelection.pruneToCurrentAccounts()
    },
    onError: (_message, error) => {
      setError('加载失败', error)
    },
  })
  const visibleAccounts = computed(() => accounts.value)

  const currentPage = accountListQuery.currentPage
  const accountListTotal = accountListQuery.total
  const statusFilterOptions = [
    { label: '全部状态', value: 'all' },
    { label: '正常', value: 'normal' },
    { label: '限流', value: 'limited' },
    { label: '异常', value: 'abnormal' },
    { label: '禁用', value: 'disabled' },
  ] as const

  const groupFilterOptions = computed(() => [
    { label: '全部账号组', value: 'all' },
    { label: '未分组', value: '__ungrouped__' },
    ...accountGroups.value.map((group) => ({
      label: `${group.enabled === false ? '停用 · ' : ''}${group.name || group.id}`,
      value: group.id,
    })),
  ])

  const accountSelection = useAccountSelectionRuntime({
    accounts,
    pagedAccounts: visibleAccounts,
    total: accountListTotal,
    allTotal: accountAllTotal,
    keyword,
    status: statusFilter,
    groupId: groupFilter,
  })
  const selectedCount = accountSelection.selectedCount
  const scopedSelectionActive = accountSelection.scopedSelectionActive
  const allVisibleSelected = accountSelection.allVisibleSelected
  const someVisibleSelected = accountSelection.someVisibleSelected
  const selectionScope = accountSelection.selectionScope
  const batchInteractionBusy = ref(false)
  const batchBusy = computed(() => bulkProgress.batchBusy.value || batchInteractionBusy.value)
  const showRefreshProgress = bulkProgress.showRefreshProgress
  const refreshProgressTitle = bulkProgress.refreshProgressTitle
  const refreshProgress = bulkProgress.refreshProgress
  const refreshProgressKind = bulkProgress.refreshProgressKind
  const refreshProgressPercent = bulkProgress.refreshProgressPercent
  const refreshProgressStatusText = bulkProgress.refreshProgressStatusText
  const canStopRefreshProgress = bulkProgress.canStopRefreshProgress
  const canCloseRefreshProgress = bulkProgress.canCloseRefreshProgress
  const bulkStopRequested = bulkProgress.bulkStopRequested
  const accountOperationEvents = bulkProgress.operationEvents

  function setError(prefix: string, error: unknown, notify = true) {
    const message = normalizeErrorMessage(error)
    if (notify) toast.error(`${prefix}: ${message}`)
  }

  const accountGroupsRuntime = useAccountGroupsRuntime({
    runtime: pageRuntime,
    requestKey: ACCOUNT_GROUPS_REQUEST_KEY,
    groupFilter,
    loadData,
    setError,
  })
  const accountGroups = accountGroupsRuntime.accountGroups
  const proxyGroups = accountGroupsRuntime.proxyGroups
  const accountGroupsLoading = accountGroupsRuntime.accountGroupsLoading
  const showAccountGroupsModal = accountGroupsRuntime.showAccountGroupsModal
  const accountGroupSaving = accountGroupsRuntime.accountGroupSaving
  const editingAccountGroupId = accountGroupsRuntime.editingAccountGroupId
  const selectedBindGroupId = accountGroupsRuntime.selectedBindGroupId
  const accountGroupForm = accountGroupsRuntime.accountGroupForm
  const accountGroupOptions = accountGroupsRuntime.accountGroupOptions
  const accountGroupProxyOptions = accountGroupsRuntime.accountGroupProxyOptions
  const bindAccountGroupOptions = accountGroupsRuntime.bindAccountGroupOptions
  const accountGroupProxyMode = accountGroupsRuntime.accountGroupProxyMode
  const selectedAccountGroupProxyGroupId = accountGroupsRuntime.selectedAccountGroupProxyGroupId
  const accountGroupCustomProxyInput = accountGroupsRuntime.accountGroupCustomProxyInput
  const accountGroupProxyPreview = accountGroupsRuntime.accountGroupProxyPreview
  const applyAccountGroupsPayload = accountGroupsRuntime.applyAccountGroupsPayload
  const loadAccountGroups = accountGroupsRuntime.loadAccountGroups
  const resetAccountGroupForm = accountGroupsRuntime.resetAccountGroupForm
  const openAccountGroupsModal = accountGroupsRuntime.openAccountGroupsModal
  const closeAccountGroupsModal = accountGroupsRuntime.closeAccountGroupsModal
  const editAccountGroup = accountGroupsRuntime.editAccountGroup
  const saveAccountGroup = accountGroupsRuntime.saveAccountGroup
  const deleteAccountGroup = accountGroupsRuntime.deleteAccountGroup
  const setAccountGroupProxyMode = accountGroupsRuntime.setAccountGroupProxyMode
  const selectAccountGroupProxyGroup = accountGroupsRuntime.selectAccountGroupProxyGroup
  const setAccountGroupCustomProxyInput = accountGroupsRuntime.setAccountGroupCustomProxyInput

  const accountCrud = useAccountCrudRuntime({
    bulkProgress,
    loadData,
    loadAccountGroups,
    normalizeErrorMessage,
    setError,
    isBatchBusy: () => batchBusy.value,
  })
  const saving = accountCrud.saving
  const showModal = accountCrud.showModal
  const editingId = accountCrud.editingId
  const syncingAccountIds = accountCrud.syncingAccountIds
  const refreshingAccessTokenAccountIds = accountCrud.refreshingAccessTokenAccountIds
  const accountOperationBusy = accountCrud.accountOperationBusy
  const form = accountCrud.form

  const accountProxyRuntime = useAccountProxyRuntime({
    proxyGroups,
    proxyValue: toRef(form, 'proxy'),
    setError,
  })
  const proxyTesting = accountProxyRuntime.proxyTesting
  const proxyMode = accountProxyRuntime.proxyMode
  const accountProxyModeOptions = accountProxyRuntime.accountProxyModeOptions
  const proxyGroupOptions = accountProxyRuntime.proxyGroupOptions
  const selectedProxyGroupId = accountProxyRuntime.selectedProxyGroupId
  const customProxyInput = accountProxyRuntime.customProxyInput
  const accountProxyPreview = accountProxyRuntime.accountProxyPreview
  const setProxyMode = accountProxyRuntime.setProxyMode
  const selectProxyGroup = accountProxyRuntime.selectProxyGroup
  const setCustomProxyInput = accountProxyRuntime.setCustomProxyInput
  const testAccountProxy = accountProxyRuntime.testAccountProxy
  accountCrud.setProxyControlsSync(accountProxyRuntime.syncProxyControlsFromProjection)

  const accountExport = useAccountExportRuntime({
    accounts,
    selectedCount,
    selectionScope,
    scopedSelectionActive,
    accountAllTotal,
    accountListTotal,
    reconcileSelection: () => reconcileScopedSelection(true),
    setError,
  })
  const exportBusy = accountExport.exportBusy
  const exportAccounts = accountExport.exportAccounts

  const accountImport = useAccountImportRuntime({
    bulkProgress,
    normalizeErrorMessage,
    setError,
    loadData,
  })
  const importBusy = accountImport.importBusy
  const showImportModal = accountImport.showImportModal
  const importMode = accountImport.importMode
  const importModeOptions = accountImport.importModeOptions
  const oauthEmailHint = accountImport.oauthEmailHint
  const oauthCallbackText = accountImport.oauthCallbackText
  const oauthSessionId = accountImport.oauthSessionId
  const oauthAuthorizeUrl = accountImport.oauthAuthorizeUrl
  const oauthRedirectUriPrefix = accountImport.oauthRedirectUriPrefix
  const manualTokenText = accountImport.manualTokenText
  const sessionJsonText = accountImport.sessionJsonText

  const accountBulkActions = useAccountBulkActionsRuntime({
    bulkProgress,
    accountSelection,
    accountGroups,
    proxyGroups,
    selectedBindGroupId,
    normalizeErrorMessage,
    setError,
    loadData,
    reconcileSelection: () => reconcileScopedSelection(true),
    applyAccountGroupsPayload,
  })
  async function runBatchInteraction<T>(operation: () => Promise<T>) {
    if (batchBusy.value || accountOperationBusy.value) return undefined
    batchInteractionBusy.value = true
    try {
      return await operation()
    } finally {
      batchInteractionBusy.value = false
    }
  }

  const requestStopRefreshProgress = accountBulkActions.requestStopRefreshProgress
  const runBulkAction = (...args: Parameters<typeof accountBulkActions.runBulkAction>) => (
    runBatchInteraction(() => accountBulkActions.runBulkAction(...args))
  )
  const bindSelectedAccountsToGroup = () => runBatchInteraction(accountBulkActions.bindSelectedAccountsToGroup)

  async function copyAccountCredential(item: Account, kind: 'access' | 'refresh') {
    const label = kind === 'access' ? 'AT' : 'RT'
    try {
      const token = kind === 'access'
        ? await accountsApi.getAccessToken(item.id)
        : await accountsApi.getRefreshToken(item.id)
      if (!token) {
        toast.warning(`当前账号没有可复制的 ${label}`)
        return
      }
      await navigator.clipboard.writeText(token)
      toast.success(`${label} 已复制`)
    } catch (error) {
      setError(`复制 ${label} 失败`, error)
    }
  }

  async function loadData(options?: { silentErrorToast?: boolean }) {
    await accountListQuery.load({ silentError: options?.silentErrorToast })
    await reconcileScopedSelection(false)
  }

  const accountTest = useAccountTestRuntime({
    loadData,
    setError,
  })

  async function reconcileScopedSelection(notify: boolean) {
    if (!accountSelection.scopedSelectionActive.value) return true
    const expectedRevision = accountSelection.selectionRevision.value
    const currentScope = accountSelection.selectionScope.value
    const selection = {
      ...currentScope,
      account_ids: [...(currentScope.account_ids || [])],
      excluded_account_ids: [...(currentScope.excluded_account_ids || [])],
    }
    try {
      const preview = await accountsApi.previewSelection(selection)
      return accountSelection.reconcileScopedSelection(preview, expectedRevision)
    } catch (error) {
      if (notify) setError('核对已选账号数量失败', error)
      return false
    }
  }

  const isSelected = accountSelection.isSelected
  const toggleSelect = accountSelection.toggleSelect
  const clearSelection = accountSelection.clearSelection
  const toggleSelectAllVisible = accountSelection.toggleSelectAllVisible
  const selectAllMatching = accountSelection.selectAllMatching

  const setImportMode = accountImport.setImportMode
  const openImportModal = accountImport.openImportModal
  const closeImportModal = accountImport.closeImportModal
  const importManualTokenText = accountImport.importManualTokenText
  const importTokenTextFile = accountImport.importTokenTextFile
  const importSessionJson = accountImport.importSessionJson
  const startOAuthLogin = accountImport.startOAuthLogin
  const openOAuthAuthorizeUrl = accountImport.openOAuthAuthorizeUrl
  const copyOAuthAuthorizeUrl = accountImport.copyOAuthAuthorizeUrl
  const finishOAuthLogin = accountImport.finishOAuthLogin
  const importLocalCPAFiles = accountImport.importLocalCPAFiles
  const updateRemoteImportProgress = accountImport.updateRemoteImportProgress
  const startRemoteImportTracking = accountImport.startRemoteImportTracking
  const stopRemoteImportTracking = accountImport.stopRemoteImportTracking
  const resumeRemoteImportTracking = accountImport.resumeRemoteImportTracking

  function closeRefreshProgress() {
    bulkProgress.close()
  }

  const openCreateModal = accountCrud.openCreateModal
  const openEditModal = accountCrud.openEditModal
  const closeModal = accountCrud.closeModal
  const saveAccount = accountCrud.saveAccount
  const toggleEnabled = accountCrud.toggleEnabled
  const syncAccount = accountCrud.syncAccount
  const refreshAccessToken = accountCrud.refreshAccessToken
  const removeAccount = (item: Account) => runBulkAction(
    'delete',
    [item.id],
    { [item.id]: item.email || item.display_name || item.id },
  )

  const pageLifecycle = useAccountPageLifecycleRuntime({
    runtime: pageRuntime,
    viewMode,
    pageSize,
    currentPage,
    keyword,
    statusFilter,
    groupFilter,
    pageSizeDefault: DEFAULT_PAGE_SIZE,
    pageSizeOptions: ACCOUNT_PAGE_SIZE_OPTIONS,
    reloadTimerKey: LIST_RELOAD_TIMER_KEY,
    loadData,
    loadGroups: loadAccountGroups,
    invalidateData: accountListQuery.invalidate,
    invalidateGroups: accountGroupsRuntime.invalidate,
    clearSelection,
    clearPageSelection: accountSelection.clearExplicitSelection,
    shouldSkipRefresh: () => Boolean(
      showModal.value ||
      showImportModal.value ||
      showAccountGroupsModal.value ||
      accountTest.opened.value ||
      saving.value ||
      batchBusy.value ||
      accountOperationBusy.value ||
      importBusy.value ||
      accountGroupsLoading.value ||
      accountGroupSaving.value,
    ),
  })
  pageRuntime.onActivate(() => {
    void resumeRemoteImportTracking()
  })
  pageRuntime.onShow(() => {
    void resumeRemoteImportTracking()
  })
  pageRuntime.onDeactivate(stopRemoteImportTracking)
  pageRuntime.onHide(stopRemoteImportTracking)
  const setViewMode = pageLifecycle.setViewMode

  return {
    loading,
    saving,
    showModal,
    showAccountTestModal: accountTest.opened,
    accountTestAccount: accountTest.account,
    accountTestMode: accountTest.mode,
    accountTestModel: accountTest.model,
    accountTestPrompt: accountTest.prompt,
    accountTestRunning: accountTest.running,
    accountTestResult: accountTest.result,
    accountTestModelOptions: accountTest.modelOptions,
    accountTestModelCatalogLoading: accountTest.modelCatalogLoading,
    keyword,
    statusFilter,
    groupFilter,
    statusFilterOptions,
    groupFilterOptions,
    editingId,
    accounts,
    accountListTotal,
    accountAllTotal,
    selectedCount,
    allVisibleSelected,
    someVisibleSelected,
    currentPage,
    pageSize,
    pageSizeOptions: ACCOUNT_PAGE_SIZE_OPTIONS,
    batchBusy,
    viewMode,
    syncingAccountIds,
    refreshingAccessTokenAccountIds,
    accountOperationBusy,
    importBusy,
    exportBusy,
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
    accountGroups,
    proxyGroups,
    accountGroupsLoading,
    showAccountGroupsModal,
    accountGroupSaving,
    editingAccountGroupId,
    accountGroupForm,
    accountGroupOptions,
    accountGroupProxyOptions,
    bindAccountGroupOptions,
    selectedBindGroupId,
    proxyTesting,
    proxyMode,
    accountGroupProxyMode,
    accountProxyModeOptions,
    proxyGroupOptions,
    selectedProxyGroupId,
    customProxyInput,
    selectedAccountGroupProxyGroupId,
    accountGroupCustomProxyInput,
    accountProxyPreview,
    accountGroupProxyPreview,
    showRefreshProgress,
    refreshProgressTitle,
    refreshProgress,
    refreshProgressKind,
    refreshProgressPercent,
    refreshProgressStatusText,
    canStopRefreshProgress,
    canCloseRefreshProgress,
    bulkStopRequested,
    accountOperationEvents,
    form,
    visibleAccounts,
    setViewMode,
    isSelected,
    toggleSelect,
    clearSelection,
    toggleSelectAllVisible,
    selectAllMatching,
    selectAllAccounts: accountSelection.selectAllAccounts,
    setImportMode,
    openImportModal,
    closeImportModal,
    loadAccountGroups,
    openAccountGroupsModal,
    closeAccountGroupsModal,
    resetAccountGroupForm,
    editAccountGroup,
    saveAccountGroup,
    deleteAccountGroup,
    testAccountProxy,
    setProxyMode,
    selectProxyGroup,
    setCustomProxyInput,
    setAccountGroupProxyMode,
    selectAccountGroupProxyGroup,
    setAccountGroupCustomProxyInput,
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
    requestStopRefreshProgress,
    closeRefreshProgress,
    loadData,
    copyAccountCredential,
    openCreateModal,
    openEditModal,
    openAccountTest: accountTest.open,
    closeAccountTest: accountTest.close,
    setAccountTestMode: accountTest.setMode,
    runAccountTest: accountTest.run,
    closeModal,
    saveAccount,
    toggleEnabled,
    syncAccount,
    refreshAccessToken,
    removeAccount,
    runBulkAction,
    bindSelectedAccountsToGroup,
    exportAccounts,
  }
}
