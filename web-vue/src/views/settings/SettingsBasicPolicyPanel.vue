<template>
  <div class="space-y-4">
    <FormSection title="Account policies">
      <div class="settings-check-grid settings-check-grid--single">
        <div class="settings-check-item">
          <div class="settings-check-control">
            <Checkbox
              v-model="settings.auto_remove_invalid_accounts"
              :disabled="fieldReadOnly('auto_remove_invalid_accounts')"
            >Automatically remove invalid accounts</Checkbox>
            <HelpTip text="Accounts confirmed to have invalid credentials are marked as invalid. When enabled, they are removed; when disabled, they remain in the invalid state." />
          </div>
        </div>
        <div class="settings-check-item">
          <div class="settings-check-control">
            <Checkbox
              v-model="settings.auto_remove_rate_limited_accounts"
              :disabled="fieldReadOnly('auto_remove_rate_limited_accounts')"
            >Automatically remove accounts with exhausted quotas</Checkbox>
            <HelpTip text="This applies only when the upstream explicitly confirms that the image quota is 0. Proxy errors, interrupted streams, and upstream HTTP 429 responses do not remove accounts." />
          </div>
        </div>
        <div class="settings-check-item">
          <div class="settings-check-control">
            <Checkbox
              v-model="settings.image_account_retry_enabled"
              :disabled="fieldReadOnly('image_account_retry_enabled')"
            >Try another account when image generation fails</Checkbox>
            <HelpTip text="If the current account does not return an image, another account is tried immediately, except when the result is text (HTTP 400). The request does not wait for background account verification." />
          </div>
        </div>
      </div>
      <FormField label="Maximum accounts to try">
        <template #label-extra>
          <HelpTip text="Includes the first account tried. Default: 4; minimum: 2. There is no maximum value." />
        </template>
        <SettingsNumberInput
          :field="imageMaxAccountAttemptsField"
          :disabled="!settings.image_account_retry_enabled"
        />
      </FormField>
    </FormSection>

    <FormSection title="Image confirmation">
      <div class="settings-check-grid settings-check-grid--single">
        <div class="settings-check-item">
          <div class="settings-check-control">
            <Checkbox
              v-model="settings.image_settle_enabled"
              :disabled="fieldReadOnly('image_settle_enabled')"
            >Recheck image results</Checkbox>
            <HelpTip text="After an image result is found, wait the specified number of seconds and check again to avoid returning an unstable result." />
          </div>
        </div>
        <div class="settings-check-item">
          <div class="settings-check-control">
            <Checkbox
              v-model="settings.image_remove_conversation_after_result"
              :disabled="fieldReadOnly('image_remove_conversation_after_result')"
            >Remove the ChatGPT conversation after a successful image result</Checkbox>
            <HelpTip text="Off by default. After an image is saved successfully, the system tries to hide the ChatGPT conversation. Failure is logged and does not affect the returned image. When disabled, the conversation is kept for recovery and troubleshooting." />
          </div>
        </div>
      </div>
      <FormField label="Recheck delay (seconds)">
        <SettingsNumberInput
          :field="imageSettleSecondsField"
          :disabled="!settings.image_settle_enabled"
        />
      </FormField>
    </FormSection>

    <FormSection title="Image upscaling">
      <div class="settings-check-grid settings-check-grid--single">
        <div class="settings-check-item">
          <div class="settings-check-control">
            <Checkbox
              v-model="settings.image_upscale_enabled"
              :disabled="fieldReadOnly('image_upscale_enabled')"
            >Automatically upscale undersized images</Checkbox>
            <HelpTip text="Off by default. Applies only when a size was explicitly requested and the upstream image is smaller than the target. Automatic sizes and images that already meet the target are left unchanged." />
          </div>
        </div>
      </div>
      <FormField label="Upscaling engine">
        <GroupedSelectMenu
          v-model="settings.image_upscale_engine"
          :options="imageUpscaleEngineOptions"
          :disabled="!settings.image_upscale_enabled || fieldReadOnly('image_upscale_engine')"
          selected-indicator="none"
          aria-label="Image upscaling engine"
          block
        />
      </FormField>
    </FormSection>

    <FormSection title="Console log levels">
      <div class="settings-check-grid settings-check-grid--single mt-3">
        <div
          v-for="level in logLevelOptions"
          :key="level.value"
          class="settings-check-item"
        >
          <div class="settings-check-control">
            <Checkbox
              :model-value="settings.log_levels.includes(level.value)"
              :disabled="fieldReadOnly('log_levels')"
              @update:model-value="$emit('setLogLevel', level.value, Boolean($event))"
            >
              {{ level.label }}
            </Checkbox>
            <HelpTip v-if="level.value === 'debug'" text="If no levels are selected, the defaults are info / warning / error." />
          </div>
        </div>
      </div>
    </FormSection>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Checkbox, FormField, FormSection, HelpTip } from 'nanocat-ui'
import { GroupedSelectMenu } from 'nanocat-ui'
import type { Settings } from '@/types/api'
import SettingsNumberInput from '@/views/settings/SettingsNumberInput.vue'
import {
  settingsFieldOptions,
  settingsFieldReadOnly,
  type SettingsFields,
} from '@/views/settings/settingsView'
import type { NumberSettingField } from '@/views/settings/useNumberSettingField'

const props = defineProps<{
  settings: Settings
  fields: SettingsFields
  imageMaxAccountAttemptsField: NumberSettingField
  imageSettleSecondsField: NumberSettingField
}>()

defineEmits<{
  setLogLevel: [level: string, enabled: boolean]
}>()

const fieldReadOnly = (path: string) => settingsFieldReadOnly(props.fields, path)
const imageUpscaleEngineOptions = computed(() => (
  settingsFieldOptions(props.fields, 'image_upscale_engine', props.settings.image_upscale_engine)
))
const logLevelOptions = computed(() => (
  settingsFieldOptions(props.fields, 'log_levels', props.settings.log_levels)
))
</script>

<style scoped>
.settings-check-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13.5rem, 1fr));
  gap: 8px;
}

.settings-check-grid--single {
  grid-template-columns: minmax(0, 1fr);
}

.settings-check-item {
  min-height: 38px;
  border: 1px solid hsl(var(--border));
  border-radius: 14px;
  background: hsl(var(--background) / 0.72);
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease;
}

.settings-check-item:hover {
  border-color: hsl(var(--foreground) / 0.18);
  background: hsl(var(--muted) / 0.24);
}

.settings-check-control {
  display: flex;
  min-height: 38px;
  align-items: center;
  gap: 8px;
  padding-right: 10px;
}

.settings-check-item :deep(label) {
  display: flex;
  width: 100%;
  flex: 1;
  min-height: 38px;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
}

.settings-check-item :deep(label > span:last-child) {
  color: hsl(var(--foreground) / 0.78);
  line-height: 1.35;
}
</style>
