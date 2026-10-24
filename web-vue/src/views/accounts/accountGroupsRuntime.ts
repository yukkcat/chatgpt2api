import { computed, reactive, ref, type Ref } from 'vue'

import { accountsApi, type AccountGroup } from '@/api/accounts'
import { serializeProxyReference, type ProxyGroup } from '@/api/proxy'
import type { usePageRuntime } from '@/composables/usePageRuntime'
import { usePageQuery } from '@/composables/usePageQuery'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'

type AccountProxyMode = 'global' | 'direct' | 'group' | 'custom'

type AccountGroupForm = {
  id: string
  name: string
  proxy: string
  proxy_group_id: string
  enabled: boolean
  notes: string
}

type AccountGroupsRuntimeOptions = {
  runtime: ReturnType<typeof usePageRuntime>
  requestKey: string
  groupFilter: Ref<string>
  loadData: (options?: { silentErrorToast?: boolean }) => Promise<void>
  setError: (prefix: string, error: unknown, notify?: boolean) => void
}

function createDefaultAccountGroupForm(): AccountGroupForm {
  return {
    id: '',
    name: '',
    proxy: '',
    proxy_group_id: '',
    enabled: true,
    notes: '',
  }
}

function stableGroupNameHash(value: string) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

function createAccountGroupId(name: string) {
  const hash = stableGroupNameHash(name).slice(0, 6)
  const slug = name
    .trim()
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/[-._]+/g, '-')
    .replace(/^-+|-+$/g, '')
  const base = slug ? `${slug}-${hash}` : `group-${hash}`
  return base.slice(0, 64).replace(/-+$/g, '') || `group-${hash}`
}

function normalizeAccountGroupName(name: unknown) {
  return String(name || '').trim().replace(/\s+/g, ' ').toLowerCase()
}

