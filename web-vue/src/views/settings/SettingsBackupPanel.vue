<template>
  <div class="space-y-4">
    <FormSection title="R2 备份管理">
      <div class="backup-switch-grid">
        <div class="backup-switch-item">
          <div class="backup-switch-control">
            <Checkbox
              v-model="backup.enabled"
              :disabled="fieldReadOnly('backup.enabled')"
            >启用定时备份</Checkbox>
          </div>
        </div>
        <div class="backup-switch-item">
          <div class="backup-switch-control">
            <Checkbox
              v-model="backup.encrypt"
              :disabled="fieldReadOnly('backup.encrypt')"
            >启用备份加密</Checkbox>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 gap-2.5 md:grid-cols-2">
        <FormField label="Cloudflare Account ID">
          <Input
            v-model.trim="backup.account_id"
            block
            :disabled="fieldReadOnly('backup.account_id')"
          />
        </FormField>

        <FormField label="Bucket 名称">
          <Input
            v-model.trim="backup.bucket"
            block
            :disabled="fieldReadOnly('backup.bucket')"
          />
        </FormField>
      </div>

      <div class="grid grid-cols-1 gap-2.5 md:grid-cols-2">
        <FormField label="Access Key ID">
          <Input
            v-model.trim="backup.access_key_id"
            block
            :disabled="fieldReadOnly('backup.access_key_id')"
          />
        </FormField>

        <FormField label="Secret Access Key">
          <Input
            v-model="backup.secret_access_key"
            type="password"
            block
            :disabled="fieldReadOnly('backup.secret_access_key')"
            :placeholder="backup.has_secret_access_key ? '已配置，留空不修改' : '请输入 Secret Access Key'"
          />
        </FormField>
      </div>

      <div class="grid grid-cols-1 gap-2.5 md:grid-cols-2">
        <FormField label="备份前缀">
          <Input
            v-model.trim="backup.prefix"
            block
            :disabled="fieldReadOnly('backup.prefix')"
            placeholder="backups"
          />
        </FormField>

        <FormField label="保留份数">
          <SettingsNumberInput :field="backupRotationKeepField" />
        </FormField>
      </div>

      <FormField label="备份间隔（分钟）">
        <SettingsNumberInput :field="backupIntervalMinutesField" />
      </FormField>

      <FormField label="加密口令">
        <Input
          v-model="backup.passphrase"
          type="password"
          block
          :disabled="fieldReadOnly('backup.passphrase')"
          :placeholder="backup.has_passphrase ? '已配置，留空不修改' : '留空'"
        />
      </FormField>

      <div class="space-y-2">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <p class="text-xs font-medium text-foreground">备份内容</p>
          <span class="text-xs text-muted-foreground">Application Database 始终包含</span>
        </div>
        <div class="settings-check-grid">
          <div
            v-for="item in backupIncludeOptions"
            :key="item.value"
            class="settings-check-item"
          >
            <Checkbox
              v-model="backup.include[item.value]"
              :disabled="fieldReadOnly(`backup.include.${item.value}`)"
            >{{ item.label }}</Checkbox>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <Button size="xs" variant="outline" :disabled="backupBusy === 'test'" @click="$emit('testConnection')">
          {{ backupBusy === 'test' ? '测试中...' : '测试连接' }}
        </Button>
        <Button size="xs" variant="outline" :disabled="backupBusy === 'run' || backupState?.running" @click="$emit('runNow')">
          {{ backupBusy === 'run' || backupState?.running ? '备份中...' : '立即备份' }}
        </Button>
        <Button size="xs" variant="outline" :disabled="backupLoading" @click="$emit('loadBackups')">
          {{ backupLoading ? '加载中...' : '刷新历史' }}
        </Button>
      </div>

      <div v-if="backupTestResult" class="rounded-xl border border-border bg-background px-3 py-2 text-xs">
        <p :class="backupTestResult.ok ? 'text-emerald-600' : 'text-rose-600'">
          {{ backupTestResult.ok ? '备份连接可用' : '备份连接不可用' }}
          <span v-if="backupTestResult.status"> · HTTP {{ backupTestResult.status }}</span>
        </p>
        <p v-if="backupTestResult.error" class="mt-1 break-all text-rose-600">{{ backupTestResult.error }}</p>
      </div>

      <div class="rounded-xl border border-border bg-background px-3 py-3 text-xs">
        <div class="grid grid-cols-2 gap-2 text-muted-foreground">
          <span>最近状态</span>
          <span class="text-right text-foreground">{{ backupStatusText }}</span>
          <span>最近开始</span>
          <span class="text-right text-foreground">{{ formatDateTime(backupState?.last_started_at) }}</span>
          <span>最近完成</span>
          <span class="text-right text-foreground">{{ formatDateTime(backupState?.last_finished_at) }}</span>
          <span>最近对象</span>
          <span class="break-all text-right font-mono text-foreground">{{ backupState?.last_object_key || '-' }}</span>
          <span>最近错误</span>
          <span class="break-all text-right text-rose-600">{{ backupState?.last_error || '-' }}</span>
        </div>
      </div>

      <div v-if="backupItems.length > 0" class="space-y-2">
        <div
          v-for="item in visibleBackupItems"
          :key="item.key"
          class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-card px-3 py-2 text-xs"
        >
          <div class="min-w-0">
            <p class="truncate font-medium text-foreground">{{ item.name || item.key }}</p>
            <p class="mt-1 text-muted-foreground">{{ formatBytes(item.size_bytes ?? item.size ?? 0) }} · {{ item.last_modified || '-' }}</p>
          </div>
          <Button
            size="xs"
            variant="outline"
            root-class="text-rose-600"
            :disabled="backupBusy === item.key"
            @click="$emit('deleteItem', item)"
          >
            删除
          </Button>
        </div>
      </div>
    </FormSection>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button, Checkbox, FormField, FormSection, Input } from 'nanocat-ui'
