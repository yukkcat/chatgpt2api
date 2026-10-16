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
  { label: 'Use default proxy', value: 'global' },
  { label: 'Always connect directly', value: 'direct' },
  { label: 'Proxy group (multiple nodes)', value: 'group' },
  { label: 'Custom proxy', value: 'custom' },
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
      label: `${group.enabled === false ? 'Disabled · ' : ''}${group.name || group.id}${Array.isArray(group.nodes) ? ` · ${group.nodes.length} nodes` : ''}`,
      value: group.id,
    }))
    const selectedId = selectedProxyGroupId.value
    if (selectedId && !rows.some((item) => item.value === selectedId)) {
      rows.unshift({ label: `Unknown proxy group · ${selectedId}`, value: selectedId })
    }
    return [
      { label: 'Select a proxy group', value: '' },
      ...rows,
    ]
  })

  const accountProxyPreview = computed(() => {
    if (projectedProxyLabel.value) return projectedProxyLabel.value
    if (proxyMode.value === 'global') return 'Using default proxy'
    if (proxyMode.value === 'direct') return 'Direct connection required'
    if (proxyMode.value === 'group') {
      const group = options.proxyGroups.value.find((item) => item.id === selectedProxyGroupId.value)
      return `Proxy group: ${group?.name || selectedProxyGroupId.value || '-'}`
    }
    return customProxyInput.value || 'Custom proxy'
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
      toast.info('This account is set to connect directly. No proxy test is needed.')
      return
    }

    if (proxyMode.value === 'group' && !selectedProxyGroupId.value) {
      toast.warning('Select a proxy group first.')
      return
    }

    if (proxyMode.value === 'custom' && !customProxyInput.value.trim()) {
      toast.warning('Enter a custom proxy address first.')
      return
    }

    const confirmed = await confirmDialog.ask({
      title: 'Confirm account proxy test',
      message: 'An external network test request will be sent through this account’s proxy. Confirm that you are allowed to test this connection.',
      confirmText: 'Start test',
      cancelText: 'Cancel',
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
        toast.success(`Proxy is available: ${result.latency_ms} ms, HTTP ${result.status}`)
      } else {
        toast.error(`Proxy is unavailable: ${result.error || 'Unknown error'}`)
      }
    } catch (error) {
      options.setError('Proxy test failed', error)
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
