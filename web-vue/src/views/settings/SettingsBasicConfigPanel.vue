<template>
  <div class="space-y-4">
    <FormSection title="Basic configuration">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
        <FormField label="Background maintenance interval">
          <template #label-extra>
            <HelpTip text="Minutes between background checks for accounts pending verification, rate-limited accounts, and ATs nearing expiration." />
          </template>
          <SettingsNumberInput :field="refreshAccountIntervalField" />
        </FormField>

        <FormField label="Image URL base">
          <template #label-extra>
            <HelpTip text="URL prefix used to access generated images." />
          </template>
          <Input
            v-model.trim="settings.base_url"
            block
            :disabled="fieldReadOnly('base_url')"
            placeholder="https://example.com"
          />
        </FormField>

        <FormField label="Image retention">
          <template #label-extra>
            <HelpTip text="Automatically delete local images older than this many hours." />
          </template>
          <SettingsNumberInput :field="imageRetentionHoursField" />
        </FormField>

        <FormField label="Log retention">
          <template #label-extra>
            <HelpTip text="Automatically delete console request logs older than this many hours." />
          </template>
          <SettingsNumberInput :field="logRetentionHoursField" />
        </FormField>

        <FormField label="Image concurrency per account">
          <template #label-extra>
            <HelpTip text="Maximum number of image requests processed concurrently per account. Default: 1; range: 1–3." />
          </template>
          <SettingsNumberInput :field="imageAccountConcurrencyField" />
        </FormField>

        <FormField label="Account task concurrency">
          <template #label-extra>
            <HelpTip text="Maximum concurrency for account tasks. AT refresh, account and quota sync, import verification, and background checks each use one slot per account. Enable, disable, reset, delete, and bulk save use one slot per batch. Default: 30; range: 1–100. Image generation concurrency is configured separately." />
          </template>
          <SettingsNumberInput :field="accountProcessingConcurrencyField" />
        </FormField>
      </div>
    </FormSection>

    <FormSection title="Requests and tasks">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
        <FormField label="Console request timeout">
          <template #label-extra>
            <HelpTip text="Seconds to wait for the server to respond to console requests, including logs, images, accounts, and settings." />
          </template>
          <SettingsNumberInput :field="consoleRequestTimeoutField" />
        </FormField>

      </div>
    </FormSection>

    <FormSection title="Image generation">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
        <FormField label="Image stream timeout">
          <template #label-extra>
            <HelpTip text="Maximum number of seconds to wait for the ChatGPT image generation SSE stream." />
          </template>
          <SettingsNumberInput :field="imageStreamTimeoutField" />
        </FormField>

        <FormField label="Image result timeout">
          <template #label-extra>
            <HelpTip text="Maximum number of seconds to wait for the upstream image result after the SSE stream ends." />
          </template>
          <SettingsNumberInput :field="imagePollTimeoutField" />
        </FormField>

        <FormField label="Initial image polling delay">
          <template #label-extra>
            <HelpTip text="Seconds to wait before checking for an image result." />
          </template>
          <SettingsNumberInput :field="imagePollInitialWaitField" />
        </FormField>

        <FormField label="Image polling interval">
          <template #label-extra>
            <HelpTip text="Seconds to wait between image result checks." />
          </template>
          <SettingsNumberInput :field="imagePollIntervalField" />
        </FormField>
      </div>
    </FormSection>
  </div>
</template>

<script setup lang="ts">
import { FormField, FormSection, HelpTip, Input } from 'nanocat-ui'
import type { Settings } from '@/types/api'
import SettingsNumberInput from '@/views/settings/SettingsNumberInput.vue'
import { settingsFieldReadOnly, type SettingsFields } from '@/views/settings/settingsView'
import type { NumberSettingField } from '@/views/settings/useNumberSettingField'

const props = defineProps<{
  settings: Settings
  fields: SettingsFields
  refreshAccountIntervalField: NumberSettingField
  imageRetentionHoursField: NumberSettingField
  logRetentionHoursField: NumberSettingField
  consoleRequestTimeoutField: NumberSettingField
  imagePollTimeoutField: NumberSettingField
  imageStreamTimeoutField: NumberSettingField
  imagePollInitialWaitField: NumberSettingField
  imagePollIntervalField: NumberSettingField
  imageAccountConcurrencyField: NumberSettingField
  accountProcessingConcurrencyField: NumberSettingField
}>()

const fieldReadOnly = (path: string) => settingsFieldReadOnly(props.fields, path)
</script>
