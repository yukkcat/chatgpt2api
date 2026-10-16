import { computed, ref, type Ref } from 'vue'

import {
  proxyApi,
  type ProxyEffectiveReference,
  type ProxyGroup,
  type ProxyReference,
  type ProxyTestResult,
  type ProxyView,
} from '@/api/proxy'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { usePageQuery } from '@/composables/usePageQuery'
import type { usePageRuntime } from '@/composables/usePageRuntime'
import { useToast } from '@/composables/useToast'
import { errorMessage, prefixedErrorMessage } from '@/lib/errorMessage'
import {
  proxyGroupOptions as buildProxyGroupOptions,
  proxyTestToastType,
  toDefaultProxyMode,
  toFallbackProxyMode,
  type DefaultProxyMode,
  type FallbackProxyMode,
} from '@/views/proxy/proxyView'

type ProxyDefaultRuntimeOptions = {
  runtime: ReturnType<typeof usePageRuntime>
  requestKey: string
  groups: Ref<ProxyGroup[]>
  testingKey: Ref<string>
  updateGroups: (groups: ProxyGroup[]) => void
}

export const DEFAULT_TEST_KEY = '__default__'

const EMPTY_EFFECTIVE_DEFAULT: ProxyEffectiveReference = {
  source: 'direct',
  label: 'Direct',
  configured: false,
  available: true,
  has_proxy: false,
  group_id: '',
}

function firstSelectValue(value: string | string[]) {
  return Array.isArray(value) ? value[0] : value
}

function referenceKey(reference: ProxyReference | null) {
  if (!reference) return 'off'
  return `${reference.mode}|${reference.group_id}|${reference.url}`
}

