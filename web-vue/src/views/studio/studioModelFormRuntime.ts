import { computed, reactive, ref, watch } from 'vue'
import {
  DEFAULT_IMAGE_MODEL,
  DEFAULT_IMAGE_QUALITY,
  DEFAULT_IMAGE_SIZE,
  isImageSizeSupportedByModel,
} from '@/api/imageTasks'
import { useModelCatalog } from '@/composables/useModelCatalog'
import {
  getStringPreference,
  preferenceKeys,
  setStringPreference,
} from '@/lib/preferences'
import type { StudioImageForm } from '@/components/studio/types'

export function useStudioModelFormRuntime() {
  const { catalog, chatModels, imageModels, loadModelCatalog } = useModelCatalog()
  const chatModel = ref(getStringPreference(preferenceKeys.studioChatModel, 'auto') || 'auto')
  const chatReasoningEffort = ref(getStringPreference(preferenceKeys.studioChatReasoningEffort, ''))
  const imageForm = reactive<StudioImageForm>({
    model: getStringPreference(preferenceKeys.studioImageModel, DEFAULT_IMAGE_MODEL) || DEFAULT_IMAGE_MODEL,
    size: DEFAULT_IMAGE_SIZE,
    quality: DEFAULT_IMAGE_QUALITY,
    n: 1,
  })

  const chatModelOptions = computed(() => (
    catalog.value ? [...chatModels.value] : uniqueStrings([chatModel.value])
  ))
  const imageModelOptions = computed(() => (
    catalog.value ? [...imageModels.value] : uniqueStrings([imageForm.model])
  ))
  const imageHighResolutionEnabled = computed(() => {
    const capabilities = catalog.value?.capabilities
    return Boolean(
      capabilities?.image_upscale
      || capabilities?.high_resolution_image_models.includes(imageForm.model),
    )
  })

  watch(chatModel, (model) => setStringPreference(preferenceKeys.studioChatModel, model || 'auto'))
  watch(chatReasoningEffort, (effort) => setStringPreference(preferenceKeys.studioChatReasoningEffort, effort || ''))
  watch(() => imageForm.model, (model) => {
    setStringPreference(preferenceKeys.studioImageModel, model || DEFAULT_IMAGE_MODEL)
  })
  watch(catalog, (value) => {
    if (!value) return
    if (!value.chat_models.includes(chatModel.value)) {
      chatModel.value = value.defaults.chat_model
    }
    if (!value.image_models.includes(imageForm.model)) {
      imageForm.model = value.defaults.image_model
    }
  }, { immediate: true })
  watch([() => imageForm.model, imageHighResolutionEnabled], ([, highResolutionEnabled]) => {
    if (!isImageSizeSupportedByModel(imageForm.size, highResolutionEnabled)) imageForm.size = DEFAULT_IMAGE_SIZE
  })

  return {
    chatModel,
    chatModelOptions,
    chatReasoningEffort,
    imageForm,
    imageModelOptions,
    imageHighResolutionEnabled,
    loadModelCatalog,
  }
}

function uniqueStrings(values: string[]) {
  return values.map((value) => String(value || '').trim()).filter((value, index, arr) => value && arr.indexOf(value) === index)
}