import type { BackupItem, BackupState, BackupTestResult } from '@/api/settings'
import type { Settings } from '@/types/api'
import SettingsNumberInput from '@/views/settings/SettingsNumberInput.vue'
import {
  formatBytes,
  formatDateTime,
  settingsBooleanFieldOptions,
  settingsFieldReadOnly,
  type SettingsFields,
} from '@/views/settings/settingsView'
import type { NumberSettingField } from '@/views/settings/useNumberSettingField'

const props = defineProps<{
  settings: Settings
  fields: SettingsFields
  backupIntervalMinutesField: NumberSettingField
  backupRotationKeepField: NumberSettingField
  backupBusy: string
  backupLoading: boolean
  backupState: BackupState | null
  backupItems: BackupItem[]
  backupTestResult: BackupTestResult | null
  backupStatusText: string
}>()

defineEmits<{
  testConnection: []
  runNow: []
  loadBackups: []
  deleteItem: [item: BackupItem]
}>()

const visibleBackupItems = computed(() => props.backupItems.slice(0, 5))
const backup = computed(() => props.settings.backup as NonNullable<Settings['backup']>)
const fieldReadOnly = (path: string) => settingsFieldReadOnly(props.fields, path)
const backupIncludeOptions = computed(() => (
  settingsBooleanFieldOptions(props.fields, 'backup.include.', backup.value.include)
))
</script>

<style scoped>
.settings-check-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13.5rem, 1fr));
  gap: 8px;
}

.backup-switch-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
}

@media (min-width: 768px) {
  .backup-switch-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.backup-switch-item,
.settings-check-item {
  min-height: 38px;
  border: 1px solid hsl(var(--border));
  border-radius: 14px;
  background: hsl(var(--background) / 0.72);
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease;
}

.backup-switch-item:hover,
.settings-check-item:hover {
  border-color: hsl(var(--foreground) / 0.18);
  background: hsl(var(--muted) / 0.24);
}

.backup-switch-control {
  display: flex;
  min-height: 36px;
  align-items: center;
  padding: 0 10px;
}

.settings-check-item {
  display: flex;
  align-items: center;
  padding: 0 10px;
}
</style>
