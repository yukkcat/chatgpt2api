<template>
  <ModalShell
    :open="modal === 'cpa'"
    :aria-label="editingCpaPoolId ? '编辑 CPA 连接' : '新增 CPA 连接'"
    :z-index="130"
    close-on-backdrop
    @close="$emit('close')"
  >
    <ModalHeader
      :title="editingCpaPoolId ? '编辑 CPA 连接' : '新增 CPA 连接'"
      subtitle="用于账号管理里的远程 CPA 导入。"
      :close-disabled="savingExternalSource === 'cpa'"
      :bordered="false"
      @close="$emit('close')"
    />
    <ModalBody class="space-y-3">
      <div class="grid gap-3 md:grid-cols-2">
        <FormField label="名称">
          <Input v-model.trim="cpaForm.name" block placeholder="主 CPA" />
        </FormField>
        <FormField label="CPA 地址">
          <Input v-model.trim="cpaForm.base_url" block placeholder="http://your-cpa-host:8317" />
        </FormField>
      </div>
      <FormField label="管理密钥">
        <Input v-model="cpaForm.secret_key" type="password" block :placeholder="editingCpaPoolId ? '留空则不修改密钥' : 'CPA 管理密钥'" />
      </FormField>
    </ModalBody>
    <ModalFooter :bordered="false">
      <Button size="sm" variant="outline" :disabled="savingExternalSource === 'cpa'" @click="$emit('close')">取消</Button>
      <Button size="sm" variant="primary" :disabled="savingExternalSource === 'cpa'" @click="$emit('saveCpa')">
        {{ savingExternalSource === 'cpa' ? '保存中...' : '保存' }}
      </Button>
    </ModalFooter>
  </ModalShell>

  <ModalShell
    :open="modal === 'sub2api'"
    :aria-label="editingSub2apiId ? '编辑 Sub2API 连接' : '新增 Sub2API 连接'"
    :z-index="130"
    close-on-backdrop
    @close="$emit('close')"
  >
    <ModalHeader
      :title="editingSub2apiId ? '编辑 Sub2API 连接' : '新增 Sub2API 连接'"
      subtitle="用于账号管理里的 Sub2API 远程导入。"
      :close-disabled="savingExternalSource === 'sub2api'"
      :bordered="false"
      @close="$emit('close')"
    />
    <ModalBody class="space-y-3">
      <div class="grid gap-3 md:grid-cols-2">
        <FormField label="名称">
          <Input v-model.trim="sub2apiForm.name" block placeholder="自建 Sub2API" />
        </FormField>
        <FormField label="Sub2API 地址">
          <Input v-model.trim="sub2apiForm.base_url" block placeholder="http://your-sub2api-host:8080" />
        </FormField>
        <FormField label="管理员邮箱">
          <Input v-model.trim="sub2apiForm.email" block placeholder="admin@example.com" />
        </FormField>
        <FormField label="密码">
          <Input v-model="sub2apiForm.password" type="password" block :placeholder="editingSub2apiId ? '留空则不修改密码' : '管理员密码'" />
        </FormField>
        <FormField label="Admin API Key">
          <Input v-model="sub2apiForm.api_key" type="password" block :placeholder="editingSub2apiId ? '留空则不修改密钥' : '可替代邮箱密码'" />
        </FormField>
        <FormField label="默认分组 ID">
          <Input v-model.trim="sub2apiForm.group_id" block placeholder="可选" />
        </FormField>
      </div>
    </ModalBody>
    <ModalFooter :bordered="false">
      <Button size="sm" variant="outline" :disabled="savingExternalSource === 'sub2api'" @click="$emit('close')">取消</Button>
      <Button size="sm" variant="primary" :disabled="savingExternalSource === 'sub2api'" @click="$emit('saveSub2api')">
        {{ savingExternalSource === 'sub2api' ? '保存中...' : '保存' }}
      </Button>
    </ModalFooter>
  </ModalShell>
</template>

<script setup lang="ts">
import { Button, FormField, Input } from 'nanocat-ui'
import ModalBody from '@/components/ai/ModalBody.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import type { CPAForm, Sub2APIForm } from '@/views/settings/externalSourceView'

defineProps<{
  modal: 'cpa' | 'sub2api' | ''
  cpaForm: CPAForm
  sub2apiForm: Sub2APIForm
  editingCpaPoolId: string
  editingSub2apiId: string
  savingExternalSource: string
}>()

defineEmits<{
  close: []
  saveCpa: []
  saveSub2api: []
}>()
</script>
