import { computed, ref, type Ref } from 'vue'

import type { AccountProxyProjection } from '@/api/accounts'
import { proxyApi, serializeProxyReference, type ProxyGroup, type ProxyTestResult } from '@/api/proxy'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import { proxyTestToastType } from '@/views/proxy/proxyView'

type AccountProxyMode = 'global' | 'direct' | 'group' | 'custom'

type AccountProxyRuntimeOptions = {
  proxyGroups: Ref<ProxyGroup[]>
  proxyValue: Ref<string>
  setError: (prefix: string, error: unknown, notify?: boolean) => void
}

const accountProxyModeOptions = [
  { label: '使用默认代理', value: 'global' },
  { label: '强制直连', value: 'direct' },
  { label: '代理组（多节点）', value: 'group' },
  { label: '自定义代理', value: 'custom' },
] as const

export function useAccountProxyRuntime(options: AccountProxyRuntimeOptions) {
  const proxyTesting = ref(false)
  const proxyMode = ref<AccountProxyMode>('global')
  const selectedProxyGroupId = ref('')
  const customProxyInput = ref('')
  const projectedProxyLabel = ref('')
  const toast = useToast()
  const confirmDialog = useConfirmDialog()

  const proxyGroupOptions = computed(() => {
    const rows = options.proxyGroups.value.map((group) => ({
      label: `${group.enabled === false ? '停用 · ' : ''}${group.name || group.id}${Array.isArray(group.nodes) ? ` · ${group.nodes.length} 个节点` : ''}`,
      value: group.id,
    }))
    const selectedId = selectedProxyGroupId.value
    if (selectedId && !rows.some((item) => item.value === selectedId)) {
      rows.unshift({ label: `未知代理组 · ${selectedId}`, value: selectedId })
    }
    return [
      { label: '选择代理组', value: '' },
      ...rows,
    ]
  })

  const accountProxyPreview = computed(() => {
    if (projectedProxyLabel.value) return projectedProxyLabel.value
    if (proxyMode.value === 'global') return '使用默认出口'
    if (proxyMode.value === 'direct') return '强制直连'
    if (proxyMode.value === 'group') {
      const group = options.proxyGroups.value.find((item) => item.id === selectedProxyGroupId.value)
      return `代理组：${group?.name || selectedProxyGroupId.value || '-'}`
    }
    return customProxyInput.value || '自定义代理'
  })

  function syncProxyControlsFromProjection(projection?: AccountProxyProjection) {
    const mode = projection?.proxy_mode || 'inherit'
    const raw = String(projection?.proxy || '').trim()
    // Detail responses already populate the editable draft with the real proxy
    // value. Keep that value when the list projection only contains a safe
    // placeholder for custom proxy credentials.
    if (!String(options.proxyValue.value || '').trim() && raw) {
      options.proxyValue.value = raw
    }
    customProxyInput.value = ''
    selectedProxyGroupId.value = ''
    projectedProxyLabel.value = String(projection?.proxy_label || '').trim()
    proxyMode.value = mode === 'inherit' ? 'global' : mode
    if (mode === 'group') {
      selectedProxyGroupId.value = String(projection?.proxy_group_id || '').trim()
      return
    }
    if (mode === 'custom') {
      customProxyInput.value = raw
    }
  }

  function beginProxyDraft() {
    projectedProxyLabel.value = ''
  }

  function setProxyMode(mode: string) {
    const nextMode = ['global', 'direct', 'group', 'custom'].includes(mode)
      ? mode as AccountProxyMode
      : 'global'
    beginProxyDraft()
    proxyMode.value = nextMode
    if (nextMode === 'global') {
      options.proxyValue.value = serializeProxyReference('global')
    } else if (nextMode === 'direct') {
      options.proxyValue.value = serializeProxyReference('direct')
    } else if (nextMode === 'group') {
      options.proxyValue.value = serializeProxyReference('group', selectedProxyGroupId.value)
    } else {
      options.proxyValue.value = serializeProxyReference('custom', customProxyInput.value)
    }
  }

  function selectProxyGroup(groupId: string) {
    beginProxyDraft()
    selectedProxyGroupId.value = groupId.trim()
    proxyMode.value = 'group'
    options.proxyValue.value = serializeProxyReference('group', selectedProxyGroupId.value)
  }

  function setCustomProxyInput(value: string) {
    beginProxyDraft()
    customProxyInput.value = value.trim()
    proxyMode.value = 'custom'
    options.proxyValue.value = serializeProxyReference('custom', customProxyInput.value)
  }

  async function testAccountProxy() {
    if (proxyTesting.value) return

    if (proxyMode.value === 'direct') {
      toast.info('当前账号强制直连，不需要测试代理')
      return
    }

    if (proxyMode.value === 'group' && !selectedProxyGroupId.value) {
      toast.warning('请先选择代理组')
      return
    }

    if (proxyMode.value === 'custom' && !customProxyInput.value.trim()) {
      toast.warning('请先填写自定义代理地址')
      return
    }

    const confirmed = await confirmDialog.ask({
      title: '确认测试账号代理',
      message: '即将通过当前账号代理配置发起外部网络测试请求。请确认当前允许测试该代理连接。',
      confirmText: '开始测试',
      cancelText: '取消',
    })
    if (!confirmed) return

    proxyTesting.value = true
    try {
      if (proxyMode.value === 'group') {
        const response = await proxyApi.testGroup({ id: selectedProxyGroupId.value })
        toast[proxyTestToastType(response.summary.tone)](response.summary.message)
        return
      }
      const response: { result: ProxyTestResult } = await proxyApi.test(
        proxyMode.value === 'custom' ? customProxyInput.value.trim() : '',
      )
      const result = response.result
      if (result.ok) {
        toast.success(`代理可用：${result.latency_ms} ms，HTTP ${result.status}`)
      } else {
        toast.error(`代理不可用：${result.error || '未知错误'}`)
      }
    } catch (error) {
      options.setError('测试代理失败', error)
    } finally {
      proxyTesting.value = false
    }
  }

  return {
    proxyTesting,
    proxyMode,
    accountProxyModeOptions,
    proxyGroupOptions,
    selectedProxyGroupId,
    customProxyInput,
    accountProxyPreview,
    syncProxyControlsFromProjection,
    setProxyMode,
    selectProxyGroup,
    setCustomProxyInput,
    testAccountProxy,
  }
}
