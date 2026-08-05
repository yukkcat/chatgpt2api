import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, ref } from 'vue'
import { createServer } from 'vite'

const accountsViewSource = readFileSync(new URL('../src/views/Accounts.vue', import.meta.url), 'utf8')
const accountsApiSource = readFileSync(new URL('../src/api/accounts.ts', import.meta.url), 'utf8')
const bulkActionsSource = readFileSync(
  new URL('../src/views/accounts/accountBulkActionsRuntime.ts', import.meta.url),
  'utf8',
)
const bulkProgressSource = readFileSync(
  new URL('../src/views/accounts/accountBulkProgressRuntime.ts', import.meta.url),
  'utf8',
)
const proxyViewSource = readFileSync(new URL('../src/views/Proxy.vue', import.meta.url), 'utf8')

assert.doesNotMatch(accountsViewSource, /form\.status|accountStatusOptions/)
assert.doesNotMatch(accountsApiSource, /resetAccountState|bulkReset/)
assert.doesNotMatch(bulkActionsSource, /'reset'|reset_account/)
assert.doesNotMatch(bulkProgressSource, /buildLocalEvent|appendTerminalEvent|terminalSummary|eventTone/)
assert.doesNotMatch(
  proxyViewSource,
  /scroll-class="[^"]*overflow-y-auto/,
)

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

async function waitFor(predicate, message, timeoutMs = 1_000) {
  const deadline = Date.now() + timeoutMs
  while (!predicate()) {
    if (Date.now() >= deadline) {
      throw new Error(`Timed out waiting for ${message}`)
    }
    await new Promise(resolve => setTimeout(resolve, 0))
  }
}

