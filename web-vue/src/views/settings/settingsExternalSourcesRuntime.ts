import { computed, ref } from 'vue'

import {
  accountImportsApi,
  remoteImportJobIsActive,
  type CPAPool,
  type Sub2APIRemoteGroup,
  type Sub2APIServer,
} from '@/api/accountImports'
import { accountsApi, type AccountGroup } from '@/api/accounts'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import type { usePageRuntime } from '@/composables/usePageRuntime'
import { usePageQuery } from '@/composables/usePageQuery'
import { useToast } from '@/composables/useToast'
import { errorMessage } from '@/lib/errorMessage'
import {
  buildCPAPayload,
  buildSub2APIPayload,
  createCPAForm,
  createSub2APIForm,
  hasSub2APICredentials,
} from '@/views/settings/externalSourceView'

type SettingsExternalSourcesRuntimeOptions = {
  runtime: ReturnType<typeof usePageRuntime>
  cpaRequestKey: string
  sub2apiRequestKey: string
}

export function useSettingsExternalSourcesRuntime(options: SettingsExternalSourcesRuntimeOptions) {
  let externalSourcesLoadGeneration = 0
  const externalSourcesLoaded = ref(false)
  const cpaLoading = ref(false)
  const sub2apiLoading = ref(false)
  const savingExternalSource = ref('')
  const testingExternalSource = ref('')
  const externalSourceModal = ref<'cpa' | 'sub2api' | ''>('')
  const remoteImportModal = ref<'cpa' | 'sub2api' | ''>('')
  const remoteImportCPAPoolId = ref('')
  const remoteImportSub2APIServerId = ref('')
  const remoteImportSub2APIGroupId = ref<string | undefined>(undefined)
  const remoteImportTargetGroupValue = ref('__preserve__')
  const remoteImportBusy = ref(false)
  const accountGroups = ref<AccountGroup[]>([])
  const accountGroupsLoading = ref(false)
  const accountGroupsLoaded = ref(false)
  const cpaPools = ref<CPAPool[]>([])
  const sub2apiServers = ref<Sub2APIServer[]>([])
  const sub2apiGroups = ref<Record<string, Sub2APIRemoteGroup[]>>({})
  const editingCPAPoolId = ref('')
  const editingSub2APIId = ref('')
  const cpaForm = ref(createCPAForm())
  const sub2apiForm = ref(createSub2APIForm())
  const toast = useToast()
  const confirmDialog = useConfirmDialog()
  const externalSourcesLoading = computed(() => cpaLoading.value || sub2apiLoading.value)
  const remoteImportActive = computed(() => (
    [...cpaPools.value, ...sub2apiServers.value]
      .some((source) => remoteImportJobIsActive(source.import_job))
  ))

  const cpaPoolsQuery = usePageQuery({
    runtime: options.runtime,
    key: options.cpaRequestKey,
    loading: cpaLoading,
    errorMessage: 'Failed to load CPA connections',
  })
  const sub2apiServersQuery = usePageQuery({
    runtime: options.runtime,
    key: options.sub2apiRequestKey,
    loading: sub2apiLoading,
    errorMessage: 'Failed to load Sub2API connections',
  })

  function resetCPAForm() {
    editingCPAPoolId.value = ''
    cpaForm.value = createCPAForm()
  }

  function openCPAModal(pool?: CPAPool) {
    if (pool) {
      editCPAPool(pool)
      return
    }
    resetCPAForm()
    externalSourceModal.value = 'cpa'
  }

  function editCPAPool(pool: CPAPool) {
    editingCPAPoolId.value = pool.id
    cpaForm.value = createCPAForm(pool)
    externalSourceModal.value = 'cpa'
  }

  async function loadCPAPools() {
    await cpaPoolsQuery.run(
      () => accountImportsApi.listCPAPools(),
      {
        apply: (response) => {
          cpaPools.value = Array.isArray(response.pools) ? response.pools : []
        },
        onError: (message) => {
          cpaPools.value = []
          toast.error(message)
        },
      },
    )
  }

  async function saveCPAPool() {
    const payload = buildCPAPayload(cpaForm.value)
    if (!payload.base_url) {
      toast.warning('Enter a CPA URL')
      return
    }
    if (!editingCPAPoolId.value && !payload.secret_key) {
      toast.warning('An admin key is required to add a CPA connection')
      return
    }

    savingExternalSource.value = 'cpa'
    try {
      const response = editingCPAPoolId.value
        ? await accountImportsApi.updateCPAPool(editingCPAPoolId.value, {
            name: payload.name,
            base_url: payload.base_url,
            ...(payload.secret_key ? { secret_key: payload.secret_key } : {}),
          })
        : await accountImportsApi.createCPAPool(payload)
      cpaPools.value = response.pools || []
      resetCPAForm()
      externalSourceModal.value = ''
      toast.success('CPA connection saved')
    } catch (error) {
      toast.error(errorMessage(error, 'Failed to save CPA connection'))
    } finally {
      savingExternalSource.value = ''
    }
  }

  async function deleteCPAPool(pool: CPAPool) {
    const confirmed = await confirmDialog.ask({
      title: 'Delete CPA connection',
      message: `Delete ${pool.name || pool.base_url}? You will no longer be able to import from this CPA connection on the Accounts page.`,
      confirmText: 'Delete',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    savingExternalSource.value = pool.id
    try {
      const response = await accountImportsApi.deleteCPAPool(pool.id)
      cpaPools.value = response.pools || []
      if (editingCPAPoolId.value === pool.id) resetCPAForm()
      toast.success('CPA connection deleted')
    } catch (error) {
      toast.error(errorMessage(error, 'Failed to delete CPA connection'))
    } finally {
      savingExternalSource.value = ''
    }
  }

  async function testCPAPool(pool: CPAPool) {
    const confirmed = await confirmDialog.ask({
      title: 'Test CPA connection',
      message: `This will access CPA connection ${pool.name || pool.base_url || pool.id} and read its remote file list. Confirm that this external service is allowed.`,
      confirmText: 'Start test',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    testingExternalSource.value = pool.id
    try {
      const response = await accountImportsApi.listCPAPoolFiles(pool.id)
      toast.success(`CPA connection is available; found ${response.files?.length || 0} files`)
    } catch (error) {
      toast.error(errorMessage(error, 'CPA connection test failed'))
    } finally {
      testingExternalSource.value = ''
    }
  }

  function resetSub2APIForm() {
    editingSub2APIId.value = ''
    sub2apiForm.value = createSub2APIForm()
  }

  function openSub2APIModal(server?: Sub2APIServer) {
    if (server) {
      editSub2APIServer(server)
      return
    }
    resetSub2APIForm()
    externalSourceModal.value = 'sub2api'
  }

  function editSub2APIServer(server: Sub2APIServer) {
    editingSub2APIId.value = server.id
    sub2apiForm.value = createSub2APIForm(server)
    externalSourceModal.value = 'sub2api'
  }

  async function loadSub2APIServers() {
    await sub2apiServersQuery.run(
      () => accountImportsApi.listSub2APIServers(),
      {
        apply: (response) => {
          sub2apiServers.value = Array.isArray(response.servers) ? response.servers : []
        },
        onError: (message) => {
          sub2apiServers.value = []
          toast.error(message)
        },
      },
    )
  }

  async function saveSub2APIServer() {
    const payload = buildSub2APIPayload(sub2apiForm.value)
    if (!payload.base_url) {
      toast.warning('Enter a Sub2API URL')
      return
    }
    if (!editingSub2APIId.value && !hasSub2APICredentials(payload)) {
      toast.warning('An email and password or an Admin API key is required to add a Sub2API connection')
      return
    }

    savingExternalSource.value = 'sub2api'
    try {
      const response = editingSub2APIId.value
        ? await accountImportsApi.updateSub2APIServer(editingSub2APIId.value, {
            name: payload.name,
            base_url: payload.base_url,
            email: payload.email,
            group_id: payload.group_id,
            ...(payload.password ? { password: payload.password } : {}),
            ...(payload.api_key ? { api_key: payload.api_key } : {}),
          })
        : await accountImportsApi.createSub2APIServer(payload)
      sub2apiServers.value = response.servers || []
      resetSub2APIForm()
      externalSourceModal.value = ''
      toast.success('Sub2API connection saved')
    } catch (error) {
      toast.error(errorMessage(error, 'Failed to save Sub2API connection'))
    } finally {
      savingExternalSource.value = ''
    }
  }

  async function deleteSub2APIServer(server: Sub2APIServer) {
    const confirmed = await confirmDialog.ask({
      title: 'Delete Sub2API connection',
      message: `Delete ${server.name || server.base_url}? You will no longer be able to import from this Sub2API connection on the Accounts page.`,
      confirmText: 'Delete',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    savingExternalSource.value = server.id
    try {
      const response = await accountImportsApi.deleteSub2APIServer(server.id)
      sub2apiServers.value = response.servers || []
      const nextGroups = { ...sub2apiGroups.value }
      delete nextGroups[server.id]
      sub2apiGroups.value = nextGroups
      if (editingSub2APIId.value === server.id) resetSub2APIForm()
      toast.success('Sub2API connection deleted')
    } catch (error) {
      toast.error(errorMessage(error, 'Failed to delete Sub2API connection'))
    } finally {
      savingExternalSource.value = ''
    }
  }

  async function testSub2APIServer(server: Sub2APIServer) {
    const confirmed = await confirmDialog.ask({
      title: 'Test Sub2API connection',
      message: `This will access Sub2API connection ${server.name || server.base_url || server.id} and read its remote groups. Confirm that this external service is allowed.`,
      confirmText: 'Start test',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    testingExternalSource.value = server.id
    try {
      const response = await accountImportsApi.listSub2APIServerGroups(server.id)
      sub2apiGroups.value = {
        ...sub2apiGroups.value,
        [server.id]: response.groups || [],
      }
      toast.success(`Sub2API connection is available; found ${response.groups?.length || 0} groups`)
    } catch (error) {
      toast.error(errorMessage(error, 'Sub2API connection test failed'))
    } finally {
      testingExternalSource.value = ''
    }
  }

  async function loadAccountGroups() {
    if (accountGroupsLoading.value || accountGroupsLoaded.value) return
    accountGroupsLoading.value = true
    try {
      const response = await accountsApi.listGroups()
      accountGroups.value = Array.isArray(response.groups) ? response.groups : []
      accountGroupsLoaded.value = true
    } catch (error) {
      toast.error(errorMessage(error, 'Failed to load account groups'))
    } finally {
      accountGroupsLoading.value = false
    }
  }

  function openCPAImport(pool: CPAPool) {
    if (remoteImportActive.value) {
      toast.warning('Wait for the current account import to finish')
      return
    }
    remoteImportCPAPoolId.value = pool.id
    remoteImportSub2APIServerId.value = ''
    remoteImportSub2APIGroupId.value = undefined
    remoteImportTargetGroupValue.value = '__preserve__'
    remoteImportBusy.value = false
    remoteImportModal.value = 'cpa'
    void loadAccountGroups()
  }

  function openSub2APIImport(server: Sub2APIServer, groupId?: string) {
    if (remoteImportActive.value) {
      toast.warning('Wait for the current account import to finish')
      return
    }
    remoteImportCPAPoolId.value = ''
    remoteImportSub2APIServerId.value = server.id
    remoteImportSub2APIGroupId.value = groupId
    remoteImportTargetGroupValue.value = '__preserve__'
    remoteImportBusy.value = false
    remoteImportModal.value = 'sub2api'
    void loadAccountGroups()
  }

  function applyRemoteImportStarted(
    mode: 'cpa' | 'sub2api',
    sourceId: string,
    importJob: CPAPool['import_job'],
  ) {
    if (mode === 'cpa') {
      cpaPools.value = cpaPools.value.map((pool) => (
        pool.id === sourceId ? { ...pool, import_job: importJob } : pool
      ))
      return
    }
    sub2apiServers.value = sub2apiServers.value.map((server) => (
      server.id === sourceId ? { ...server, import_job: importJob } : server
    ))
  }

  function closeRemoteImportModal() {
    if (remoteImportBusy.value) return
    handoffRemoteImport()
  }

  function handoffRemoteImport() {
    remoteImportBusy.value = false
    remoteImportModal.value = ''
    remoteImportCPAPoolId.value = ''
    remoteImportSub2APIServerId.value = ''
    remoteImportSub2APIGroupId.value = undefined
  }

  function closeExternalSourceModal() {
    if (savingExternalSource.value === 'cpa' || savingExternalSource.value === 'sub2api') return
    externalSourceModal.value = ''
    resetCPAForm()
    resetSub2APIForm()
  }

  async function loadExternalSources() {
    const generation = ++externalSourcesLoadGeneration
    await Promise.allSettled([
      loadCPAPools(),
      loadSub2APIServers(),
    ])
    if (generation !== externalSourcesLoadGeneration || !options.runtime.canRun.value) return
    externalSourcesLoaded.value = true
  }

  function handleRemoteImportDone() {
    void loadExternalSources()
  }

  function invalidate() {
    externalSourcesLoadGeneration += 1
    cpaPoolsQuery.invalidate()
    sub2apiServersQuery.invalidate()
    externalSourcesLoaded.value = false
  }

  return {
    externalSourcesLoaded,
    cpaLoading,
    sub2apiLoading,
    savingExternalSource,
    testingExternalSource,
    externalSourceModal,
    remoteImportModal,
    remoteImportCPAPoolId,
    remoteImportSub2APIServerId,
    remoteImportSub2APIGroupId,
    remoteImportTargetGroupValue,
    remoteImportBusy,
    remoteImportActive,
    accountGroups,
    accountGroupsLoading,
    cpaPools,
    sub2apiServers,
    sub2apiGroups,
    editingCPAPoolId,
    editingSub2APIId,
    cpaForm,
    sub2apiForm,
    externalSourcesLoading,
    resetCPAForm,
    openCPAModal,
    editCPAPool,
    loadCPAPools,
    saveCPAPool,
    deleteCPAPool,
    testCPAPool,
    resetSub2APIForm,
    openSub2APIModal,
    editSub2APIServer,
    loadSub2APIServers,
    saveSub2APIServer,
    deleteSub2APIServer,
    testSub2APIServer,
    loadAccountGroups,
    openCPAImport,
    openSub2APIImport,
    applyRemoteImportStarted,
    closeRemoteImportModal,
    handoffRemoteImport,
    closeExternalSourceModal,
    loadExternalSources,
    handleRemoteImportDone,
    invalidate,
  }
}
