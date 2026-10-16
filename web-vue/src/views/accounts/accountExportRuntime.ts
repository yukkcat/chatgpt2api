import { ref, type ComputedRef, type Ref } from 'vue'

import { accountsApi, type Account, type AccountSelectionScope } from '@/api/accounts'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import { saveBlob } from '@/lib/downloads'

export type AccountExportScope = 'selected' | 'all'
export type AccountExportFormat = 'json' | 'txt'

type AccountExportRuntimeOptions = {
  accounts: Ref<Account[]>
  selectedCount: ComputedRef<number>
  selectionScope: ComputedRef<AccountSelectionScope>
  scopedSelectionActive: ComputedRef<boolean>
  accountAllTotal: Ref<number>
  accountListTotal: Ref<number>
  reconcileSelection: () => Promise<boolean>
  setError: (prefix: string, error: unknown, notify?: boolean) => void
}

function createExportFilename(extension: AccountExportFormat) {
  const now = new Date()
  const parts = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
    '-',
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0'),
  ]
  return `accounts-export-${parts.join('')}.${extension}`
}

export function useAccountExportRuntime(options: AccountExportRuntimeOptions) {
  const exportBusy = ref(false)
  const toast = useToast()
  const confirmDialog = useConfirmDialog()

  async function exportAccounts(
    scope: AccountExportScope,
    format: AccountExportFormat = 'json',
  ) {
    const exportAll = scope === 'all'
    if (!exportAll && options.scopedSelectionActive.value && !await options.reconcileSelection()) return
    const count = exportAll
      ? (options.accountAllTotal.value || options.accountListTotal.value || options.accounts.value.length)
      : options.selectedCount.value
    if (!count) {
      toast.warning(scope === 'selected' ? 'Select accounts to export first' : 'No accounts to export')
      return
    }

    const formatLabel = format === 'json' ? 'Full account JSON' : 'Access Token TXT'
    const scopeLabel = exportAll ? 'all' : 'selected'
    const confirmed = await confirmDialog.ask({
      title: `Export ${scopeLabel} accounts`,
      message: format === 'json'
        ? `This will export ${count} ${scopeLabel} accounts as reusable JSON. The file contains account credentials and configuration. Store it only in a trusted environment.`
        : `This will export ${count} ${scopeLabel} accounts as TXT, with one Access Token per line. RT, ID Token, and account configuration are not included.`,
      confirmText: `Export ${formatLabel}`,
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    exportBusy.value = true
    try {
      const target: AccountSelectionScope = exportAll ? { mode: 'all' } : options.selectionScope.value
      const result = await accountsApi.exportAccounts(target, format)
      saveBlob(result.blob, createExportFilename(format))
      const skippedText = result.skipped > 0 ? `, skipped ${result.skipped}` : ''
      toast.success(`Exported ${result.exported} accounts${skippedText} · ${formatLabel}`)
    } catch (error) {
      options.setError('Export failed', error)
    } finally {
      exportBusy.value = false
    }
  }

  return {
    exportBusy,
    exportAccounts,
  }
}
