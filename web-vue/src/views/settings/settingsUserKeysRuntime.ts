import { onDeactivated, onScopeDispose, ref } from 'vue'

import { userKeysApi, type UserKey } from '@/api/userKeys'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import type { usePageRuntime } from '@/composables/usePageRuntime'
import { usePageQuery } from '@/composables/usePageQuery'
import { useToast } from '@/composables/useToast'
import { errorMessage } from '@/lib/errorMessage'

export type UserKeyForm = {
  name: string
  key: string
}

type SettingsUserKeysRuntimeOptions = {
  runtime: ReturnType<typeof usePageRuntime>
  requestKey: string
}

function createUserKeyForm(): UserKeyForm {
  return { name: '', key: '' }
}

export function useSettingsUserKeysRuntime(options: SettingsUserKeysRuntimeOptions) {
  const userKeys = ref<UserKey[]>([])
  const userKeysLoaded = ref(false)
  const userKeysLoading = ref(false)
  const userKeyBusy = ref('')
  const userKeyModal = ref<'create' | 'edit' | ''>('')
  const editingUserKey = ref<UserKey | null>(null)
  const newUserKey = ref('')
  const userKeyForm = ref<UserKeyForm>(createUserKeyForm())
  const toast = useToast()
  const confirmDialog = useConfirmDialog()
  let rawKeyClearTimer: ReturnType<typeof window.setTimeout> | null = null

  function clearNewUserKey() {
    if (rawKeyClearTimer !== null) {
      window.clearTimeout(rawKeyClearTimer)
      rawKeyClearTimer = null
    }
    newUserKey.value = ''
  }

  function revealNewUserKey(rawKey: string) {
    clearNewUserKey()
    newUserKey.value = rawKey
    if (!rawKey) return
    rawKeyClearTimer = window.setTimeout(clearNewUserKey, 120000)
  }

  function upsertUserKey(item: UserKey) {
    const index = userKeys.value.findIndex(candidate => candidate.id === item.id)
    if (index < 0) {
      userKeys.value = [...userKeys.value, item]
      return
    }
    userKeys.value = userKeys.value.map(candidate => candidate.id === item.id ? item : candidate)
  }

  onDeactivated(clearNewUserKey)
  onScopeDispose(clearNewUserKey)

  const userKeysQuery = usePageQuery({
    runtime: options.runtime,
    key: options.requestKey,
    loading: userKeysLoading,
    errorMessage: 'Failed to load user keys',
  })

  async function copyUserKey(value: string) {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      if (value === newUserKey.value) clearNewUserKey()
      toast.success('Key copied.')
    } catch {
      toast.error('Copy failed. Copy the key manually.')
    }
  }

  function resetUserKeyForm() {
    userKeyForm.value = createUserKeyForm()
    editingUserKey.value = null
  }

  function openUserKeyCreateModal() {
    clearNewUserKey()
    resetUserKeyForm()
    userKeyModal.value = 'create'
  }

  function openUserKeyEditModal(item: UserKey) {
    editingUserKey.value = item
    userKeyForm.value = {
      name: item.name || '',
      key: '',
    }
    userKeyModal.value = 'edit'
  }

  function closeUserKeyModal() {
    if (userKeyBusy.value === 'create') return
    if (editingUserKey.value && userKeyBusy.value === editingUserKey.value.id) return
    userKeyModal.value = ''
    resetUserKeyForm()
  }

  async function loadUserKeys() {
    await userKeysQuery.run(
      () => userKeysApi.list(),
      {
        apply: (response) => {
          userKeys.value = Array.isArray(response.items) ? response.items : []
          userKeysLoaded.value = true
        },
        onError: (message) => {
          userKeys.value = []
          toast.error(message)
        },
      },
    )
  }

  async function createUserKey() {
    userKeyBusy.value = 'create'
    try {
      const response = await userKeysApi.create(userKeyForm.value.name.trim())
      upsertUserKey(response.item)
      revealNewUserKey(response.raw_key)
      toast.success('User key created.')
      userKeyModal.value = ''
      resetUserKeyForm()
    } catch (error) {
      toast.error(errorMessage(error, 'Failed to create user key'))
    } finally {
      userKeyBusy.value = ''
    }
  }

  async function updateUserKey() {
    const item = editingUserKey.value
    if (!item) return
    const nextName = userKeyForm.value.name.trim()
    const nextKey = userKeyForm.value.key.trim()
    const updates: { name?: string; key?: string } = {}
    if (nextName !== item.name) updates.name = nextName
    if (nextKey) updates.key = nextKey
    if (!Object.keys(updates).length) {
      closeUserKeyModal()
      return
    }

    userKeyBusy.value = item.id
    try {
      const response = await userKeysApi.update(item.id, updates)
      upsertUserKey(response.item)
      toast.success(nextKey ? 'User key updated.' : 'User name updated.')
      userKeyModal.value = ''
      resetUserKeyForm()
    } catch (error) {
      toast.error(errorMessage(error, 'Failed to update user key'))
    } finally {
      userKeyBusy.value = ''
    }
  }

  async function toggleUserKey(item: UserKey) {
    userKeyBusy.value = item.id
    try {
      const response = await userKeysApi.update(item.id, { enabled: !item.enabled })
      upsertUserKey(response.item)
      toast.success(item.enabled ? 'User key disabled.' : 'User key enabled.')
    } catch (error) {
      toast.error(errorMessage(error, 'Failed to update user key'))
    } finally {
      userKeyBusy.value = ''
    }
  }

  async function deleteUserKey(item: UserKey) {
    const confirmed = await confirmDialog.ask({
      title: 'Delete user key',
      message: `Delete user key “${item.name || item.id}”? This key will no longer be able to call the API.`,
      confirmText: 'Delete key',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    userKeyBusy.value = item.id
    try {
      const response = await userKeysApi.delete(item.id)
      userKeys.value = userKeys.value.filter(candidate => candidate.id !== response.deleted_id)
      if (editingUserKey.value?.id === item.id) {
        userKeyModal.value = ''
        resetUserKeyForm()
      }
      toast.success('User key deleted.')
    } catch (error) {
      toast.error(errorMessage(error, 'Failed to delete user key'))
    } finally {
      userKeyBusy.value = ''
    }
  }

  function invalidate() {
    clearNewUserKey()
    userKeysQuery.invalidate()
    userKeysLoaded.value = false
  }

  return {
    userKeys,
    userKeysLoaded,
    userKeysLoading,
    userKeyBusy,
    userKeyModal,
    editingUserKey,
    newUserKey,
    userKeyForm,
    copyUserKey,
    resetUserKeyForm,
    openUserKeyCreateModal,
    openUserKeyEditModal,
    closeUserKeyModal,
    loadUserKeys,
    createUserKey,
    updateUserKey,
    toggleUserKey,
    deleteUserKey,
    invalidate,
  }
}
