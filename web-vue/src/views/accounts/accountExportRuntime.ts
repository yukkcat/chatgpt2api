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
      toast.warning(scope === 'selected' ? '请先选择要导出的账号' : '暂无可导出的账号')
      return
    }

    const formatLabel = format === 'json' ? '完整账号 JSON' : 'Access Token TXT'
    const scopeLabel = exportAll ? '全部' : '选中'
    const confirmed = await confirmDialog.ask({
      title: `导出${scopeLabel}账号`,
      message: format === 'json'
        ? `即将把${scopeLabel} ${count} 个账号导出为可再次导入的完整 JSON。文件包含账号凭据和配置，请只在可信环境保存。`
        : `即将把${scopeLabel} ${count} 个账号导出为 TXT，每行一个 Access Token，不包含 RT、ID Token 和账号配置。`,
      confirmText: `导出 ${formatLabel}`,
      cancelText: '取消',
    })
    if (!confirmed) return

    exportBusy.value = true
    try {
      const target: AccountSelectionScope = exportAll ? { mode: 'all' } : options.selectionScope.value
      const result = await accountsApi.exportAccounts(target, format)
      saveBlob(result.blob, createExportFilename(format))
      const skippedText = result.skipped > 0 ? `，跳过 ${result.skipped} 个` : ''
      toast.success(`已导出 ${result.exported} 个账号${skippedText} · ${formatLabel}`)
    } catch (error) {
      options.setError('导出失败', error)
    } finally {
      exportBusy.value = false
    }
  }

  return {
    exportBusy,
    exportAccounts,
  }
}
