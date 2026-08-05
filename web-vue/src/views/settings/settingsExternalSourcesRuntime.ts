import { computed, ref } from 'vue'

import { accountImportsApi, type CPAPool, type Sub2APIRemoteGroup, type Sub2APIServer } from '@/api/accountImports'
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
  const remoteImportBusy = ref(false)
  const cpaPools = ref<CPAPool[]>([])
  const sub2apiServers = ref<Sub2APIServer[]>([])
  const sub2apiGroups = ref<Record<string, Sub2APIRemoteGroup[]>>({})
  const sub2apiGroupsLoadingId = ref('')
  const editingCPAPoolId = ref('')
  const editingSub2APIId = ref('')
  const cpaForm = ref(createCPAForm())
  const sub2apiForm = ref(createSub2APIForm())
  const toast = useToast()
  const confirmDialog = useConfirmDialog()
  const externalSourcesLoading = computed(() => cpaLoading.value || sub2apiLoading.value)

  const cpaPoolsQuery = usePageQuery({
    runtime: options.runtime,
    key: options.cpaRequestKey,
    loading: cpaLoading,
    errorMessage: '加载 CPA 连接失败',
  })
  const sub2apiServersQuery = usePageQuery({
    runtime: options.runtime,
    key: options.sub2apiRequestKey,
    loading: sub2apiLoading,
    errorMessage: '加载 Sub2API 连接失败',
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
      toast.warning('请输入 CPA 地址')
      return
    }
    if (!editingCPAPoolId.value && !payload.secret_key) {
      toast.warning('新增 CPA 连接需要管理密钥')
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
      toast.success('CPA 连接已保存')
    } catch (error) {
      toast.error(errorMessage(error, '保存 CPA 连接失败'))
    } finally {
      savingExternalSource.value = ''
    }
  }

  async function deleteCPAPool(pool: CPAPool) {
    const confirmed = await confirmDialog.ask({
      title: '删除 CPA 连接',
      message: `确定删除 ${pool.name || pool.base_url}？账号页将不能再从这个 CPA 连接导入。`,
      confirmText: '删除',
      cancelText: '取消',
    })
    if (!confirmed) return

    savingExternalSource.value = pool.id
    try {
      const response = await accountImportsApi.deleteCPAPool(pool.id)
      cpaPools.value = response.pools || []
      if (editingCPAPoolId.value === pool.id) resetCPAForm()
      toast.success('CPA 连接已删除')
    } catch (error) {
      toast.error(errorMessage(error, '删除 CPA 连接失败'))
    } finally {
      savingExternalSource.value = ''
    }
  }

  async function testCPAPool(pool: CPAPool) {
    const confirmed = await confirmDialog.ask({
      title: '测试 CPA 连接',
      message: `即将访问 CPA 连接 ${pool.name || pool.base_url || pool.id} 并读取远程文件列表。请确认当前允许连接该外部服务。`,
      confirmText: '开始测试',
      cancelText: '取消',
    })
    if (!confirmed) return

    testingExternalSource.value = pool.id
    try {
      const response = await accountImportsApi.listCPAPoolFiles(pool.id)
      toast.success(`CPA 连接可用，读取到 ${response.files?.length || 0} 个文件`)
    } catch (error) {
      toast.error(errorMessage(error, 'CPA 连接测试失败'))
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
      toast.warning('请输入 Sub2API 地址')
      return
    }
    if (!editingSub2APIId.value && !hasSub2APICredentials(payload)) {
      toast.warning('新增 Sub2API 连接需要邮箱密码或 Admin API Key')
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
      toast.success('Sub2API 连接已保存')
    } catch (error) {
      toast.error(errorMessage(error, '保存 Sub2API 连接失败'))
    } finally {
      savingExternalSource.value = ''
    }
  }

  async function deleteSub2APIServer(server: Sub2APIServer) {
    const confirmed = await confirmDialog.ask({
      title: '删除 Sub2API 连接',
      message: `确定删除 ${server.name || server.base_url}？账号页将不能再从这个 Sub2API 连接导入。`,
      confirmText: '删除',
      cancelText: '取消',
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
      toast.success('Sub2API 连接已删除')
    } catch (error) {
      toast.error(errorMessage(error, '删除 Sub2API 连接失败'))
    } finally {
      savingExternalSource.value = ''
    }
  }

  async function loadSub2APIGroups(server: Sub2APIServer) {
    const confirmed = await confirmDialog.ask({
      title: '加载 Sub2API 分组',
      message: `即将访问 Sub2API 连接 ${server.name || server.base_url || server.id} 并读取远程分组列表。请确认当前允许连接该外部服务。`,
      confirmText: '确认加载',
      cancelText: '取消',
    })
    if (!confirmed) return

    sub2apiGroupsLoadingId.value = server.id
    try {
      const response = await accountImportsApi.listSub2APIServerGroups(server.id)
      sub2apiGroups.value = {
        ...sub2apiGroups.value,
        [server.id]: Array.isArray(response.groups) ? response.groups : [],
      }
      if (!response.groups?.length) toast.info('这个 Sub2API 连接没有返回分组')
    } catch (error) {
      toast.error(errorMessage(error, '读取 Sub2API 分组失败'))
    } finally {
      sub2apiGroupsLoadingId.value = ''
    }
  }

  async function testSub2APIServer(server: Sub2APIServer) {
    const confirmed = await confirmDialog.ask({
      title: '测试 Sub2API 连接',
      message: `即将访问 Sub2API 连接 ${server.name || server.base_url || server.id} 并读取远程分组列表。请确认当前允许连接该外部服务。`,
      confirmText: '开始测试',
      cancelText: '取消',
    })
    if (!confirmed) return

    testingExternalSource.value = server.id
    try {
      const response = await accountImportsApi.listSub2APIServerGroups(server.id)
      sub2apiGroups.value = {
        ...sub2apiGroups.value,
        [server.id]: response.groups || [],
      }
      toast.success(`Sub2API 连接可用，读取到 ${response.groups?.length || 0} 个分组`)
    } catch (error) {
      toast.error(errorMessage(error, 'Sub2API 连接测试失败'))
    } finally {
      testingExternalSource.value = ''
    }
  }

  function openCPAImport(pool: CPAPool) {
    remoteImportCPAPoolId.value = pool.id
    remoteImportSub2APIServerId.value = ''
    remoteImportSub2APIGroupId.value = undefined
    remoteImportBusy.value = false
    remoteImportModal.value = 'cpa'
  }

  function openSub2APIImport(server: Sub2APIServer, groupId?: string) {
    remoteImportCPAPoolId.value = ''
    remoteImportSub2APIServerId.value = server.id
    remoteImportSub2APIGroupId.value = groupId
    remoteImportBusy.value = false
    remoteImportModal.value = 'sub2api'
  }

  function closeRemoteImportModal() {
    if (remoteImportBusy.value) return
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
    remoteImportBusy,
    cpaPools,
    sub2apiServers,
    sub2apiGroups,
    sub2apiGroupsLoadingId,
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
    loadSub2APIGroups,
    testSub2APIServer,
    openCPAImport,
    openSub2APIImport,
    closeRemoteImportModal,
    closeExternalSourceModal,
    loadExternalSources,
    handleRemoteImportDone,
    invalidate,
  }
}
