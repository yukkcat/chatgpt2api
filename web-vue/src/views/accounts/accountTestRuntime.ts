import { computed, ref } from 'vue'

import { accountsApi } from '@/api/accounts'
import type { Account, AccountTestMode, AccountTestResult } from '@/api/accounts'
import { useModelCatalog } from '@/composables/useModelCatalog'

const CHAT_PROMPT = 'Hi！ChatGPT'
const IMAGE_PROMPT = '一只慵懒的猫咪蜷在柔软毛毯上睡觉，午后暖光，温馨室内，细节丰富，治愈系插画。'

type AccountTestRuntimeOptions = {
  loadData: () => Promise<unknown>
  setError: (prefix: string, error: unknown) => void
}

export function useAccountTestRuntime(options: AccountTestRuntimeOptions) {
  const opened = ref(false)
  const account = ref<Account | null>(null)
  const mode = ref<AccountTestMode>('chat')
  const model = ref('')
  const prompt = ref(CHAT_PROMPT)
  const running = ref(false)
  const result = ref<AccountTestResult | null>(null)
  const { catalog, chatModels, imageModels, isLoading, loadModelCatalog } = useModelCatalog()

  const modelOptions = computed(() => (
    mode.value === 'image' ? imageModels.value : chatModels.value
  ))

  function applyMode(nextMode: AccountTestMode) {
    mode.value = nextMode
    prompt.value = nextMode === 'image' ? IMAGE_PROMPT : CHAT_PROMPT
    model.value = nextMode === 'image'
      ? (catalog.value?.defaults.image_model || imageModels.value[0] || '')
      : (catalog.value?.defaults.chat_model || chatModels.value[0] || '')
    result.value = null
  }

  async function open(item: Account) {
    account.value = item
    opened.value = true
    result.value = null
    await loadModelCatalog()
    applyMode('chat')
  }

  function close() {
    if (running.value) return
    opened.value = false
    account.value = null
    result.value = null
  }

  function setMode(value: AccountTestMode) {
    if (running.value || value === mode.value) return
    applyMode(value)
  }

  async function run() {
    const target = account.value
    if (!target || running.value || !model.value || !prompt.value.trim()) return
    running.value = true
    result.value = null
    try {
      result.value = await accountsApi.testAccount(target.id, {
        mode: mode.value,
        model: model.value,
        prompt: prompt.value.trim(),
      })
      if (mode.value === 'image' && result.value.status === 'success') {
        await options.loadData()
      }
    } catch (error) {
      options.setError('账号测试失败', error)
    } finally {
      running.value = false
    }
  }

  return {
    opened,
    account,
    mode,
    model,
    prompt,
    running,
    result,
    modelOptions,
    modelCatalogLoading: isLoading,
    open,
    close,
    setMode,
    run,
  }
}
