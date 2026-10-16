import { computed } from 'vue'
import type { ActionMenuItem } from 'nanocat-ui'

import { actionMenuGroups } from '@/components/ai/menuItems'
import type { AccountBulkAction } from './accountBulkActionsRuntime'
import type { AccountExportFormat, AccountExportScope } from './accountExportRuntime'
import {
  ACCOUNT_IMPORT_MODE_CATALOG,
  isAccountImportMode,
  type AccountImportMode,
} from './accountImportRuntime'

type ReadableRef<T> = {
  readonly value: T
}

type WritableRef<T> = {
  value: T
}

type AccountGroupBindOption = {
  label: string
  value: string
}

export type AccountActionMenuItem = ActionMenuItem & {
  children?: AccountActionMenuItem[]
}

type AccountActionMenuRuntimeOptions = {
  selectedCount: ReadableRef<number>
  accountAllTotal: ReadableRef<number>
  accountMatchingTotal: ReadableRef<number>
  allMatchingSelected: ReadableRef<boolean>
  accountGroupsLoading: ReadableRef<boolean>
  bindAccountGroupOptions: ReadableRef<readonly AccountGroupBindOption[]>
  selectedBindGroupId: WritableRef<string>
  openCreateModal: () => void
  openImportModal: (mode: AccountImportMode) => void
  exportAccounts: (scope: AccountExportScope, format?: AccountExportFormat) => Promise<void>
  runBulkAction: (action: AccountBulkAction) => Promise<void>
  bindSelectedAccountsToGroup: () => Promise<void>
  selectAllAccounts: () => void
  selectAllMatching: () => void
  clearSelection: () => void
}

const BIND_ACCOUNT_GROUP_ACTION_PREFIX = 'bind_group:'

const accountBulkActions = new Set<AccountBulkAction>([
  'sync',
  'refresh-access-token',
  'enable',
  'disable',
  'delete',
])

function isAccountBulkAction(value: string): value is AccountBulkAction {
  return accountBulkActions.has(value as AccountBulkAction)
}

export function useAccountActionMenuRuntime(options: AccountActionMenuRuntimeOptions) {
  const bindAccountGroupBatchItems = computed<AccountActionMenuItem[]>(() => {
    const disabled = options.selectedCount.value === 0 || options.accountGroupsLoading.value
    const normalOptions = options.bindAccountGroupOptions.value.filter((option) => (
      option.value && option.value !== '__ungrouped__'
    ))
    const ungroupedOptions = options.bindAccountGroupOptions.value.filter((option) => (
      option.value === '__ungrouped__'
    ))
    const children = actionMenuGroups<AccountActionMenuItem>(
      normalOptions.map((option) => ({
        key: `${BIND_ACCOUNT_GROUP_ACTION_PREFIX}${option.value}`,
        label: `Bind to ${option.label}`,
        disabled,
      })),
      ungroupedOptions.map((option) => ({
        key: `${BIND_ACCOUNT_GROUP_ACTION_PREFIX}${option.value}`,
        label: option.label,
        disabled,
      })),
    )

    return [{
      key: 'bind_group_menu',
      label: 'Bind group',
      disabled: disabled || children.length === 0,
      children,
    }]
  })

  const accountEntryItems = computed<ActionMenuItem[]>(() => actionMenuGroups(
    [
      { key: 'create', label: 'Add account manually' },
    ],
    ACCOUNT_IMPORT_MODE_CATALOG.map((item) => ({ key: item.value, label: item.label })),
  ))

  const exportMenuItems = computed<ActionMenuItem[]>(() => actionMenuGroups(
    [
      {
        key: 'selected_json',
        label: `Selected accounts · full JSON${options.selectedCount.value ? ` (${options.selectedCount.value})` : ''}`,
        disabled: options.selectedCount.value === 0,
      },
      {
        key: 'selected_txt',
        label: 'Selected accounts · access token TXT',
        disabled: options.selectedCount.value === 0,
      },
    ],
    [
      {
        key: 'all_json',
        label: 'All accounts · full JSON',
        disabled: options.accountAllTotal.value === 0,
      },
      {
        key: 'all_txt',
        label: 'All accounts · access token TXT',
        disabled: options.accountAllTotal.value === 0,
      },
    ],
  ))

  const batchMenuItems = computed<AccountActionMenuItem[]>(() => actionMenuGroups<AccountActionMenuItem>(
    [
      {
        key: 'select-all-accounts',
        label: 'Select all accounts',
        disabled: options.accountAllTotal.value === 0 || options.selectedCount.value >= options.accountAllTotal.value,
      },
      {
        key: 'select-all-matching',
        label: 'Select all filtered accounts',
        disabled: options.accountMatchingTotal.value === 0 || options.allMatchingSelected.value,
      },
      {
        key: 'clear-selection',
        label: options.selectedCount.value ? `Clear selection (${options.selectedCount.value})` : 'Clear selection',
        disabled: options.selectedCount.value === 0,
      },
    ],
    [
      { key: 'refresh-access-token', label: 'Refresh AT in bulk', disabled: options.selectedCount.value === 0 },
      { key: 'sync', label: 'Sync accounts and quotas in bulk', disabled: options.selectedCount.value === 0 },
    ],
    bindAccountGroupBatchItems.value,
    [
      { key: 'enable', label: 'Enable selected', disabled: options.selectedCount.value === 0 },
      { key: 'disable', label: 'Disable selected', disabled: options.selectedCount.value === 0 },
      { key: 'delete', label: 'Delete selected', danger: true, disabled: options.selectedCount.value === 0 },
    ],
  ))

  const batchMenuLabel = 'Bulk actions'

  async function handleBatchAction(action: string) {
    if (action === 'select-all-accounts') {
      options.selectAllAccounts()
      return
    }
    if (action === 'select-all-matching') {
      options.selectAllMatching()
      return
    }
    if (action === 'clear-selection') {
      options.clearSelection()
      return
    }
    if (action.startsWith(BIND_ACCOUNT_GROUP_ACTION_PREFIX)) {
      options.selectedBindGroupId.value = action.slice(BIND_ACCOUNT_GROUP_ACTION_PREFIX.length)
      await options.bindSelectedAccountsToGroup()
      return
    }
    if (isAccountBulkAction(action)) {
      await options.runBulkAction(action)
    }
  }

  function handleAccountEntryAction(key: string) {
    if (key === 'create') {
      options.openCreateModal()
      return
    }
    if (isAccountImportMode(key)) {
      options.openImportModal(key)
    }
  }

  async function handleExportAction(key: string) {
    const match = /^(selected|all)_(json|txt)$/.exec(key)
    if (!match) return
    await options.exportAccounts(
      match[1] as AccountExportScope,
      match[2] as AccountExportFormat,
    )
  }

  return {
    accountEntryItems,
    exportMenuItems,
    batchMenuItems,
    batchMenuLabel,
    handleBatchAction,
    handleAccountEntryAction,
    handleExportAction,
  }
}
