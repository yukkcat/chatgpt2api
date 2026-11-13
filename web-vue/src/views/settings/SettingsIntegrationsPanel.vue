<template>
  <div class="space-y-4">
    <template v-if="mode === 'canvas'">
      <div class="grid items-start gap-4 lg:grid-cols-2">
        <FormSection
          title="无限画布"
          subtitle="开启后顶部导航会显示画布入口，并自动带上当前接口地址和密钥。"
        >
          <div class="settings-check-grid settings-check-grid--single">
            <div class="settings-check-item">
              <div class="settings-check-control">
                <Checkbox
                  v-model="settings.third_party_apps.infinite_canvas.enabled"
                  :disabled="fieldReadOnly('third_party_apps.infinite_canvas.enabled')"
                >
                  启用无限画布入口
                </Checkbox>
              </div>
            </div>
            <div class="settings-check-item">
              <div class="settings-check-control">
                <Checkbox
                  v-model="settings.genbox_push.delete_source_after_push"
                  :disabled="!settings.genbox_push.enabled || fieldReadOnly('genbox_push.delete_source_after_push')"
                >
                  自动推送成功后删除源图（需 GenBox 回执确认）
                </Checkbox>
              </div>
            </div>
          </div>
          <FormField label="无限画布地址">
            <Input
              v-model.trim="settings.third_party_apps.infinite_canvas.url"
              block
              :disabled="fieldReadOnly('third_party_apps.infinite_canvas.url')"
              placeholder="https://canvas.best"
            />
          </FormField>
        </FormSection>

        <FormSection
          title="GenBox 图片推送"
          subtitle="配置图库手动 Push，以及 Studio 生成成功后的自动推送。"
        >
          <div class="settings-check-grid">
            <div class="settings-check-item">
              <div class="settings-check-control">
                <Checkbox
                  v-model="settings.genbox_push.enabled"
                  :disabled="fieldReadOnly('genbox_push.enabled')"
                >
                  启用 GenBox Push
                </Checkbox>
              </div>
            </div>
            <div class="settings-check-item">
              <div class="settings-check-control">
                <Checkbox
                  v-model="settings.genbox_push.auto_push_after_studio"
                  :disabled="!settings.genbox_push.enabled || fieldReadOnly('genbox_push.auto_push_after_studio')"
                >
                  Studio 成功后自动推送
                </Checkbox>
              </div>
            </div>
          </div>

          <FormField label="GenBox 地址">
            <Input
              v-model.trim="settings.genbox_push.base_url"
              block
              :disabled="fieldReadOnly('genbox_push.base_url')"
              placeholder="https://genbox.example.com"
            />
          </FormField>

          <div class="grid grid-cols-1 gap-2.5 md:grid-cols-2">
            <FormField label="来源 ID">
              <Input
                v-model.trim="settings.genbox_push.source_id"
                block
                :disabled="fieldReadOnly('genbox_push.source_id')"
                placeholder="chatgpt2api"
              />
            </FormField>

            <FormField label="请求超时（秒）">
              <SettingsNumberInput :field="genboxTimeoutSecondsField" />
            </FormField>
          </div>

          <FormField label="Push Key">
            <Input
              v-model="settings.genbox_push.push_key"
              type="password"
              block
              :disabled="fieldReadOnly('genbox_push.push_key')"
              :placeholder="settings.genbox_push.has_push_key ? '已配置，留空不修改' : '请输入 GenBox Push Key'"
            />
          </FormField>
        </FormSection>
      </div>
    </template>

    <template v-else>
      <FormSection title="接口接入" subtitle="第三方应用按 OpenAI 兼容接口接入，使用同一套 Bearer 鉴权。">
        <div class="grid gap-3 md:grid-cols-2">
          <SurfaceBox
            v-for="item in accessItems"
            :key="item.label"
            density="compact"
          >
            <p class="text-xs text-muted-foreground">{{ item.label }}</p>
            <p class="mt-1 break-all font-mono text-xs text-foreground">{{ item.value }}</p>
          </SurfaceBox>
        </div>
      </FormSection>

      <FormSection title="常用接口">
        <div class="space-y-2">
          <details
            v-for="item in apiDocItems"
            :key="item.path"
            class="rounded-xl border border-border bg-card px-4 py-3"
          >
            <summary class="flex cursor-pointer list-none items-center justify-between gap-3">
              <span class="min-w-0">
                <span class="block text-sm font-medium text-foreground">{{ item.title }}</span>
                <span class="mt-1 block truncate font-mono text-xs text-muted-foreground">{{ item.method }} {{ item.path }}</span>
              </span>
              <span class="text-xs text-muted-foreground">展开</span>
            </summary>
            <div class="mt-3 space-y-2">
              <p class="text-xs leading-5 text-muted-foreground">{{ item.description }}</p>
              <pre class="overflow-auto whitespace-pre-wrap break-all rounded-xl bg-zinc-950 px-3 py-3 text-xs leading-5 text-zinc-100">{{ item.example }}</pre>
            </div>
          </details>
        </div>
      </FormSection>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Checkbox, FormField, FormSection, Input } from 'nanocat-ui'
import SurfaceBox from '@/components/ai/SurfaceBox.vue'
import { getAuthToken } from '@/api/client'
import type { Settings } from '@/types/api'
import SettingsNumberInput from '@/views/settings/SettingsNumberInput.vue'
import type { NumberSettingField } from '@/views/settings/useNumberSettingField'
import {
  buildApiDocItems,
  settingsFieldReadOnly,
  type SettingsFields,
} from '@/views/settings/settingsView'

const props = defineProps<{
  mode: 'api-docs' | 'canvas'
  settings: Settings
  fields: SettingsFields
  genboxTimeoutSecondsField: NumberSettingField
}>()

const fieldReadOnly = (path: string) => settingsFieldReadOnly(props.fields, path)

const serviceBaseUrl = computed(() => window.location.origin)
const openAIBaseUrl = computed(() => `${serviceBaseUrl.value.replace(/\/$/, '')}/v1`)
const currentApiKey = computed(() => getAuthToken() || '<当前密钥>')
const accessItems = computed(() => [
  { label: '服务地址', value: serviceBaseUrl.value },
  { label: 'Base URL（OpenAI）', value: openAIBaseUrl.value },
  { label: 'API Key', value: currentApiKey.value },
  { label: '请求头', value: `Authorization: Bearer ${currentApiKey.value}` },
])
const apiDocItems = computed(() => (
  props.mode === 'api-docs'
    ? buildApiDocItems(serviceBaseUrl.value, currentApiKey.value)
    : []
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
