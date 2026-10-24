<template>
  <ModalShell
    :open="modal === 'cpa'"
    :aria-label="editingCpaPoolId ? 'Edit CPA connection' : 'Add CPA connection'"
    :z-index="130"
    close-on-backdrop
    @close="$emit('close')"
  >
    <ModalHeader
      :title="editingCpaPoolId ? 'Edit CPA connection' : 'Add CPA connection'"
      subtitle="Used to import accounts remotely from CPA on the Accounts page."
      :close-disabled="savingExternalSource === 'cpa'"
      :bordered="false"
      @close="$emit('close')"
    />
    <ModalBody class="space-y-3">
      <div class="grid gap-3 md:grid-cols-2">
        <FormField label="Name">
          <Input v-model.trim="cpaForm.name" block placeholder="Primary CPA" />
        </FormField>
        <FormField label="CPA URL">
          <Input v-model.trim="cpaForm.base_url" block placeholder="http://your-cpa-host:8317" />
        </FormField>
      </div>
      <FormField label="Admin key">
        <Input v-model="cpaForm.secret_key" type="password" block :placeholder="editingCpaPoolId ? 'Leave blank to keep the key unchanged.' : 'CPA admin key'" />
      </FormField>
    </ModalBody>
    <ModalFooter :bordered="false">
      <Button size="sm" variant="outline" :disabled="savingExternalSource === 'cpa'" @click="$emit('close')">Cancel</Button>
      <Button size="sm" variant="primary" :disabled="savingExternalSource === 'cpa'" @click="$emit('saveCpa')">
        {{ savingExternalSource === 'cpa' ? 'Saving…' : 'Save' }}
      </Button>
    </ModalFooter>
  </ModalShell>

  <ModalShell
    :open="modal === 'sub2api'"
    :aria-label="editingSub2apiId ? 'Edit Sub2API connection' : 'Add Sub2API connection'"
    :z-index="130"
    close-on-backdrop
    @close="$emit('close')"
  >
    <ModalHeader
      :title="editingSub2apiId ? 'Edit Sub2API connection' : 'Add Sub2API connection'"
      subtitle="Used to import accounts remotely from Sub2API on the Accounts page."
      :close-disabled="savingExternalSource === 'sub2api'"
      :bordered="false"
      @close="$emit('close')"
    />
    <ModalBody class="space-y-3">
      <div class="grid gap-3 md:grid-cols-2">
        <FormField label="Name">
          <Input v-model.trim="sub2apiForm.name" block placeholder="Self-hosted Sub2API" />
        </FormField>
        <FormField label="Sub2API URL">
          <Input v-model.trim="sub2apiForm.base_url" block placeholder="http://your-sub2api-host:8080" />
        </FormField>
        <FormField label="Admin email">
          <Input v-model.trim="sub2apiForm.email" block placeholder="admin@example.com" />
        </FormField>
        <FormField label="Password">
          <Input v-model="sub2apiForm.password" type="password" block :placeholder="editingSub2apiId ? 'Leave blank to keep the password unchanged.' : 'Admin password'" />
        </FormField>
        <FormField label="Admin API Key">
          <Input v-model="sub2apiForm.api_key" type="password" block :placeholder="editingSub2apiId ? 'Leave blank to keep the key unchanged.' : 'Can be used instead of the email password'" />
        </FormField>
        <FormField label="Default group ID">
          <Input v-model.trim="sub2apiForm.group_id" block placeholder="Optional" />
        </FormField>
      </div>
    </ModalBody>
    <ModalFooter :bordered="false">
      <Button size="sm" variant="outline" :disabled="savingExternalSource === 'sub2api'" @click="$emit('close')">Cancel</Button>
      <Button size="sm" variant="primary" :disabled="savingExternalSource === 'sub2api'" @click="$emit('saveSub2api')">
        {{ savingExternalSource === 'sub2api' ? 'Saving…' : 'Save' }}
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
