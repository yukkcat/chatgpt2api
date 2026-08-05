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
    errorMessage: '加载用户密钥失败',
  })

  async function copyUserKey(value: string) {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      if (value === newUserKey.value) clearNewUserKey()
      toast.success('已复制密钥')
    } catch {
      toast.error('复制失败，请手动复制')
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
      toast.success('用户密钥已创建')
      userKeyModal.value = ''
      resetUserKeyForm()
    } catch (error) {
      toast.error(errorMessage(error, '创建用户密钥失败'))
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
      toast.success(nextKey ? '用户密钥已更新' : '用户名称已更新')
      userKeyModal.value = ''
      resetUserKeyForm()
    } catch (error) {
      toast.error(errorMessage(error, '更新用户密钥失败'))
    } finally {
      userKeyBusy.value = ''
    }
  }

  async function toggleUserKey(item: UserKey) {
    userKeyBusy.value = item.id
    try {
      const response = await userKeysApi.update(item.id, { enabled: !item.enabled })
      upsertUserKey(response.item)
      toast.success(item.enabled ? '用户密钥已禁用' : '用户密钥已启用')
    } catch (error) {
      toast.error(errorMessage(error, '更新用户密钥失败'))
    } finally {
      userKeyBusy.value = ''
    }
  }

  async function deleteUserKey(item: UserKey) {
    const confirmed = await confirmDialog.ask({
      title: '删除用户密钥',
      message: `确定删除用户密钥「${item.name || item.id}」吗？删除后这条密钥将无法继续调用接口。`,
      confirmText: '删除',
      cancelText: '取消',
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
      toast.success('用户密钥已删除')
    } catch (error) {
      toast.error(errorMessage(error, '删除用户密钥失败'))
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
