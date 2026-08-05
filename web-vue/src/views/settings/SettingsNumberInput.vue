<template>
  <div class="space-y-1">
    <input
      :value="field.input.value"
      type="number"
      class="ui-input-sm w-full"
      :class="{ '!border-rose-500': !field.isValid.value }"
      :min="field.min.value"
      :max="field.max.value"
      :step="field.step.value"
      :placeholder="field.placeholder.value"
      :disabled="disabled || field.readOnly.value"
      :aria-invalid="!field.isValid.value"
      @input="handleInput"
    />
    <p v-if="field.error.value" class="text-xs text-rose-600 dark:text-rose-400">
      {{ field.error.value }}
    </p>
  </div>
</template>

<script setup lang="ts">
import type { NumberSettingField } from '@/views/settings/useNumberSettingField'

const props = withDefaults(defineProps<{
  field: NumberSettingField
  disabled?: boolean
}>(), {
  disabled: false,
})

function handleInput(event: Event) {
  props.field.update((event.target as HTMLInputElement).value)
}
</script>
