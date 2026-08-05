<template>
  <ModalShell
    :open="modal === 'create'"
    aria-label="创建用户密钥"
    :z-index="130"
    close-on-backdrop
    @close="$emit('close')"
  >
    <ModalHeader
      title="创建用户密钥"
      subtitle="名称只是备注；创建后会生成一条只展示一次的原始密钥。"
      :close-disabled="busy === 'create'"
      :bordered="false"
      @close="$emit('close')"
    />
    <ModalBody class="space-y-3">
      <FormField label="名称">
        <Input v-model.trim="form.name" block placeholder="例如：运营画图账号" />
      </FormField>
    </ModalBody>
    <ModalFooter :bordered="false">
      <Button size="sm" variant="outline" :disabled="busy === 'create'" @click="$emit('close')">取消</Button>
      <Button size="sm" variant="primary" :disabled="busy === 'create'" @click="$emit('create')">
        {{ busy === 'create' ? '创建中...' : '创建' }}
      </Button>
    </ModalFooter>
  </ModalShell>

  <ModalShell
    :open="modal === 'edit'"
    aria-label="编辑用户密钥"
    :z-index="130"
    close-on-backdrop
    @close="$emit('close')"
  >
    <ModalHeader
      title="编辑用户密钥"
      subtitle="可以修改备注名称；填写新的专用密钥会让旧密钥失效。"
      :close-disabled="isEditBusy"
      :bordered="false"
      @close="$emit('close')"
    />
    <ModalBody class="space-y-3">
      <FormField label="名称">
        <Input v-model.trim="form.name" block placeholder="例如：运营画图账号" />
      </FormField>
      <FormField label="新的专用密钥（可选）">
        <Input v-model.trim="form.key" block root-class="font-mono" placeholder="留空则不修改当前密钥" />
      </FormField>
    </ModalBody>
    <ModalFooter :bordered="false">
      <Button size="sm" variant="outline" :disabled="isEditBusy" @click="$emit('close')">取消</Button>
      <Button size="sm" variant="primary" :disabled="isEditBusy" @click="$emit('update')">
        {{ isEditBusy ? '保存中...' : '保存' }}
      </Button>
    </ModalFooter>
  </ModalShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button, FormField, Input } from 'nanocat-ui'
import type { UserKey } from '@/api/userKeys'
import ModalBody from '@/components/ai/ModalBody.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import type { UserKeyForm } from '@/views/settings/settingsUserKeysRuntime'

const props = defineProps<{
  modal: 'create' | 'edit' | ''
  form: UserKeyForm
  editingUserKey: UserKey | null
  busy: string
}>()

defineEmits<{
  close: []
  create: []
  update: []
}>()

const isEditBusy = computed(() => Boolean(props.editingUserKey && props.busy === props.editingUserKey.id))
</script>
