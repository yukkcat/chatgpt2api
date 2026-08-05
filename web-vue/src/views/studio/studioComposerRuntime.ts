import { ref, watch } from 'vue'
import type { StudioComposeMode, StudioFileKind, StudioMessage } from '@/components/studio/types'
import { getStringPreference, preferenceKeys, setStringPreference } from '@/lib/preferences'

export function normalizeStudioComposeMode(value: string): StudioComposeMode {
  if (value === 'chat' || value === 'search' || value === 'file') return value
  return 'image'
}

export function normalizeStudioFileKind(value: string): StudioFileKind {
  return value === 'psd' ? 'psd' : 'ppt'
}

export function useStudioComposerRuntime() {
  const composeMode = ref<StudioComposeMode>(
    normalizeStudioComposeMode(getStringPreference(preferenceKeys.studioActiveMode, 'image')),
  )
  const composerText = ref('')
  const fileKind = ref<StudioFileKind>(
    normalizeStudioFileKind(getStringPreference(preferenceKeys.studioFileKind, 'ppt')),
  )
  const editingMessageId = ref('')
  const isSending = ref(false)

  watch(composeMode, (mode) => setStringPreference(preferenceKeys.studioActiveMode, mode))
  watch(fileKind, (kind) => setStringPreference(preferenceKeys.studioFileKind, kind))

  function cancelMessageEdit(clearComposer = true) {
    editingMessageId.value = ''
    if (clearComposer) composerText.value = ''
  }

  function fillFromMessage(message: StudioMessage) {
    composerText.value = message.content
    composeMode.value = message.mode
    if (message.fileKind) fileKind.value = message.fileKind
  }

  function startEdit(message: StudioMessage) {
    editingMessageId.value = message.id
    composerText.value = message.content
    composeMode.value = message.mode
    if (message.fileKind) fileKind.value = message.fileKind
  }

  function setSending(value: boolean) {
    isSending.value = value
  }

  function activateImageMode() {
    composeMode.value = 'image'
  }

  return {
    activateImageMode,
    cancelMessageEdit,
    composeMode,
    composerText,
    editingMessageId,
    fileKind,
    fillFromMessage,
    isSending,
    setSending,
    startEdit,
  }
}
