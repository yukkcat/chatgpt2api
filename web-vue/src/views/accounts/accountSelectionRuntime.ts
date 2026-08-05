import { computed, ref, type ComputedRef, type Ref } from 'vue'

import type {
  Account,
  AccountSelectionPreview,
  AccountSelectionScope,
  AccountStatusCategory,
} from '@/api/accounts'

type AccountSelectionRuntimeOptions = {
  accounts: Ref<Account[]>
  pagedAccounts: ComputedRef<Account[]>
  total: Ref<number>
  allTotal: Ref<number>
  keyword: Ref<string>
  status: Ref<'all' | AccountStatusCategory>
  groupId: Ref<string>
}

type FilterSnapshot = Pick<AccountSelectionScope, 'keyword' | 'status' | 'group_id'>

export function useAccountSelectionRuntime(options: AccountSelectionRuntimeOptions) {
  const selectionMode = ref<'explicit' | 'filter' | 'all'>('explicit')
  const selectedIds = ref<string[]>([])
  const excludedIds = ref<string[]>([])
  const filterSnapshot = ref<FilterSnapshot>({ keyword: '', status: 'all', group_id: 'all' })
  const selectionRevision = ref(0)
  const authoritativeSelectedCount = ref<number | null>(null)

  const selectedSet = computed(() => new Set(selectedIds.value))
  const excludedSet = computed(() => new Set(excludedIds.value))
  const scopedSelectionActive = computed(() => selectionMode.value !== 'explicit')
  const selectedCount = computed(() => (
    scopedSelectionActive.value
      ? authoritativeSelectedCount.value ?? Math.max(
        0,
        (selectionMode.value === 'all' ? options.allTotal.value : options.total.value) - excludedIds.value.length,
      )
      : selectedIds.value.length
  ))
  const selectionScope = computed<AccountSelectionScope>(() => {
    if (!scopedSelectionActive.value) {
      return { mode: 'explicit', account_ids: selectedIds.value }
    }
    if (selectionMode.value === 'all') {
      return {
        mode: 'all',
        excluded_account_ids: excludedIds.value,
      }
    }
    return {
      mode: 'filter',
      ...filterSnapshot.value,
      excluded_account_ids: excludedIds.value,
    }
  })
  const allVisibleSelected = computed(() => {
    const visible = options.pagedAccounts.value.map((item) => item.id)
    if (!visible.length) return false
    return visible.every(isSelected)
  })
  const someVisibleSelected = computed(() => (
    !allVisibleSelected.value
    && options.pagedAccounts.value.some((item) => isSelected(item.id))
  ))

  function pruneToCurrentAccounts() {
    if (scopedSelectionActive.value || !selectedIds.value.length) return
    const existingIds = new Set(options.accounts.value.map((item) => item.id))
    const next = selectedIds.value.filter((id) => existingIds.has(id))
    if (next.length !== selectedIds.value.length) {
      selectedIds.value = next
      selectionRevision.value += 1
    }
  }

  function isSelected(accountId: string) {
    return scopedSelectionActive.value
      ? !excludedSet.value.has(accountId)
      : selectedSet.value.has(accountId)
  }

  function toggleSelect(accountId: string, checked?: boolean) {
    if (scopedSelectionActive.value) {
      const next = new Set(excludedIds.value)
      const shouldSelect = typeof checked === 'boolean' ? checked : next.has(accountId)
      if (shouldSelect) next.delete(accountId)
      else next.add(accountId)
      excludedIds.value = Array.from(next)
      authoritativeSelectedCount.value = null
      selectionRevision.value += 1
      return
    }

    const next = new Set(selectedIds.value)
    const shouldSelect = typeof checked === 'boolean' ? checked : !next.has(accountId)
    if (shouldSelect) next.add(accountId)
    else next.delete(accountId)
    selectedIds.value = Array.from(next)
    selectionRevision.value += 1
  }

  function clearSelection() {
    selectionMode.value = 'explicit'
    selectedIds.value = []
    excludedIds.value = []
    authoritativeSelectedCount.value = null
    selectionRevision.value += 1
  }

  function clearExplicitSelection() {
    if (!scopedSelectionActive.value) clearSelection()
  }

  function selectAllMatching() {
    if (!options.total.value) return
    selectionMode.value = 'filter'
    selectedIds.value = []
    excludedIds.value = []
    filterSnapshot.value = {
      keyword: options.keyword.value.trim(),
      status: options.status.value,
      group_id: options.groupId.value,
    }
    authoritativeSelectedCount.value = options.total.value
    selectionRevision.value += 1
  }

  function selectAllAccounts() {
    if (!options.allTotal.value) return
    selectionMode.value = 'all'
    selectedIds.value = []
    excludedIds.value = []
    authoritativeSelectedCount.value = options.allTotal.value
    selectionRevision.value += 1
  }

  function toggleSelectAllVisible(checked?: boolean) {
    const ids = options.pagedAccounts.value.map((item) => item.id)
    const shouldSelect = typeof checked === 'boolean' ? checked : !allVisibleSelected.value
    if (scopedSelectionActive.value) {
      const next = new Set(excludedIds.value)
      for (const id of ids) {
        if (shouldSelect) next.delete(id)
        else next.add(id)
      }
      excludedIds.value = Array.from(next)
      authoritativeSelectedCount.value = null
      selectionRevision.value += 1
      return
    }

    const next = new Set(selectedIds.value)
    for (const id of ids) {
      if (shouldSelect) next.add(id)
      else next.delete(id)
    }
    selectedIds.value = Array.from(next)
    selectionRevision.value += 1
  }

  function reconcileScopedSelection(
    preview: AccountSelectionPreview,
    expectedRevision: number,
  ) {
    if (!scopedSelectionActive.value || selectionRevision.value !== expectedRevision) return false
    excludedIds.value = Array.from(new Set(
      (preview.excluded_account_ids || []).map((id) => String(id || '').trim()).filter(Boolean),
    ))
    const matchingCount = Math.max(0, Number(preview.matching_count || 0))
    authoritativeSelectedCount.value = Math.min(
      matchingCount,
      Math.max(0, Number(preview.selected_count || 0)),
    )
    return true
  }

  function removeSelectedIds(ids: readonly string[]) {
    if (!ids.length) return
    if (scopedSelectionActive.value) {
      clearSelection()
      return
    }
    const removed = new Set(ids)
    selectedIds.value = selectedIds.value.filter((id) => !removed.has(id))
    selectionRevision.value += 1
  }

  return {
    selectedIds,
    selectedCount,
    selectionRevision,
    selectionScope,
    scopedSelectionActive,
    allVisibleSelected,
    someVisibleSelected,
    pruneToCurrentAccounts,
    isSelected,
    toggleSelect,
    clearSelection,
    clearExplicitSelection,
    selectAllMatching,
    selectAllAccounts,
    toggleSelectAllVisible,
    reconcileScopedSelection,
    removeSelectedIds,
  }
}
