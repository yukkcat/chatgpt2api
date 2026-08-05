<template>
  <FormSection title="基础配置">
    <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
      <FormField label="后台维护间隔">
        <template #label-extra>
          <HelpTip text="单位分钟，控制待核验账号、限流账号和临期 AT 的后台处理频率。" />
        </template>
        <SettingsNumberInput :field="refreshAccountIntervalField" />
      </FormField>

      <FormField label="图片访问地址">
        <template #label-extra>
          <HelpTip text="用于生成图片结果的访问前缀地址。" />
        </template>
        <Input
          v-model.trim="settings.base_url"
          block
          :disabled="fieldReadOnly('base_url')"
          placeholder="https://example.com"
        />
      </FormField>

      <FormField label="图片自动清理">
        <template #label-extra>
          <HelpTip text="自动删除多少天前的本地图片。" />
        </template>
        <SettingsNumberInput :field="imageRetentionDaysField" />
      </FormField>

      <FormField label="日志自动清理">
        <template #label-extra>
          <HelpTip text="自动删除多少天前的控制台调用日志，清理对象是 data/logs.jsonl。" />
        </template>
        <SettingsNumberInput :field="logRetentionDaysField" />
      </FormField>

      <FormField label="图片轮询超时">
        <template #label-extra>
          <HelpTip text="单位秒，等待上游图片结果的最长时间。" />
        </template>
        <SettingsNumberInput :field="imagePollTimeoutField" />
      </FormField>

      <FormField label="上游流超时">
        <template #label-extra>
          <HelpTip text="单位秒，限制 ChatGPT 生图 SSE 流最长等待时间。" />
        </template>
        <SettingsNumberInput :field="imageStreamTimeoutField" />
      </FormField>

      <FormField label="单账号图片并发">
        <template #label-extra>
          <HelpTip text="限制每个账号同时处理的图片请求数量。默认 1，可设置为 1–3。" />
        </template>
        <SettingsNumberInput :field="imageAccountConcurrencyField" />
      </FormField>

      <FormField label="账号批量任务并发">
        <template #label-extra>
          <HelpTip text="控制账号批量任务的最大并发数。刷新 AT、同步账号与额度、导入核验和后台复查按账号占用并发；启用、禁用、重置、删除和批量保存按整个批次占用一个并发。默认 30，可设置为 1–100；图片生成并发单独设置。" />
        </template>
        <SettingsNumberInput :field="accountProcessingConcurrencyField" />
      </FormField>

    </div>
  </FormSection>
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
  imageRetentionDaysField: NumberSettingField
  logRetentionDaysField: NumberSettingField
  imagePollTimeoutField: NumberSettingField
  imageStreamTimeoutField: NumberSettingField
  imageAccountConcurrencyField: NumberSettingField
  accountProcessingConcurrencyField: NumberSettingField
}>()

const fieldReadOnly = (path: string) => settingsFieldReadOnly(props.fields, path)
</script>
