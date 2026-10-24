<template>
  <ModalShell
    :open="modal === 'create'"
    aria-label="Create user key"
    :z-index="130"
    close-on-backdrop
    @close="$emit('close')"
  >
    <ModalHeader
      title="Create user key"
      subtitle="The name is for reference. The raw key will be shown only once after creation."
      :close-disabled="busy === 'create'"
      :bordered="false"
      @close="$emit('close')"
    />
    <ModalBody class="space-y-3">
      <FormField label="Name">
        <Input v-model.trim="form.name" block placeholder="e.g. Design account" />
      </FormField>
    </ModalBody>
    <ModalFooter :bordered="false">
      <Button size="sm" variant="outline" :disabled="busy === 'create'" @click="$emit('close')">Cancel</Button>
      <Button size="sm" variant="primary" :disabled="busy === 'create'" @click="$emit('create')">
        {{ busy === 'create' ? 'Creating...' : 'Create' }}
      </Button>
    </ModalFooter>
  </ModalShell>

  <ModalShell
    :open="modal === 'edit'"
    aria-label="Edit user key"
    :z-index="130"
    close-on-backdrop
    @close="$emit('close')"
  >
    <ModalHeader
      title="Edit user key"
      subtitle="You can change the label. Setting a new dedicated key will invalidate the old key."
      :close-disabled="isEditBusy"
      :bordered="false"
      @close="$emit('close')"
    />
    <ModalBody class="space-y-3">
      <FormField label="Name">
        <Input v-model.trim="form.name" block placeholder="e.g. Design account" />
      </FormField>
      <FormField label="New dedicated key (optional)">
        <Input v-model.trim="form.key" block root-class="font-mono" placeholder="Leave blank to keep the current key" />
      </FormField>
    </ModalBody>
    <ModalFooter :bordered="false">
      <Button size="sm" variant="outline" :disabled="isEditBusy" @click="$emit('close')">Cancel</Button>
      <Button size="sm" variant="primary" :disabled="isEditBusy" @click="$emit('update')">
        {{ isEditBusy ? 'Saving...' : 'Save' }}
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