export function useAccountGroupsRuntime(options: AccountGroupsRuntimeOptions) {
  const accountGroups = ref<AccountGroup[]>([])
  const proxyGroups = ref<ProxyGroup[]>([])
  const accountGroupsLoading = ref(false)
  const showAccountGroupsModal = ref(false)
  const accountGroupSaving = ref(false)
  const editingAccountGroupId = ref('')
  const selectedBindGroupId = ref('')
  const accountGroupProxyMode = ref<AccountProxyMode>('global')
  const selectedAccountGroupProxyGroupId = ref('')
  const accountGroupCustomProxyInput = ref('')
  const projectedAccountGroupProxyLabel = ref('')
  const accountGroupForm = reactive(createDefaultAccountGroupForm())
  const toast = useToast()
  const confirmDialog = useConfirmDialog()

  const accountGroupsQuery = usePageQuery({
    runtime: options.runtime,
    key: options.requestKey,
    loading: accountGroupsLoading,
    errorMessage: 'Failed to load account groups',
  })

  const accountGroupOptions = computed(() => [
    { label: 'No group', value: '' },
    ...accountGroups.value.map((group) => ({
      label: `${group.enabled === false ? 'Disabled · ' : ''}${group.name || group.id}`,
      value: group.id,
    })),
  ])

  const accountGroupProxyOptions = computed(() => {
    const rows = proxyGroups.value.map((group) => ({
      label: `${group.enabled === false ? 'Disabled · ' : ''}${group.name || group.id}${Array.isArray(group.nodes) ? ` · ${group.nodes.length} nodes` : ''}`,
      value: group.id,
    }))
    const selectedId = selectedAccountGroupProxyGroupId.value
    if (selectedId && !rows.some((item) => item.value === selectedId)) {
      rows.unshift({ label: `Unknown proxy group · ${selectedId}`, value: selectedId })
    }
    return [
      { label: 'Select a proxy group', value: '' },
      ...rows,
    ]
  })

  const bindAccountGroupOptions = computed(() => [
    { label: 'Select an account group', value: '' },
    ...accountGroupOptions.value.slice(1),
    { label: 'Remove from group', value: '__ungrouped__' },
  ])

  const accountGroupProxyPreview = computed(() => {
    if (projectedAccountGroupProxyLabel.value) return projectedAccountGroupProxyLabel.value
    if (accountGroupProxyMode.value === 'global') return 'Using default proxy'
    if (accountGroupProxyMode.value === 'direct') return 'Direct connection required'
    if (accountGroupProxyMode.value === 'group') {
      const group = proxyGroups.value.find((item) => item.id === selectedAccountGroupProxyGroupId.value)
      return `Proxy group: ${group?.name || selectedAccountGroupProxyGroupId.value || '-'}`
    }
    return accountGroupCustomProxyInput.value || 'Custom proxy'
  })

  function syncAccountGroupProxyControlsFromProjection(group?: AccountGroup) {
    const mode = group?.proxy_mode || 'inherit'
    const legacyGroupId = String(group?.proxy_group_id || '').trim()
    const raw = String(group?.proxy || '').trim() || (legacyGroupId ? serializeProxyReference('group', legacyGroupId) : '')
    accountGroupCustomProxyInput.value = ''
    selectedAccountGroupProxyGroupId.value = ''
    projectedAccountGroupProxyLabel.value = String(group?.proxy_label || '').trim()
    accountGroupProxyMode.value = mode === 'inherit' ? 'global' : mode === 'profile' ? 'custom' : mode
    accountGroupForm.proxy = raw
    accountGroupForm.proxy_group_id = ''
    if (mode === 'profile') {
      accountGroupCustomProxyInput.value = raw
      return
    }
    if (mode === 'group') {
      selectedAccountGroupProxyGroupId.value = legacyGroupId
      accountGroupForm.proxy_group_id = legacyGroupId
      return
    }
    if (mode === 'custom') {
      accountGroupCustomProxyInput.value = raw
    }
  }

  function beginAccountGroupProxyDraft() {
    projectedAccountGroupProxyLabel.value = ''
  }

  function setAccountGroupProxyMode(mode: string) {
    const nextMode = ['global', 'direct', 'group', 'custom'].includes(mode)
      ? mode as AccountProxyMode
      : 'global'
    beginAccountGroupProxyDraft()
    accountGroupProxyMode.value = nextMode
    accountGroupForm.proxy_group_id = ''
    if (nextMode === 'global') {
      accountGroupForm.proxy = serializeProxyReference('global')
    } else if (nextMode === 'direct') {
      accountGroupForm.proxy = serializeProxyReference('direct')
    } else if (nextMode === 'group') {
      accountGroupForm.proxy_group_id = selectedAccountGroupProxyGroupId.value
      accountGroupForm.proxy = serializeProxyReference('group', selectedAccountGroupProxyGroupId.value)
    } else {
      accountGroupForm.proxy = serializeProxyReference('custom', accountGroupCustomProxyInput.value)
    }
  }

  function selectAccountGroupProxyGroup(groupId: string) {
    beginAccountGroupProxyDraft()
    selectedAccountGroupProxyGroupId.value = groupId.trim()
    accountGroupProxyMode.value = 'group'
    accountGroupForm.proxy_group_id = selectedAccountGroupProxyGroupId.value
    accountGroupForm.proxy = serializeProxyReference('group', selectedAccountGroupProxyGroupId.value)
  }

  function setAccountGroupCustomProxyInput(value: string) {
    beginAccountGroupProxyDraft()
    accountGroupCustomProxyInput.value = value.trim()
    accountGroupProxyMode.value = 'custom'
    accountGroupForm.proxy_group_id = ''
    accountGroupForm.proxy = serializeProxyReference('custom', accountGroupCustomProxyInput.value)
  }

  function applyAccountGroupsPayload(response: { groups?: AccountGroup[]; proxy_groups?: ProxyGroup[] }) {
    accountGroups.value = Array.isArray(response.groups)
      ? response.groups.filter((group) => group.id)
      : []
    proxyGroups.value = Array.isArray(response.proxy_groups)
      ? response.proxy_groups.filter((group) => String(group?.id || '').trim())
      : []
    if (
      options.groupFilter.value !== 'all'
      && options.groupFilter.value !== '__ungrouped__'
      && !accountGroups.value.some((group) => group.id === options.groupFilter.value)
    ) {
      options.groupFilter.value = 'all'
    }
    if (selectedBindGroupId.value && !accountGroups.value.some((group) => group.id === selectedBindGroupId.value)) {
      selectedBindGroupId.value = ''
    }
  }

  async function loadAccountGroups(loadOptions?: { silentErrorToast?: boolean }) {
    await accountGroupsQuery.run(
      () => accountsApi.listGroups(),
      {
        apply: applyAccountGroupsPayload,
        onError: (_message, error) => {
          if (!loadOptions?.silentErrorToast) options.setError('Failed to load account groups', error)
        },
        silentError: loadOptions?.silentErrorToast,
      },
    )
  }

  function invalidate() {
    accountGroupsQuery.invalidate()
  }

  function resetAccountGroupForm() {
    Object.assign(accountGroupForm, createDefaultAccountGroupForm())
    editingAccountGroupId.value = ''
    syncAccountGroupProxyControlsFromProjection()
  }

  function openAccountGroupsModal() {
    showAccountGroupsModal.value = true
    resetAccountGroupForm()
    void loadAccountGroups({ silentErrorToast: true })
  }

  function closeAccountGroupsModal() {
    if (accountGroupSaving.value) return
    showAccountGroupsModal.value = false
    resetAccountGroupForm()
  }

  function editAccountGroup(group: AccountGroup) {
    editingAccountGroupId.value = group.id
    Object.assign(accountGroupForm, {
      id: group.id,
      name: group.name || group.id,
      proxy: group.proxy || '',
      proxy_group_id: group.proxy_group_id || '',
      enabled: group.enabled !== false,
      notes: group.notes || '',
    })
    syncAccountGroupProxyControlsFromProjection(group)
  }

  async function saveAccountGroup() {
    if (accountGroupSaving.value) return
    const name = accountGroupForm.name.trim()
    const id = (accountGroupForm.id || editingAccountGroupId.value || createAccountGroupId(name)).trim()
    if (!name) {
      toast.warning('Enter a group name.')
      return
    }
    const normalizedName = normalizeAccountGroupName(name)
    const duplicatedName = accountGroups.value.some((group) => (
      group.id !== id &&
      normalizeAccountGroupName(group.name || group.id) === normalizedName
    ))
    if (duplicatedName) {
      toast.warning('A group with this name already exists. Choose a different name.')
      return
    }
    if (accountGroupProxyMode.value === 'group' && !selectedAccountGroupProxyGroupId.value.trim()) {
      toast.warning('Select a default proxy group for this account group.')
      return
    }
    if (accountGroupProxyMode.value === 'custom' && !accountGroupCustomProxyInput.value.trim()) {
      toast.warning('Enter a custom proxy address for this account group.')
      return
    }

    accountGroupSaving.value = true
    const wasEditing = Boolean(editingAccountGroupId.value)
    try {
      const response = await accountsApi.saveGroup({
        id,
        name,
        proxy: accountGroupForm.proxy.trim(),
        proxy_group_id: accountGroupForm.proxy_group_id.trim(),
        enabled: accountGroupForm.enabled,
        notes: accountGroupForm.notes.trim(),
        create_only: !editingAccountGroupId.value,
      })
      applyAccountGroupsPayload(response)
      selectedBindGroupId.value = response.group?.id || selectedBindGroupId.value
      resetAccountGroupForm()
      toast.success(wasEditing ? 'Account group updated.' : 'Account group created.')
    } catch (error) {
      options.setError(wasEditing ? 'Failed to update account group' : 'Failed to create account group', error)
    } finally {
      accountGroupSaving.value = false
    }
  }

  async function deleteAccountGroup(group: AccountGroup) {
    if (accountGroupSaving.value) return
    const accountCount = Number(group.account_count || 0)
    const confirmed = await confirmDialog.ask({
      title: 'Delete account group',
      message: `Delete account group “${group.name || group.id}”?${accountCount ? ` ${accountCount} accounts will become ungrouped.` : ' No accounts will be deleted.'}`,
      confirmText: 'Delete group',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    accountGroupSaving.value = true
    try {
      const response = await accountsApi.deleteGroup(group.id)
      applyAccountGroupsPayload(response)
      await options.loadData({ silentErrorToast: true })
      if (editingAccountGroupId.value === group.id) resetAccountGroupForm()
      toast.success('Account group deleted.')
    } catch (error) {
      options.setError('Failed to delete account group', error)
    } finally {
      accountGroupSaving.value = false
    }
  }

  return {
    accountGroups,
    proxyGroups,
    accountGroupsLoading,
    showAccountGroupsModal,
    accountGroupSaving,
    editingAccountGroupId,
    selectedBindGroupId,
    accountGroupForm,
    accountGroupOptions,
    accountGroupProxyOptions,
    bindAccountGroupOptions,
    accountGroupProxyMode,
    selectedAccountGroupProxyGroupId,
    accountGroupCustomProxyInput,
    accountGroupProxyPreview,
    applyAccountGroupsPayload,
    loadAccountGroups,
    invalidate,
    resetAccountGroupForm,
    openAccountGroupsModal,
    closeAccountGroupsModal,
    editAccountGroup,
    saveAccountGroup,
    deleteAccountGroup,
    setAccountGroupProxyMode,
    selectAccountGroupProxyGroup,
    setAccountGroupCustomProxyInput,
  }
}
