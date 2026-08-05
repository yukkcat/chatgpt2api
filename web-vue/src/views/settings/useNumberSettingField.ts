import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import type { NumberSettingOptions } from './settingsView'

export type NumberSettingField = {
  input: Ref<string>
  update: (value: string) => void
  min: ComputedRef<number | undefined>
  max: ComputedRef<number | undefined>
  step: ComputedRef<number | 'any'>
  placeholder: ComputedRef<string>
  readOnly: ComputedRef<boolean>
  error: ComputedRef<string>
  isValid: ComputedRef<boolean>
}

export function useNumberSettingField(
  getter: () => number | null | undefined,
  setter: (value: number) => void,
  options: NumberSettingOptions = {},
): NumberSettingField {
  const input = ref('')
  const metadata = computed(() => options.metadata?.() || null)
  const min = computed(() => metadata.value?.min ?? undefined)
  const max = computed(() => metadata.value?.max ?? undefined)
  const step = computed(() => options.integer ? 1 : 'any' as const)
  const placeholder = computed(() => {
    const value = metadata.value?.default
    return value == null ? '' : String(value)
  })
  const readOnly = computed(() => Boolean(metadata.value?.read_only))
  const validationEnabled = computed(() => !readOnly.value && (options.enabled?.() ?? true))
  const error = computed(() => {
    if (!validationEnabled.value) return ''
    const raw = input.value.trim()
    if (!raw) return '请输入数值'
    const value = Number(raw)
    if (!Number.isFinite(value)) return '请输入有效数值'
    if (options.integer && !Number.isInteger(value)) return '请输入整数'
    if (min.value != null && value < min.value) return `不能小于 ${min.value}`
    if (max.value != null && value > max.value) return `不能大于 ${max.value}`
    return ''
  })
  const isValid = computed(() => !error.value)

  watch(getter, (value) => {
    const next = value == null ? '' : String(value)
    if (input.value !== next) {
      input.value = next
    }
  }, { immediate: true })

  const update = (value: string) => {
    input.value = value
    const parsed = Number(value)
    if (!isValid.value || !Number.isFinite(parsed)) return
    setter(parsed)
  }

  return { input, update, min, max, step, placeholder, readOnly, error, isValid }
}