export function useProxyDefaultRuntime(options: ProxyDefaultRuntimeOptions) {
  const toast = useToast()
  const confirmDialog = useConfirmDialog()
  const loading = ref(false)
  const savingDefaultProxy = ref(false)
  const defaultProxyMode = ref<DefaultProxyMode>('direct')
  const selectedDefaultProxyGroupId = ref('')
  const defaultCustomProxyInput = ref('')
  const fallbackProxyMode = ref<FallbackProxyMode>('off')
  const selectedFallbackProxyGroupId = ref('')
  const fallbackCustomProxyInput = ref('')
  const currentView = ref<ProxyView | null>(null)
  const defaultTestResult = ref<ProxyTestResult | null>(null)

  const proxyDataQuery = usePageQuery({
    runtime: options.runtime,
    key: options.requestKey,
    loading,
    errorMessage: 'Failed to load proxy settings',
  })

  const defaultProxyGroupOptions = computed(() => (
    buildProxyGroupOptions(options.groups.value, selectedDefaultProxyGroupId.value)
  ))

  const fallbackProxyGroupOptions = computed(() => (
    buildProxyGroupOptions(options.groups.value, selectedFallbackProxyGroupId.value)
  ))

  const effectiveDefault = computed(() => (
    currentView.value?.effective_default || EMPTY_EFFECTIVE_DEFAULT
  ))

  const canTestDefaultProxy = computed(() => {
    if (defaultProxyMode.value === 'group') return Boolean(selectedDefaultProxyGroupId.value)
    if (defaultProxyMode.value === 'custom') return Boolean(defaultCustomProxyInput.value.trim())
    return false
  })

  const isDefaultProxyDirty = computed(() => {
    const view = currentView.value
    if (!view) return false
    return (
      referenceKey(defaultProxyReference()) !== referenceKey(view.default_reference)
      || referenceKey(fallbackProxyReference()) !== referenceKey(view.fallback_reference)
    )
  })

  function defaultProxyReference(): ProxyReference {
    if (defaultProxyMode.value === 'direct') {
      return { mode: 'direct', group_id: '', url: '' }
    }
    if (defaultProxyMode.value === 'group') {
      return { mode: 'group', group_id: selectedDefaultProxyGroupId.value, url: '' }
    }
    return { mode: 'custom', group_id: '', url: defaultCustomProxyInput.value.trim() }
  }

  function fallbackProxyReference(): ProxyReference | null {
    if (fallbackProxyMode.value === 'off') return null
    if (fallbackProxyMode.value === 'direct') {
      return { mode: 'direct', group_id: '', url: '' }
    }
    if (fallbackProxyMode.value === 'group') {
      return { mode: 'group', group_id: selectedFallbackProxyGroupId.value, url: '' }
    }
    return { mode: 'custom', group_id: '', url: fallbackCustomProxyInput.value.trim() }
  }

  function syncDefaultProxyControls(reference: ProxyReference) {
    defaultProxyMode.value = reference.mode
    selectedDefaultProxyGroupId.value = reference.mode === 'group' ? reference.group_id : ''
    defaultCustomProxyInput.value = reference.mode === 'custom' ? reference.url : ''
    defaultTestResult.value = null
  }

  function syncFallbackProxyControls(reference: ProxyReference | null) {
    fallbackProxyMode.value = reference?.mode || 'off'
    selectedFallbackProxyGroupId.value = reference?.mode === 'group' ? reference.group_id : ''
    fallbackCustomProxyInput.value = reference?.mode === 'custom' ? reference.url : ''
  }

  function setDefaultProxyMode(mode: string | string[]) {
    defaultProxyMode.value = toDefaultProxyMode(mode)
    defaultTestResult.value = null
  }

  function setFallbackProxyMode(mode: string | string[]) {
    fallbackProxyMode.value = toFallbackProxyMode(mode)
  }

  function selectDefaultProxyGroup(groupId: string | string[]) {
    selectedDefaultProxyGroupId.value = String(firstSelectValue(groupId) || '').trim()
    defaultProxyMode.value = 'group'
    defaultTestResult.value = null
  }

  function selectFallbackProxyGroup(groupId: string | string[]) {
    selectedFallbackProxyGroupId.value = String(firstSelectValue(groupId) || '').trim()
    fallbackProxyMode.value = 'group'
  }

  function setDefaultCustomProxyInput(value: string) {
    defaultCustomProxyInput.value = String(value || '').trim()
    defaultProxyMode.value = 'custom'
    defaultTestResult.value = null
  }

  function setFallbackCustomProxyInput(value: string) {
    fallbackCustomProxyInput.value = String(value || '').trim()
    fallbackProxyMode.value = 'custom'
  }

  function validateProxySelection(
    mode: DefaultProxyMode | FallbackProxyMode,
    groupId: string,
    customInput: Ref<string>,
    messages: {
      missingGroup: string
      missingCustom: string
    },
  ) {
    if (mode === 'group' && !groupId) {
      toast.warning(messages.missingGroup)
      return false
    }
    if (mode !== 'custom') return true

    const value = customInput.value.trim()
    if (!value) {
      toast.warning(messages.missingCustom)
      return false
    }
    return true
  }

  async function loadData() {
    await proxyDataQuery.run(
      () => proxyApi.getView(),
      {
        apply: (view) => {
          currentView.value = view
          options.updateGroups(view.groups)
          syncDefaultProxyControls(view.default_reference)
          syncFallbackProxyControls(view.fallback_reference)
        },
        onError: (message) => {
          toast.error(message)
        },
      },
    )
  }

  async function saveDefaultProxy() {
    if (!currentView.value) {
      toast.warning('Settings have not finished loading')
      return
    }
    if (!validateProxySelection(
      defaultProxyMode.value,
      selectedDefaultProxyGroupId.value,
      defaultCustomProxyInput,
      {
        missingGroup: 'Select a default egress proxy group',
        missingCustom: 'Enter a custom proxy URL',
      },
    )) return
    if (!validateProxySelection(
      fallbackProxyMode.value,
      selectedFallbackProxyGroupId.value,
      fallbackCustomProxyInput,
      {
        missingGroup: 'Select a fallback egress proxy group',
        missingCustom: 'Enter a fallback proxy URL',
      },
    )) return
    const confirmed = await confirmDialog.ask({
      title: 'Confirm egress settings',
      message: 'This will save the default and fallback egress settings. Fallback egress retries image requests once after an early connection failure. Continue?',
      confirmText: 'Save',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    savingDefaultProxy.value = true
    try {
      const response = await proxyApi.saveDefaults({
        default_reference: defaultProxyReference(),
        fallback_reference: fallbackProxyReference(),
      })
      currentView.value = {
        ...currentView.value,
        ...response,
      }
      syncDefaultProxyControls(response.default_reference)
      syncFallbackProxyControls(response.fallback_reference)
      toast.success('Egress settings saved')
    } catch (error) {
      toast.error(prefixedErrorMessage('Failed to save egress settings', error))
    } finally {
      savingDefaultProxy.value = false
    }
  }

  function setDefaultProxyDirect() {
    defaultProxyMode.value = 'direct'
    selectedDefaultProxyGroupId.value = ''
    defaultCustomProxyInput.value = ''
    defaultTestResult.value = null
  }

  async function testDefaultProxy() {
    if (defaultProxyMode.value === 'direct') {
      toast.info('Egress testing is not needed in direct mode')
      return
    }
    if (!validateProxySelection(
      defaultProxyMode.value,
      selectedDefaultProxyGroupId.value,
      defaultCustomProxyInput,
      {
        missingGroup: 'Select a default egress proxy group',
        missingCustom: 'Enter a custom proxy URL',
      },
    )) return
    const confirmed = await confirmDialog.ask({
      title: 'Confirm default egress test',
      message: 'This will send an external network test request through the current default egress. Confirm that testing this connection is allowed.',
      confirmText: 'Start test',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    options.testingKey.value = DEFAULT_TEST_KEY
    try {
      if (defaultProxyMode.value === 'group') {
        const response = await proxyApi.testGroup({ id: selectedDefaultProxyGroupId.value })
        const firstResult = response.result || response.results[0]?.result
        defaultTestResult.value = {
          ok: response.summary.status === 'success',
          status: firstResult?.status || 0,
          latency_ms: response.summary.max_latency_ms,
          error: response.summary.status === 'success' ? null : response.summary.message,
        }
        toast[proxyTestToastType(response.summary.tone)](response.summary.message)
        return
      }
      const response = await proxyApi.test(defaultCustomProxyInput.value.trim())
      defaultTestResult.value = response.result
      if (response.result.ok) toast.success(`Default egress available, latency ${response.result.latency_ms}ms`)
      else toast.warning(response.result.error || 'Default egress test failed')
    } catch (error) {
      const message = errorMessage(error, 'Default egress test failed')
      defaultTestResult.value = {
        ok: false,
        status: 0,
        latency_ms: 0,
        error: message,
      }
      toast.error(message)
    } finally {
      options.testingKey.value = ''
    }
  }

  function invalidate() {
    proxyDataQuery.invalidate()
  }

  return {
    loading,
    savingDefaultProxy,
    defaultProxyMode,
    selectedDefaultProxyGroupId,
    defaultCustomProxyInput,
    fallbackProxyMode,
    selectedFallbackProxyGroupId,
    fallbackCustomProxyInput,
    defaultTestResult,
    defaultProxyGroupOptions,
    fallbackProxyGroupOptions,
    effectiveDefault,
    canTestDefaultProxy,
    isDefaultProxyDirty,
    setDefaultProxyMode,
    setFallbackProxyMode,
    selectDefaultProxyGroup,
    selectFallbackProxyGroup,
    setDefaultCustomProxyInput,
    setFallbackCustomProxyInput,
    loadData,
    saveDefaultProxy,
    setDefaultProxyDirect,
    testDefaultProxy,
    invalidate,
  }
}