try {
  const { useAccountSelectionRuntime } = await server.ssrLoadModule(
    '/src/views/accounts/accountSelectionRuntime.ts',
  )
  const {
    ACCOUNT_IMPORT_MODE_CATALOG,
    parseAccountArchive,
    remoteImportPollDelayMs,
    remoteImportTrackingWindowMs,
    useAccountImportRuntime,
  } = await server.ssrLoadModule(
    '/src/views/accounts/accountImportRuntime.ts',
  )
  const { accountOperationPollDelayMs, accountsApi } = await server.ssrLoadModule('/src/api/accounts.ts')
  const { modelsApi } = await server.ssrLoadModule('/src/api/models.ts')
  const { accountImportsApi } = await server.ssrLoadModule('/src/api/accountImports.ts')
  const { apiClient } = await server.ssrLoadModule('/src/api/client.ts')
  const { useAccountExportRuntime } = await server.ssrLoadModule(
    '/src/views/accounts/accountExportRuntime.ts',
  )
  const { useAccountBulkActionsRuntime } = await server.ssrLoadModule(
    '/src/views/accounts/accountBulkActionsRuntime.ts',
  )
  const { useAccountBulkProgressRuntime } = await server.ssrLoadModule(
    '/src/views/accounts/accountBulkProgressRuntime.ts',
  )
  const { useAccountActionMenuRuntime } = await server.ssrLoadModule(
    '/src/views/accounts/accountActionMenuRuntime.ts',
  )
  const { useAccountCrudRuntime } = await server.ssrLoadModule(
    '/src/views/accounts/accountCrudRuntime.ts',
  )
  const { useAccountTestRuntime } = await server.ssrLoadModule(
    '/src/views/accounts/accountTestRuntime.ts',
  )
  const {
    accountSurfaceClass,
    buildAccountGroupRows,
  } = await server.ssrLoadModule('/src/views/accounts/viewUtils.ts')
  const { useConfirmDialog } = await server.ssrLoadModule('/src/composables/useConfirmDialog.ts')
  const { toastState } = await server.ssrLoadModule('/src/composables/useToast.ts')

  const originalCatalog = modelsApi.catalog
  const originalTestAccount = accountsApi.testAccount
  let accountTestReloads = 0
  modelsApi.catalog = async () => ({
    object: 'model_catalog',
    schema_version: 1,
    generated_at: '2026-08-04T00:00:00Z',
    revision: 'account-test',
    chat_models: ['auto', 'gpt-5'],
    image_models: ['gpt-image-2'],
    all_models: ['auto', 'gpt-5', 'gpt-image-2'],
    defaults: { chat_model: 'auto', image_model: 'gpt-image-2' },
    capabilities: { image_upscale: false, high_resolution_image_models: [] },
    source: { chat: 'fallback', image: 'fallback' },
    openai_models_endpoint: '/v1/models',
  })
  const accountTestRuntime = useAccountTestRuntime({
    loadData: async () => { accountTestReloads += 1 },
    setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
  })
  await accountTestRuntime.open({
    id: 'account-test-1',
    email: 'test@example.test',
    display_name: 'test@example.test',
    source_plan_label: 'Web / Plus',
    quota_label: '5',
  })
  assert.equal(accountTestRuntime.opened.value, true)
  assert.equal(accountTestRuntime.mode.value, 'chat')
  assert.equal(accountTestRuntime.model.value, 'auto')
  assert.equal(accountTestRuntime.prompt.value, 'Hi！ChatGPT')

  accountTestRuntime.setMode('image')
  assert.equal(accountTestRuntime.model.value, 'gpt-image-2')
  assert.equal(
    accountTestRuntime.prompt.value,
    '一只慵懒的猫咪蜷在柔软毛毯上睡觉，午后暖光，温馨室内，细节丰富，治愈系插画。',
  )
  accountsApi.testAccount = async (_accountId, payload) => ({
    status: 'success',
    status_label: '测试通过',
    tone: 'success',
    account_id: 'account-test-1',
    account_label: 'test@example.test',
    mode: payload.mode,
    mode_label: '画图',
    model: payload.model,
    duration_ms: 1200,
    content: '![image_1](/images/test.png)',
    quota_before_label: '5',
    quota_after_label: '4',
    quota_deducted: true,
    error_code: '',
    error_message: '',
  })
  await accountTestRuntime.run()
  assert.equal(accountTestRuntime.result.value?.quota_after_label, '4')
  assert.equal(accountTestReloads, 1)
  accountTestRuntime.close()
  assert.equal(accountTestRuntime.opened.value, false)
  modelsApi.catalog = originalCatalog
  accountsApi.testAccount = originalTestAccount

  const accounts = ref([
    { id: 'account-1' },
    { id: 'account-2' },
  ])
  const pagedAccounts = computed(() => accounts.value)
  const total = ref(5)
  const keyword = ref('plus')
  const status = ref('normal')
  const groupId = ref('group-a')
  const runtime = useAccountSelectionRuntime({
    accounts,
    pagedAccounts,
    total,
    allTotal: ref(5),
    keyword,
    status,
    groupId,
  })

  assert.equal(remoteImportTrackingWindowMs(1), 30 * 60 * 1000)
  assert.equal(remoteImportTrackingWindowMs(200), 100 * 60 * 1000)
  assert.equal(remoteImportTrackingWindowMs(10_000), 2 * 60 * 60 * 1000)
  assert.equal(remoteImportPollDelayMs(30_000), 1_000)
  assert.equal(remoteImportPollDelayMs(90_000), 2_000)
  assert.equal(remoteImportPollDelayMs(10 * 60_000), 5_000)
  assert.equal(remoteImportPollDelayMs(30_000, 4), 8_000)
  assert.equal(accountOperationPollDelayMs(0), 250)
  assert.equal(accountOperationPollDelayMs(30_000), 500)
  assert.equal(accountOperationPollDelayMs(2 * 60_000), 1_000)
  assert.equal(accountOperationPollDelayMs(10 * 60_000), 2_000)

  const projectedAccountGroup = {
    id: 'writers',
    name: '写作组',
    proxy: 'group:primary',
    proxy_group_id: 'primary',
    proxy_mode: 'group',
    proxy_label: '代理组：后端主出口',
    enabled: true,
    account_count: 3,
  }
  const [accountGroupRow] = buildAccountGroupRows([projectedAccountGroup])
  assert.equal(accountGroupRow.proxy_label, '代理组：后端主出口')
  assert.equal(accountGroupRow.proxy, 'group:primary')
  assert.equal(accountGroupRow.raw, projectedAccountGroup)

  assert.equal(
    accountSurfaceClass({ status_tone: 'error' }, false, 'row'),
    'bg-rose-500/5 hover:bg-rose-500/[0.08]',
  )
  assert.equal(
    accountSurfaceClass({ status_tone: 'warning' }, false, 'row'),
    'bg-amber-500/5 hover:bg-amber-500/[0.08]',
  )
  assert.equal(
    accountSurfaceClass({ status_tone: 'success' }, false, 'row'),
    'hover:bg-muted/30',
  )
  assert.equal(accountSurfaceClass({ status_tone: 'neutral' }, false, 'card'), 'bg-muted/50 hover:border-primary/30')
  assert.equal(accountSurfaceClass({ status_tone: 'error' }, true, 'row'), 'bg-primary/5')
  assert.equal(
    accountSurfaceClass({ status_tone: 'warning' }, true, 'card'),
    'border-primary/45 bg-primary/[0.02]',
  )

  const actionMenuSelectedCount = ref(0)
  const actionMenuAllTotal = ref(5)
  const actionMenuCalls = []
  const accountActionMenu = useAccountActionMenuRuntime({
    selectedCount: actionMenuSelectedCount,
    accountAllTotal: actionMenuAllTotal,
    accountGroupsLoading: ref(false),
    bindAccountGroupOptions: ref([]),
    selectedBindGroupId: ref(''),
    openCreateModal: () => {},
    openImportModal: () => {},
    exportAccounts: async () => {},
    runBulkAction: async () => {},
    bindSelectedAccountsToGroup: async () => {},
    selectAllAccounts: () => actionMenuCalls.push('select-all'),
    clearSelection: () => actionMenuCalls.push('clear'),
  })
  assert.deepEqual(
    accountActionMenu.accountEntryItems.value.map((item) => item.label),
    [
      '手动添加账号',
      'OAuth 登录已有账号',
      '导入完整备份文件',
      '导入 Access Token',
      '导入 Session JSON',
      '导入 CPA JSON 文件',
      '从远程 CPA 服务器导入',
      '从 Sub2API 服务器导入',
    ],
  )
  assert.deepEqual(
    ACCOUNT_IMPORT_MODE_CATALOG.map((item) => item.value),
    [
      'oauth_login',
      'backup_json',
      'access_token',
      'session_json',
      'cpa_json',
      'remote_cpa',
      'sub2api',
    ],
  )
  const initialBatchItems = accountActionMenu.batchMenuItems.value
  assert.equal(initialBatchItems.find(item => item.key === 'select-all-accounts')?.disabled, false)
  assert.equal(initialBatchItems.find(item => item.key === 'clear-selection')?.disabled, true)
  assert.equal(initialBatchItems.find(item => item.key === 'sync')?.disabled, true)
  await accountActionMenu.handleBatchAction('select-all-accounts')
  assert.deepEqual(actionMenuCalls, ['select-all'])
  actionMenuSelectedCount.value = 5
  assert.equal(accountActionMenu.batchMenuItems.value.find(item => item.key === 'select-all-accounts')?.disabled, true)
  assert.equal(accountActionMenu.batchMenuItems.value.find(item => item.key === 'clear-selection')?.label, '取消选择 (5)')
  assert.equal(accountActionMenu.batchMenuItems.value.find(item => item.key === 'sync')?.disabled, false)
  await accountActionMenu.handleBatchAction('clear-selection')
  assert.deepEqual(actionMenuCalls, ['select-all', 'clear'])

  runtime.toggleSelectAllVisible(true)
  assert.equal(runtime.selectedCount.value, 2)
  assert.equal(runtime.allVisibleSelected.value, true)
  assert.deepEqual(runtime.selectionScope.value, {
    mode: 'explicit',
    account_ids: ['account-1', 'account-2'],
  })

  runtime.selectAllMatching()
  assert.equal(runtime.scopedSelectionActive.value, true)
  assert.equal(runtime.selectedCount.value, 5)
  assert.deepEqual(runtime.selectionScope.value, {
    mode: 'filter',
    keyword: 'plus',
    status: 'normal',
    group_id: 'group-a',
    excluded_account_ids: [],
  })

  runtime.toggleSelect('account-2', false)
  assert.equal(runtime.isSelected('account-2'), false)
  assert.equal(runtime.selectedCount.value, 4)
  assert.deepEqual(runtime.selectionScope.value.excluded_account_ids, ['account-2'])

  const reconciliationRevision = runtime.selectionRevision.value
  assert.equal(runtime.reconcileScopedSelection({
    matching_count: 4,
    selected_count: 4,
    excluded_account_ids: [],
  }, reconciliationRevision), true)
  assert.equal(runtime.selectedCount.value, 4)
  assert.deepEqual(runtime.selectionScope.value.excluded_account_ids, [])

  const staleRevision = runtime.selectionRevision.value
  runtime.toggleSelect('account-1', false)
  assert.equal(runtime.reconcileScopedSelection({
    matching_count: 2,
    selected_count: 2,
    excluded_account_ids: [],
  }, staleRevision), false)
  assert.equal(runtime.isSelected('account-1'), false)
  assert.deepEqual(runtime.selectionScope.value.excluded_account_ids, ['account-1'])

  runtime.clearExplicitSelection()
  assert.equal(runtime.scopedSelectionActive.value, true)
  runtime.clearSelection()
  assert.equal(runtime.scopedSelectionActive.value, false)
  assert.equal(runtime.selectedCount.value, 0)

  runtime.selectAllAccounts()
  assert.equal(runtime.scopedSelectionActive.value, true)
  assert.equal(runtime.selectedCount.value, 5)
  assert.deepEqual(runtime.selectionScope.value, {
    mode: 'all',
    excluded_account_ids: [],
  })
  runtime.toggleSelect('account-1', false)
  assert.equal(runtime.selectedCount.value, 4)
  assert.deepEqual(runtime.selectionScope.value.excluded_account_ids, ['account-1'])
  const allSelectionRevision = runtime.selectionRevision.value
  assert.equal(runtime.reconcileScopedSelection({
    matching_count: 5,
    selected_count: 4,
    excluded_account_ids: ['account-1'],
  }, allSelectionRevision), true)
  assert.equal(runtime.selectedCount.value, 4)
  runtime.clearSelection()

  const bulkAccountIds = Array.from({ length: 174 }, (_, index) => `bulk-${index + 1}`)
  const bulkSelectedIds = ref(bulkAccountIds)
  const bulkEnableCalls = []
  const syncCalls = []
  const accessTokenRefreshCalls = []
  const originalBulkEnable = accountsApi.bulkEnable
  const originalSyncAccountsWithProgress = accountsApi.syncAccountsWithProgress
  const originalRefreshAccessTokensWithProgress = accountsApi.refreshAccessTokensWithProgress
  accountsApi.bulkEnable = async (target, onProgress, targetCount) => {
    bulkEnableCalls.push({ target, targetCount })
    onProgress?.({
      total: targetCount,
      processed: 1,
      done: false,
      events: [{
        sequence: 1,
        timestamp: '2026-07-31T00:00:00Z',
        account_id: target[0],
        account_label: target[0],
        action: 'enable_account',
        status: 'success',
        message: '账号已启用',
      }],
    })
    return {
      progress: {
        total: targetCount,
        processed: targetCount,
        done: true,
        error: null,
        events: [],
        result: {
          updated: targetCount,
          removed: 0,
          updated_ids: [...target],
          removed_ids: [],
          errors: [],
        },
      },
    }
  }
  accountsApi.syncAccountsWithProgress = async (target) => {
    syncCalls.push([...target])
    return {
      progress: {
        total: target.length,
        processed: target.length,
        done: true,
        error: null,
        total_quota: target.length * 3,
        result: { synced: target.length, updated_ids: [...target], removed_ids: [], errors: [] },
      },
    }
  }
  accountsApi.refreshAccessTokensWithProgress = async (target) => {
    accessTokenRefreshCalls.push([...target])
    return {
      progress: {
        total: target.length,
        processed: target.length,
        done: true,
        error: null,
        total_quota: 0,
        result: { refreshed: target.length, updated_ids: [...target], removed_ids: [], errors: [] },
      },
    }
  }
  try {
    toastState.toasts.splice(0)
    const bulkProgress = useAccountBulkProgressRuntime()
    const bulkRuntime = useAccountBulkActionsRuntime({
      bulkProgress,
      accountSelection: {
        selectedIds: bulkSelectedIds,
        selectedCount: computed(() => bulkSelectedIds.value.length),
        scopedSelectionActive: ref(false),
        selectionScope: computed(() => ({
          mode: 'explicit',
          account_ids: bulkSelectedIds.value,
        })),
        clearSelection: () => {},
        removeSelectedIds: () => {},
      },
        accountGroups: ref([]),
        proxyGroups: ref([]),
        selectedBindGroupId: ref(''),
      normalizeErrorMessage: error => String(error),
      setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
      loadData: async () => {},
      reconcileSelection: async () => true,
      applyAccountGroupsPayload: () => {},
    })
    const confirmDialog = useConfirmDialog()

    let actionPromise = bulkRuntime.runBulkAction('enable')
    await Promise.resolve()
    confirmDialog.confirm()
    await actionPromise
    assert.equal(bulkEnableCalls.length, 1)
    assert.deepEqual(bulkEnableCalls[0].target, bulkAccountIds)
    assert.equal(bulkEnableCalls[0].targetCount, bulkAccountIds.length)
    assert.equal(
      bulkProgress.operationEvents.value.some(event => event.action === 'enable_account'),
      true,
    )

    actionPromise = bulkRuntime.runBulkAction('sync')
    await Promise.resolve()
    confirmDialog.confirm()
    await actionPromise
    assert.equal(syncCalls.length, 1)
    assert.deepEqual(syncCalls[0], bulkAccountIds)
    assert.equal(bulkProgress.refreshProgress.value?.total_quota, 522)
    assert.equal(bulkProgress.bulkStopEnabled.value, false)

    bulkSelectedIds.value = [...bulkAccountIds]
    actionPromise = bulkRuntime.runBulkAction('refresh-access-token')
    await Promise.resolve()
    confirmDialog.confirm()
    await actionPromise
    assert.equal(accessTokenRefreshCalls.length, 1)
    assert.deepEqual(accessTokenRefreshCalls[0], bulkAccountIds)
    assert.equal(
      toastState.toasts.length,
      0,
      '账号批量执行结果已在任务抽屉显示时不应重复弹出 Toast',
    )

    const singleRequestProgress = useAccountBulkProgressRuntime()
    singleRequestProgress.start('单次后端操作', 174, 'sync')
    assert.equal(singleRequestProgress.canStopRefreshProgress.value, false)
    assert.equal(singleRequestProgress.requestStop(), false)
    assert.equal(singleRequestProgress.close(), false)
    singleRequestProgress.end()

    const multiBatchProgress = useAccountBulkProgressRuntime()
    multiBatchProgress.start('多批前端操作', 174, 'sync', { stoppable: true })
    assert.equal(multiBatchProgress.canStopRefreshProgress.value, true)
    assert.equal(multiBatchProgress.requestStop(), true)
    multiBatchProgress.end()

    const eventProgress = useAccountBulkProgressRuntime()
    eventProgress.start('导入账号', 2, 'import')
    eventProgress.update({
      total: 2,
      processed: 0,
      stage: 'save_accounts',
      stage_label: '保存账号',
    })
    eventProgress.update({
      total: 2,
      processed: 1,
      stage: 'save_accounts',
      stage_label: '保存账号',
      events: [{
        sequence: 1,
        timestamp: '2026-07-31T00:00:01Z',
        account_id: 'account-1',
        account_label: 'first@example.com',
        action: 'import_account',
        status: 'success',
        message: '账号已保存',
      }],
    })
    eventProgress.update({
      total: 2,
      processed: 1,
      events: [{
        sequence: 1,
        timestamp: '2026-07-31T00:00:01Z',
        account_id: 'account-1',
        account_label: 'first@example.com',
        action: 'import_account',
        status: 'success',
        message: '账号已保存',
      }],
    })
    eventProgress.finish({
      total: 2,
      processed: 2,
      import_result: { added: 1, skipped: 1, synced: 0, failed: 0 },
    })
    assert.deepEqual(
      eventProgress.operationEvents.value.map(event => event.message),
      ['账号已保存'],
    )
    assert.equal(eventProgress.canCloseRefreshProgress.value, true)

    const partialFailureProgress = useAccountBulkProgressRuntime()
    partialFailureProgress.start('批量刷新 AT', 2, 'credentials')
    partialFailureProgress.update({
      total: 2,
      processed: 2,
      events: [{
        sequence: 1,
        timestamp: '2026-07-31T00:00:01Z',
        account_id: 'account-2',
        account_label: 'second@example.com',
        action: 'refresh_access_token',
        status: 'failed',
        message: '刷新失败',
      }],
    })
    partialFailureProgress.finish({
      total: 2,
      processed: 2,
      status_label: '部分完成',
      tone: 'warning',
      summary_items: [
        { key: 'refreshed', label: '刷新', value: 1 },
        { key: 'failed', label: '失败', value: 1, tone: 'danger' },
      ],
      result: {
        refreshed: 1,
        errors: [{ id: 'account-2', code: 'refresh_failed', message: '刷新失败' }],
      },
    })
    assert.equal(partialFailureProgress.refreshProgressStatusText.value, '部分完成')
    assert.equal(partialFailureProgress.operationEvents.value.at(-1)?.status, 'failed')
    assert.equal(partialFailureProgress.operationEvents.value.at(-1)?.message, '刷新失败')

    const detailedFailureProgress = useAccountBulkProgressRuntime()
    detailedFailureProgress.start('批量刷新 AT', 1, 'credentials')
    detailedFailureProgress.update({
      total: 1,
      processed: 1,
      events: [{
        sequence: 1,
        timestamp: '2026-07-31T00:00:01Z',
        account_id: 'account-3',
        account_label: 'third@example.com',
        action: 'refresh_access_token',
        status: 'failed',
        message: '刷新失败 · RT 已失效',
      }],
    })
    detailedFailureProgress.finish({
      total: 1,
      processed: 1,
      error: '批量刷新 AT 失败',
    })
    const detailedFailureMessages = detailedFailureProgress.operationEvents.value
      .filter(event => event.status === 'failed')
      .map(event => event.message)
    assert.deepEqual(
      detailedFailureMessages,
      ['刷新失败 · RT 已失效'],
    )
    assert.equal(detailedFailureMessages.includes('批量刷新 AT 失败'), false)

    const summaryOnlyProgress = useAccountBulkProgressRuntime()
    summaryOnlyProgress.start('批量启用账号', 2, 'mutation')
    summaryOnlyProgress.finish({
      total: 2,
      processed: 2,
      result: { updated: 2, updated_ids: ['account-1', 'account-2'], errors: [] },
    })
    assert.equal(summaryOnlyProgress.operationEvents.value.length, 0)
    assert.equal(summaryOnlyProgress.refreshProgressStatusText.value, '已完成')

    const importProgress = useAccountBulkProgressRuntime()
    const importRuntime = useAccountImportRuntime({
      bulkProgress: importProgress,
      normalizeErrorMessage: error => String(error),
      setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
      loadData: async () => {},
    })
    await importRuntime.updateRemoteImportProgress({ title: '导入远程账号', total: 30 })
    assert.equal(importProgress.showRefreshProgress.value, true)
    assert.equal(importProgress.batchBusy.value, true)
    assert.equal(importProgress.refreshProgress.value?.stage_label, '正在创建任务')
    await importRuntime.updateRemoteImportProgress({
      title: '导入远程账号',
      total: 30,
      job: {
        job_id: 'job-1',
        status: 'running',
        stage: 'sync_accounts',
        stage_label: '同步账号与额度',
        stage_total: 20,
        stage_completed: 8,
        terminal: false,
        progress_total: 20,
        progress_completed: 8,
        status_label: '同步账号与额度',
        tone: 'info',
        error: '',
        summary_items: [
          { key: 'added', label: '新增', value: 20 },
          { key: 'skipped', label: '更新 / 跳过', value: 10 },
          { key: 'synced', label: '同步', value: 8 },
          { key: 'failed', label: '失败', value: 0 },
        ],
        result_message: '',
        result_tone: 'info',
        created_at: '2026-07-31T00:00:00Z',
        updated_at: '2026-07-31T00:00:01Z',
        total: 30,
        completed: 30,
        added: 20,
        skipped: 10,
        synced: 8,
        failed: 0,
        failed_total: 0,
        errors: [],
      },
    })
    assert.equal(importProgress.refreshProgress.value?.total, 20)
    assert.equal(importProgress.refreshProgress.value?.processed, 8)
    assert.equal(importProgress.refreshProgress.value?.stage_label, '同步账号与额度')
    await importRuntime.updateRemoteImportProgress({
      title: '导入远程账号',
      total: 30,
      job: {
        job_id: 'job-1',
        status: 'completed',
        stage: 'completed',
        stage_label: '完成',
        stage_total: 30,
        stage_completed: 30,
        terminal: true,
        progress_total: 30,
        progress_completed: 30,
        status_label: '已完成',
        tone: 'success',
        error: '',
        summary_items: [
          { key: 'added', label: '新增', value: 20 },
          { key: 'skipped', label: '更新 / 跳过', value: 10 },
          { key: 'synced', label: '同步', value: 20 },
          { key: 'failed', label: '失败', value: 0 },
        ],
        result_message: '导入完成 · 新增 20 · 更新 / 跳过 10 · 同步 20',
        result_tone: 'success',
        created_at: '2026-07-31T00:00:00Z',
        updated_at: '2026-07-31T00:00:02Z',
        total: 30,
        completed: 30,
        added: 20,
        skipped: 10,
        synced: 20,
        failed: 0,
        failed_total: 0,
        errors: [],
      },
    })
    assert.equal(importProgress.batchBusy.value, false)
    assert.equal(importProgress.showRefreshProgress.value, true)
    assert.equal(importProgress.refreshProgress.value?.done, true)
    assert.deepEqual(importProgress.refreshProgress.value?.import_result, {
      added: 20,
      skipped: 10,
      synced: 20,
      failed: 0,
    })

    const failedImportProgress = useAccountBulkProgressRuntime()
    const failedImportRuntime = useAccountImportRuntime({
      bulkProgress: failedImportProgress,
      normalizeErrorMessage: error => String(error),
      setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
      loadData: async () => {},
    })
    await failedImportRuntime.updateRemoteImportProgress({
      title: '导入远程账号',
      total: 100,
      job: {
        job_id: 'job-failed-progress',
        status: 'failed',
        stage: 'completed',
        stage_label: '完成',
        stage_total: 100,
        stage_completed: 7,
        terminal: true,
        progress_total: 100,
        progress_completed: 7,
        status_label: '失败',
        tone: 'danger',
        error: '远端连接中断',
        summary_items: [
          { key: 'added', label: '新增', value: 0 },
          { key: 'skipped', label: '更新 / 跳过', value: 0 },
          { key: 'synced', label: '同步', value: 0 },
          { key: 'failed', label: '失败', value: 32, tone: 'danger' },
        ],
        result_message: '导入失败 · 远端连接中断',
        result_tone: 'danger',
        created_at: '2026-07-31T00:00:00Z',
        updated_at: '2026-07-31T00:00:01Z',
        total: 100,
        completed: 7,
        added: 0,
        skipped: 0,
        synced: 0,
        failed: 20,
        failed_total: 32,
        errors: [{ stage: 'fetch', name: 'account-8', error: '远端连接中断' }],
      },
    })
    assert.equal(failedImportProgress.refreshProgress.value?.total, 100)
    assert.equal(failedImportProgress.refreshProgress.value?.processed, 7)
    assert.equal(failedImportProgress.refreshProgress.value?.done, true)
    assert.equal(failedImportProgress.refreshProgress.value?.import_result?.failed, 32)

    let remoteListReloads = 0
    const trackedProgress = useAccountBulkProgressRuntime()
    const trackedRuntime = useAccountImportRuntime({
      bulkProgress: trackedProgress,
      normalizeErrorMessage: error => String(error),
      setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
      loadData: async () => { remoteListReloads += 1 },
    })
    trackedRuntime.showImportModal.value = true
    await trackedRuntime.startRemoteImportTracking({
      mode: 'cpa',
      source_id: 'pool-1',
      title: '导入远程 CPA',
      total: 2,
      job: {
        job_id: 'job-terminal',
        status: 'completed',
        stage: 'completed',
        stage_label: '完成',
        stage_total: 2,
        stage_completed: 2,
        terminal: true,
        progress_total: 2,
        progress_completed: 2,
        status_label: '已完成',
        tone: 'success',
        error: '',
        summary_items: [
          { key: 'added', label: '新增', value: 2 },
          { key: 'skipped', label: '更新 / 跳过', value: 0 },
          { key: 'synced', label: '同步', value: 2 },
          { key: 'failed', label: '失败', value: 0 },
        ],
        result_message: '导入完成 · 新增 2 · 同步 2',
        result_tone: 'success',
        created_at: '2026-07-31T00:00:00Z',
        updated_at: '2026-07-31T00:00:01Z',
        total: 2,
        completed: 2,
        added: 2,
        skipped: 0,
        synced: 2,
        failed: 0,
        failed_total: 0,
        errors: [],
      },
    })
    await Promise.resolve()
    assert.equal(trackedRuntime.showImportModal.value, false)
    assert.equal(trackedProgress.batchBusy.value, false)
    assert.equal(trackedProgress.refreshProgress.value?.done, true)
    assert.equal(remoteListReloads, 1)

    const interruptedTrackingProgress = useAccountBulkProgressRuntime()
    const interruptedTrackingRuntime = useAccountImportRuntime({
      bulkProgress: interruptedTrackingProgress,
      normalizeErrorMessage: error => String(error),
      setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
      loadData: async () => {},
      trackingWindowMs: () => 0,
    })
    await interruptedTrackingRuntime.startRemoteImportTracking({
      mode: 'cpa',
      source_id: 'pool-tracking-expired',
      title: '导入远程 CPA',
      total: 10,
      job: {
        job_id: 'job-tracking-expired',
        status: 'running',
        stage: 'save_accounts',
        stage_label: '保存账号',
        stage_total: 10,
        stage_completed: 4,
        terminal: false,
        progress_total: 10,
        progress_completed: 4,
        status_label: '保存账号',
        tone: 'info',
        error: '',
        summary_items: [
          { key: 'added', label: '新增', value: 4 },
          { key: 'skipped', label: '更新 / 跳过', value: 0 },
          { key: 'synced', label: '同步', value: 0 },
          { key: 'failed', label: '失败', value: 0 },
        ],
        result_message: '',
        result_tone: 'info',
        created_at: '2026-07-31T00:00:00Z',
        updated_at: '2026-07-31T00:00:01Z',
        total: 10,
        completed: 4,
        added: 4,
        skipped: 0,
        synced: 0,
        failed: 0,
        failed_total: 0,
        errors: [],
      },
    })
    await Promise.resolve()
    assert.equal(interruptedTrackingProgress.batchBusy.value, false)
    assert.equal(interruptedTrackingProgress.refreshProgress.value?.done, false)
    assert.equal(interruptedTrackingProgress.refreshProgress.value?.error, null)
    assert.equal(interruptedTrackingProgress.refreshProgress.value?.processed, 4)
    assert.equal(interruptedTrackingProgress.refreshProgressStatusText.value, '后台继续执行')
    assert.equal(interruptedTrackingProgress.canCloseRefreshProgress.value, true)
    assert.equal(interruptedTrackingProgress.operationEvents.value.length, 0)

    const originalFinishOAuthLogin = accountImportsApi.finishOAuthLogin
    const successfulSyncAccountsWithProgress = accountsApi.syncAccountsWithProgress
    toastState.toasts.splice(0)
    accountImportsApi.finishOAuthLogin = async () => ({
      added: 1,
      skipped: 0,
      synced: 0,
      updated_ids: ['oauth-account'],
      removed_ids: [],
      errors: [],
    })
    try {
      const oauthProgress = useAccountBulkProgressRuntime()
      const oauthRuntime = useAccountImportRuntime({
        bulkProgress: oauthProgress,
        normalizeErrorMessage: error => String(error),
        setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
        loadData: async () => {},
      })
      oauthRuntime.oauthSessionId.value = 'session-1'
      oauthRuntime.oauthCallbackText.value = 'http://localhost/callback?code=ok'
      await oauthRuntime.finishOAuthLogin()
      assert.equal(syncCalls.length, 2)
      assert.deepEqual(syncCalls[1], ['oauth-account'])
      assert.equal(oauthProgress.showRefreshProgress.value, true)
      assert.equal(oauthProgress.batchBusy.value, false)
      assert.equal(oauthProgress.refreshProgress.value?.done, true)
      assert.deepEqual(oauthProgress.refreshProgress.value?.import_result, {
        added: 1,
        skipped: 0,
        synced: 1,
        failed: 0,
      })
      assert.equal(
        toastState.toasts.length,
        0,
        '账号导入结果已在任务抽屉显示时不应重复弹出 Toast',
      )

      let partialErrorPrefix = ''
      accountsApi.syncAccountsWithProgress = async () => {
        throw new Error('sync unavailable')
      }
      const partialProgress = useAccountBulkProgressRuntime()
      const partialRuntime = useAccountImportRuntime({
        bulkProgress: partialProgress,
        normalizeErrorMessage: error => String(error instanceof Error ? error.message : error),
        setError: (prefix) => { partialErrorPrefix = prefix },
        loadData: async () => {},
      })
      partialRuntime.oauthSessionId.value = 'session-2'
      partialRuntime.oauthCallbackText.value = 'oauth-code'
      await partialRuntime.finishOAuthLogin()
      assert.equal(partialErrorPrefix, 'OAuth 凭据已保存，但同步失败')
      assert.deepEqual(partialProgress.refreshProgress.value?.import_result, {
        added: 1,
        skipped: 0,
        synced: 0,
        failed: 1,
      })
      assert.match(partialProgress.refreshProgress.value?.error || '', /凭据已保存/)
    } finally {
      accountImportsApi.finishOAuthLogin = originalFinishOAuthLogin
      accountsApi.syncAccountsWithProgress = successfulSyncAccountsWithProgress
    }

    const originalImportAccounts = accountsApi.importAccounts
    const originalCleanupImportedAbnormalAccounts = accountsApi.cleanupImportedAbnormalAccounts
    const originalCleanupSyncAccountsWithProgress = accountsApi.syncAccountsWithProgress
    const cleanupCalls = []
    accountsApi.importAccounts = async () => ({
      status: 'ok',
      added: 1,
      skipped: 0,
      synced: 0,
      updated_ids: ['cleanup-account'],
      removed_ids: [],
      errors: ['cleanup-account: unauthorized'],
      events: [{
        sequence: 1,
        timestamp: '2026-07-31T00:00:01Z',
        account_id: 'cleanup-account',
        account_label: 'cleanup@example.com',
        action: 'import_account',
        status: 'success',
        message: '账号已保存',
      }],
    })
    accountsApi.syncAccountsWithProgress = async () => ({
      progress: {
        total: 1,
        processed: 1,
        done: true,
        error: null,
        result: { synced: 1, updated_ids: ['cleanup-account'], removed_ids: [], errors: [] },
      },
    })
    accountsApi.cleanupImportedAbnormalAccounts = async (accountIds, remove) => {
      cleanupCalls.push({ accountIds: [...accountIds], remove })
      return {
        status: 'ok',
        checked: 1,
        abnormal: 1,
        removed: remove ? 1 : 0,
        updated_ids: [],
        removed_ids: remove ? ['cleanup-account'] : [],
        errors: [],
        events: remove
          ? [{
              sequence: 1,
              timestamp: '2026-07-31T00:00:02Z',
              account_id: 'cleanup-account',
              account_label: 'cleanup@example.com',
              action: 'delete_account',
              status: 'success',
              message: '导入后异常账号已删除',
            }]
          : [],
      }
    }
    try {
      const cleanupProgress = useAccountBulkProgressRuntime()
      const cleanupRuntime = useAccountImportRuntime({
        bulkProgress: cleanupProgress,
        normalizeErrorMessage: error => String(error),
        setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
        loadData: async () => {},
      })
      cleanupRuntime.manualTokenText.value = 'cleanup-token'
      const cleanupPromise = cleanupRuntime.importManualTokenText()
      await Promise.resolve()
      confirmDialog.confirm()
      for (let attempt = 0; attempt < 10 && !confirmDialog.open.value; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 0))
      }
      assert.equal(confirmDialog.title.value, '移除本次确认失效账号？')
      confirmDialog.confirm()
      await cleanupPromise
      assert.deepEqual(
        cleanupCalls,
        [
          { accountIds: ['cleanup-account'], remove: false },
          { accountIds: ['cleanup-account'], remove: true },
        ],
      )
      const cleanupDeleteEvents = cleanupProgress.operationEvents.value.filter(
        event => event.action === 'delete_account'
          && event.message === '导入后异常账号已删除',
      )
      assert.equal(cleanupDeleteEvents.length, 1)

      accountsApi.importAccounts = async () => ({
        status: 'ok',
        added: 1,
        skipped: 0,
        synced: 0,
        updated_ids: ['local-file-account'],
        removed_ids: [],
        errors: [],
        events: [{
          sequence: 1,
          timestamp: '2026-07-31T00:00:03Z',
          account_id: 'local-file-account',
          account_label: 'local@example.com',
          action: 'import_account',
          status: 'success',
          message: '账号已保存',
        }],
      })
      const localFileProgress = useAccountBulkProgressRuntime()
      const localFileRuntime = useAccountImportRuntime({
        bulkProgress: localFileProgress,
        normalizeErrorMessage: error => String(error),
        setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
        loadData: async () => {},
      })
      const localFilePromise = localFileRuntime.importLocalCPAFiles([{
        name: 'local-account.json',
        text: async () => JSON.stringify({ access_token: 'local-file-token' }),
      }])
      await Promise.resolve()
      confirmDialog.confirm()
      await localFilePromise
      assert.deepEqual(
        localFileProgress.operationEvents.value.map(event => event.message),
        ['账号已保存'],
      )
    } finally {
      accountsApi.importAccounts = originalImportAccounts
      accountsApi.cleanupImportedAbnormalAccounts = originalCleanupImportedAbnormalAccounts
      accountsApi.syncAccountsWithProgress = originalCleanupSyncAccountsWithProgress
    }

    let failedSelectionReloads = 0
    let failedSelectionErrors = 0
    accountsApi.refreshAccessTokensWithProgress = async (_target, onProgress) => {
      onProgress?.({
        total: 174,
        processed: 57,
        done: false,
        result: null,
      })
      throw new Error('polling interrupted')
    }
    const failedSelectionProgress = useAccountBulkProgressRuntime()
    const failedSelectionRuntime = useAccountBulkActionsRuntime({
      bulkProgress: failedSelectionProgress,
      accountSelection: {
        selectedIds: ref([]),
        selectedCount: ref(174),
        scopedSelectionActive: ref(true),
        selectionScope: computed(() => ({
          mode: 'filter',
          keyword: 'plus',
          status: 'normal',
          group_id: 'group-a',
          excluded_account_ids: [],
        })),
        clearSelection: () => {},
        removeSelectedIds: () => {},
      },
      accountGroups: ref([]),
      proxyGroups: ref([]),
      selectedBindGroupId: ref(''),
      normalizeErrorMessage: error => String(error),
      setError: () => { failedSelectionErrors += 1 },
      loadData: async () => { failedSelectionReloads += 1 },
      reconcileSelection: async () => true,
      applyAccountGroupsPayload: () => {},
    })
    actionPromise = failedSelectionRuntime.runBulkAction('refresh-access-token')
    await Promise.resolve()
    confirmDialog.confirm()
    await actionPromise
    assert.equal(failedSelectionReloads, 1)
    assert.equal(failedSelectionErrors, 1)
    assert.equal(failedSelectionProgress.refreshProgress.value?.processed, 57)
    assert.equal(failedSelectionProgress.refreshProgress.value?.done, true)
  } finally {
    accountsApi.bulkEnable = originalBulkEnable
    accountsApi.syncAccountsWithProgress = originalSyncAccountsWithProgress
    accountsApi.refreshAccessTokensWithProgress = originalRefreshAccessTokensWithProgress
  }

  const originalSingleSyncAccountsWithProgress = accountsApi.syncAccountsWithProgress
  const originalGetAccount = accountsApi.get
  const originalSingleBulkEnable = accountsApi.bulkEnable
  const originalSingleBulkDisable = accountsApi.bulkDisable
  let resolveSyncAccount = () => {}
  let syncAccountCalls = 0
  let getAccountCalls = 0
  let enableAccountCalls = 0
  let disableAccountCalls = 0
  const singleOperationBatchBusy = ref(false)
  accountsApi.syncAccountsWithProgress = async (target, onProgress) => {
    syncAccountCalls += 1
    await new Promise((resolve) => {
      resolveSyncAccount = resolve
    })
    const progress = {
      total: target.length,
      processed: target.length,
      done: true,
      error: null,
      result: { synced: target.length, updated_ids: [...target], removed_ids: [], errors: [] },
    }
    onProgress?.(progress)
    return { progress }
  }
  accountsApi.get = async () => {
    getAccountCalls += 1
    throw new Error('编辑操作不应在另一个单账号操作期间启动')
  }
  accountsApi.bulkEnable = async (accountIds, _onProgress, targetCount) => {
    enableAccountCalls += 1
    assert.deepEqual(accountIds, ['account-1'])
    assert.equal(targetCount, 1)
    return {
      updated_ids: [...accountIds],
      removed_ids: [],
      errors: [],
      events: [],
      progress: {
        total: 1,
        processed: 1,
        done: true,
        status_label: '已完成',
        tone: 'success',
        summary_items: [{ key: 'updated', label: '更新', value: 1 }],
        events: [],
        result: { updated: 1, updated_ids: [...accountIds], removed_ids: [], errors: [] },
      },
    }
  }
  accountsApi.bulkDisable = async (accountIds, _onProgress, targetCount) => {
    disableAccountCalls += 1
    assert.deepEqual(accountIds, ['account-1'])
    assert.equal(targetCount, 1)
    return {
      updated_ids: [...accountIds],
      removed_ids: [],
      errors: [],
      events: [],
      progress: {
        total: 1,
        processed: 1,
        done: true,
        status_label: '已完成',
        tone: 'success',
        summary_items: [{ key: 'updated', label: '更新', value: 1 }],
        events: [],
        result: { updated: 1, updated_ids: [...accountIds], removed_ids: [], errors: [] },
      },
    }
  }
  try {
    const singleOperationProgress = useAccountBulkProgressRuntime()
    const crudRuntime = useAccountCrudRuntime({
      bulkProgress: singleOperationProgress,
      loadData: async () => {},
      loadAccountGroups: async () => {},
      normalizeErrorMessage: error => String(error),
      setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
      isBatchBusy: () => singleOperationBatchBusy.value,
    })
    const confirmDialog = useConfirmDialog()
    const firstAccount = {
      id: 'account-1',
      email: 'first@example.com',
      display_name: 'first@example.com',
      enabled: true,
      enabled_action: 'enable',
      enabled_action_label: '恢复启用',
    }

    const togglePromise = crudRuntime.toggleEnabled(firstAccount)
    await Promise.resolve()
    assert.equal(confirmDialog.title.value, '确认恢复启用')
    assert.match(confirmDialog.message.value, /账号 first@example\.com 执行“恢复启用”/)
    confirmDialog.confirm()
    await togglePromise
    assert.equal(enableAccountCalls, 1)
    assert.equal(disableAccountCalls, 0)

    const syncPromise = crudRuntime.syncAccount(firstAccount)
    await Promise.resolve()
    assert.equal(crudRuntime.accountOperationBusy.value, true)
    assert.equal(confirmDialog.title.value, '同步账号与额度')
    assert.match(confirmDialog.message.value, /first@example\.com/)
    assert.equal(confirmDialog.message.value.includes('account-1'), false)

    await crudRuntime.openEditModal({ id: 'account-2' })
    assert.equal(getAccountCalls, 0)
    assert.equal(confirmDialog.title.value, '同步账号与额度')

    confirmDialog.confirm()
    await waitFor(() => syncAccountCalls === 1, 'single-account sync to start')
    assert.equal(syncAccountCalls, 1)
    assert.equal(crudRuntime.syncingAccountIds.value.has('account-1'), true)
    resolveSyncAccount()
    await syncPromise
    assert.equal(crudRuntime.accountOperationBusy.value, false)
    assert.equal(crudRuntime.syncingAccountIds.value.size, 0)
    assert.equal(singleOperationProgress.refreshProgress.value?.done, true)
    assert.equal(singleOperationProgress.showRefreshProgress.value, true)

    const refreshPromise = crudRuntime.refreshAccessToken(firstAccount)
    await Promise.resolve()
    assert.match(confirmDialog.message.value, /first@example\.com/)
    assert.equal(confirmDialog.message.value.includes('account-1'), false)
    confirmDialog.cancel()
    await refreshPromise

    accountsApi.get = async () => ({
      id: 'account-2',
      source: 'web',
      backend_status: '正常',
      quota_unknown: true,
      configuration: {
        type: '',
        source_type: 'web',
        group_id: '',
        proxy: '',
        quota: 0,
      },
    })
    await crudRuntime.openEditModal({ id: 'account-2' })
    assert.equal(crudRuntime.showModal.value, true)
    assert.equal(crudRuntime.accountOperationBusy.value, true)
    crudRuntime.closeModal()
    assert.equal(crudRuntime.accountOperationBusy.value, false)

    singleOperationBatchBusy.value = true
    await crudRuntime.refreshAccessToken(firstAccount)
    assert.equal(crudRuntime.accountOperationBusy.value, false)
    assert.equal(confirmDialog.open.value, false)

    singleOperationBatchBusy.value = false
    crudRuntime.openCreateModal()
    assert.equal(crudRuntime.showModal.value, true)
    assert.equal(crudRuntime.accountOperationBusy.value, true)
    await crudRuntime.syncAccount(firstAccount)
    assert.equal(confirmDialog.open.value, false)
    crudRuntime.closeModal()
    assert.equal(crudRuntime.accountOperationBusy.value, false)
  } finally {
    accountsApi.syncAccountsWithProgress = originalSingleSyncAccountsWithProgress
    accountsApi.get = originalGetAccount
    accountsApi.bulkEnable = originalSingleBulkEnable
    accountsApi.bulkDisable = originalSingleBulkDisable
  }

  for (const wrapper of ['accounts', 'items', 'data', 'results']) {
    const token = `token-${wrapper}`
    const parsed = parseAccountArchive(JSON.stringify({
      [wrapper]: [{
        id: `account-${wrapper}`,
        access_token: token,
        refresh_token: `refresh-${wrapper}`,
        id_token: `id-${wrapper}`,
        status: 'normal',
      }],
    }), `${wrapper}.json`)
    assert.equal(parsed.length, 1)
    assert.equal(parsed[0].access_token, token)
    assert.equal(parsed[0].refresh_token, `refresh-${wrapper}`)
    assert.equal(parsed[0].id_token, `id-${wrapper}`)
    assert.equal(parsed[0].status, 'normal')
  }

  const originalAdapter = apiClient.defaults.adapter
  globalThis.window = {
    localStorage: {
      getItem: () => '',
      setItem: () => {},
      removeItem: () => {},
    },
  }
  try {
    const accountRequests = []
    apiClient.defaults.adapter = async (config) => {
      accountRequests.push(config)
      const url = String(config.url || '')
      const method = String(config.method || 'get').toLowerCase()
      const data = url === '/api/accounts' && method === 'delete'
        ? { progress_id: 'delete-operation', target_ids: ['account-1'], errors: [] }
        : url === '/api/accounts'
          ? {
              added: 1,
              skipped: 0,
              synced: 1,
              updated_ids: ['account-imported'],
              errors: [],
              events: [],
              status_label: '已完成',
              tone: 'success',
              message: '任务完成 · 新增 1 · 同步 1',
              summary_items: [
                { key: 'synced', label: '同步', value: 1 },
                { key: 'failed', label: '失败', value: 0 },
              ],
            }
        : url === '/api/accounts/update'
          ? {
              updated: 1,
              updated_ids: ['account-1'],
              removed_ids: [],
              errors: [],
              events: [],
              status_label: '已完成',
              tone: 'success',
              message: '任务完成 · 更新 1',
              summary_items: [{ key: 'updated', label: '更新', value: 1 }],
            }
        : url === '/api/accounts/batch-update'
          ? { progress_id: 'mutation-operation', target_ids: ['account-1'], errors: [] }
        : url === '/api/accounts/sync'
          ? { progress_id: 'sync-operation' }
          : url === '/api/accounts/refresh-access-token'
            ? { progress_id: 'refresh-operation' }
          : url === '/api/accounts/operations/sync-operation'
            ? {
                total: 1,
                processed: 1,
                done: true,
                events: [],
                status_label: '已完成',
                tone: 'success',
                message: '任务完成 · 同步 1',
                summary_items: [{ key: 'synced', label: '同步', value: 1 }],
                result: { synced: 1, updated_ids: ['account-1'], removed_ids: [], errors: [] },
              }
            : url === '/api/accounts/operations/refresh-operation'
              ? {
                  total: 1,
                  processed: 1,
                  done: true,
                  events: [],
                  status_label: '已完成',
                  tone: 'success',
                  message: '任务完成 · 刷新 1',
                  summary_items: [{ key: 'refreshed', label: '刷新', value: 1 }],
                  result: { refreshed: 1, updated_ids: ['account-1'], removed_ids: [], errors: [] },
                }
            : url === '/api/accounts/operations/mutation-operation'
              ? {
                  total: 1,
                  processed: 1,
                  done: true,
                  status_label: '已完成',
                  tone: 'success',
                  message: '任务完成 · 更新 1',
                  summary_items: [{ key: 'updated', label: '更新', value: 1 }],
                  events: [{
                    sequence: 1,
                    timestamp: '2026-07-31T00:00:00Z',
                    account_id: 'account-1',
                    account_label: 'account-1',
                    action: 'reset_account',
                    status: 'success',
                    message: '账号状态已重置',
                  }],
                  result: {
                    updated: 1,
                    removed: 0,
                    updated_ids: ['account-1'],
                    removed_ids: [],
                    errors: [],
                  },
                }
            : url === '/api/accounts/operations/delete-operation'
              ? {
                  total: 1,
                  processed: 1,
                  done: true,
                  status_label: '已完成',
                  tone: 'success',
                  message: '任务完成 · 移除 1',
                  summary_items: [{ key: 'removed', label: '移除', value: 1 }],
                  events: [{
                    sequence: 1,
                    timestamp: '2026-07-31T00:00:00Z',
                    account_id: 'account-1',
                    account_label: 'account-1',
                    action: 'delete_account',
                    status: 'success',
                    message: '账号已删除',
                  }],
                  result: {
                    removed: 1,
                    removed_ids: ['account-1'],
                    errors: [],
                  },
                }
            : new Blob(['[]'], { type: 'application/json' })
      return {
        data,
        status: 200,
        statusText: 'OK',
        headers: {
          'x-export-requested': '3',
          'x-exported': '2',
          'x-skipped': '1',
        },
        config,
        request: {},
      }
    }

    const imported = await accountsApi.importAccounts(
      [{ access_token: 'import-token' }],
      'web',
      { syncAfterImport: true },
    )
    assert.equal(imported.synced, 1)
    assert.equal(imported.progress?.status_label, '已完成')
    assert.equal(imported.progress?.tone, 'success')
    const importRequest = accountRequests.find(request => request.url === '/api/accounts')
    const importPayload = JSON.parse(String(importRequest.data || '{}'))
    assert.equal(importPayload.sync_after_import, true)
    assert.equal('refresh' in importPayload, false)

    const synced = await accountsApi.syncAccountsWithProgress(['account-1'])
    assert.equal(synced.progress?.result?.synced, 1)
    assert.equal(accountRequests.some(request => request.url === '/api/accounts/operations/sync-operation'), true)
    assert.equal(accountRequests.some(request => String(request.url || '').includes('/refresh/progress/')), false)

    const enabled = await accountsApi.bulkEnable(['account-1'], undefined, 1)
    assert.deepEqual(enabled.progress?.result?.updated_ids, ['account-1'])
    const statusRequest = accountRequests.find(request => request.url === '/api/accounts/batch-update')
    const statusPayload = JSON.parse(String(statusRequest.data || '{}'))
    assert.deepEqual(statusPayload.account_ids, ['account-1'])
    assert.equal(statusPayload.operation, 'enable')
    assert.equal(statusPayload.status, '正常')
    const refreshed = await accountsApi.refreshAccessTokensWithProgress(['account-1'])
    assert.deepEqual(refreshed.progress?.result?.updated_ids, ['account-1'])
    assert.equal(accountRequests.some(request => request.url === '/api/accounts/refresh-access-token'), true)
    assert.equal(accountRequests.some(request => request.url === '/api/accounts/operations/refresh-operation'), true)

    const deleteResult = await accountsApi.bulkDelete(['account-1'], undefined, 1)
    assert.deepEqual(deleteResult.progress?.result?.removed_ids, ['account-1'])
    assert.equal(deleteResult.progress?.events?.[0]?.action, 'delete_account')

    apiClient.defaults.adapter = async (config) => ({
      data: new Blob(['[]'], { type: 'application/json' }),
      status: 200,
      statusText: 'OK',
      headers: {
        'x-export-requested': '3',
        'x-exported': '2',
        'x-skipped': '1',
      },
      config,
      request: {},
    })

    const exported = await accountsApi.exportAccounts({ mode: 'all' }, 'json')
    assert.ok(exported.blob instanceof Blob)
    assert.equal(exported.requested, 3)
    assert.equal(exported.exported, 2)
    assert.equal(exported.skipped, 1)

    let reconcileCalls = 0
    let exportedTarget
    accountsApi.exportAccounts = async (target) => {
      exportedTarget = target
      return {
        blob: new Blob(['[]'], { type: 'application/json' }),
        requested: 3,
        exported: 2,
        skipped: 1,
      }
    }
    globalThis.URL = {
      createObjectURL: () => 'blob:test',
      revokeObjectURL: () => {},
    }
    globalThis.document = {
      createElement: () => ({ click: () => {}, href: '', download: '' }),
      body: { appendChild: () => {}, removeChild: () => {} },
    }
    window.setTimeout = () => 0
    const exportRuntime = useAccountExportRuntime({
      accounts,
      selectedCount: computed(() => runtime.selectedCount.value),
      selectionScope: computed(() => runtime.selectionScope.value),
      scopedSelectionActive: computed(() => runtime.scopedSelectionActive.value),
      accountAllTotal: ref(5),
      accountListTotal: ref(5),
      reconcileSelection: async () => {
        reconcileCalls += 1
        return true
      },
      setError: (prefix, error) => { throw new Error(`${prefix}: ${error}`) },
    })
    runtime.selectAllMatching()
    const exportPromise = exportRuntime.exportAccounts('selected', 'json')
    await Promise.resolve()
    useConfirmDialog().confirm()
    await exportPromise
    assert.equal(reconcileCalls, 1)
    assert.deepEqual(exportedTarget, runtime.selectionScope.value)
    assert.equal(toastState.toasts.at(-1)?.message, '已导出 2 个账号，跳过 1 个 · 完整账号 JSON')
  } finally {
    apiClient.defaults.adapter = originalAdapter
    delete globalThis.window
  }
} finally {
  await server.close()
}
