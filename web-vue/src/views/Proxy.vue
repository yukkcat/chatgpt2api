<template>
  <div class="space-y-6">
    <PagePanel class="space-y-5">
      <PanelHeader title="Proxy Management" align="start">
        <template #copy>
          <p class="mt-1 text-xs text-muted-foreground">
            Egress priority: account proxy > account-group proxy / proxy group > default egress. Configure the default egress with a proxy group, proxy URL, or direct connection.
          </p>
        </template>
        <template #actions>
          <Button size="sm" variant="outline" :disabled="loading" @click="loadData">
            {{ loading ? 'Refreshing...' : 'Refresh' }}
          </Button>
          <Button size="sm" variant="primary" :disabled="savingDefaultProxy || loading" @click="saveDefaultProxy">
            {{ savingDefaultProxy ? 'Saving...' : 'Save egress settings' }}
          </Button>
        </template>
      </PanelHeader>

      <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <FormSection density="roomy">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-[12rem_minmax(0,1fr)]">
            <label class="block text-xs">
              <span class="ui-field-label">Default egress mode</span>
              <GroupedSelectMenu
                :model-value="defaultProxyMode"
                :options="defaultProxyModeOptions"
                aria-label="Default egress mode"
                selected-indicator="none"
                block
                @update:model-value="setDefaultProxyMode"
              />
            </label>

            <label v-if="defaultProxyMode === 'group'" class="block text-xs">
              <span class="ui-field-label">Default egress proxy group</span>
              <GroupedSelectMenu
                :model-value="selectedDefaultProxyGroupId"
                :options="defaultProxyGroupOptions"
                :disabled="loading"
                aria-label="Default egress proxy group"
                selected-indicator="none"
                block
                @update:model-value="selectDefaultProxyGroup"
              />
            </label>

            <label v-else-if="defaultProxyMode === 'custom'" class="block text-xs">
              <span class="ui-field-label">Custom proxy URL</span>
              <Input
                :model-value="defaultCustomProxyInput"
                block
                root-class="font-mono"
                placeholder="http://127.0.0.1:7890 or socks5://127.0.0.1:7890"
                @update:model-value="setDefaultCustomProxyInput"
              />
            </label>

            <div v-else class="flex min-h-[2.5rem] items-center rounded-lg border border-dashed border-border bg-muted/20 px-3 text-xs text-muted-foreground">
              Connect directly when no account or account-group proxy is specified.
            </div>
          </div>
          <ActionRow class="mt-3" gap="tight">
            <Button size="xs" variant="outline" :disabled="testingKey === DEFAULT_TEST_KEY || !canTestDefaultProxy" @click="testDefaultProxy">
              {{ testingKey === DEFAULT_TEST_KEY ? 'Testing...' : 'Test default egress' }}
            </Button>
            <Button size="xs" variant="outline" :disabled="savingDefaultProxy || testingKey === DEFAULT_TEST_KEY" @click="setDefaultProxyDirect">
              Set to direct
            </Button>
          </ActionRow>
          <div class="mt-4 border-t border-border pt-4">
            <div class="grid grid-cols-1 gap-3 md:grid-cols-[12rem_minmax(0,1fr)]">
              <label class="block text-xs">
                <span class="ui-field-label">Fallback egress mode</span>
                <GroupedSelectMenu
                  :model-value="fallbackProxyMode"
                  :options="fallbackProxyModeOptions"
                  aria-label="Fallback egress mode"
                  selected-indicator="none"
                  block
                  @update:model-value="setFallbackProxyMode"
                />
              </label>

              <label v-if="fallbackProxyMode === 'group'" class="block text-xs">
                <span class="ui-field-label">Fallback egress proxy group</span>
                <GroupedSelectMenu
                  :model-value="selectedFallbackProxyGroupId"
                  :options="fallbackProxyGroupOptions"
                  :disabled="loading"
                  aria-label="Fallback egress proxy group"
                  selected-indicator="none"
                  block
                  @update:model-value="selectFallbackProxyGroup"
                />
              </label>

              <label v-else-if="fallbackProxyMode === 'custom'" class="block text-xs">
                <span class="ui-field-label">Fallback proxy URL</span>
                <Input
                  :model-value="fallbackCustomProxyInput"
                  block
                  root-class="font-mono"
                  placeholder="http://127.0.0.1:7890 or socks5://127.0.0.1:7890"
                  @update:model-value="setFallbackCustomProxyInput"
                />
              </label>

              <div v-else class="flex min-h-[2.5rem] items-center rounded-lg border border-dashed border-border bg-muted/20 px-3 text-xs text-muted-foreground">
                {{ fallbackProxyMode === 'direct' ? 'Retry once with a direct connection after an early connection failure.' : 'Fallback egress is disabled.' }}
              </div>
            </div>
            <p class="mt-2 text-xs text-muted-foreground">
              Image requests are retried once only for an early TLS or connection timeout before any upstream event arrives. Generation interruptions and polling timeouts do not trigger a switch.
            </p>
          </div>
        </FormSection>

        <FormSection density="roomy" surface="background">
          <p class="text-xs text-muted-foreground">Default egress test result</p>
          <div v-if="defaultTestResult" class="mt-3 space-y-1 text-xs">
            <p :class="defaultTestResult.ok ? 'text-emerald-600' : 'text-rose-600'">
              {{ defaultTestResult.ok ? 'Available' : 'Unavailable' }}
            </p>
            <p class="text-muted-foreground">HTTP {{ defaultTestResult.status || '-' }} · {{ defaultTestResult.latency_ms || 0 }}ms</p>
            <p v-if="defaultTestResult.error" class="break-all text-rose-600">{{ defaultTestResult.error }}</p>
          </div>
          <p v-else class="mt-3 text-xs text-muted-foreground">Not tested yet</p>
        </FormSection>
      </div>
    </PagePanel>

    <PagePanel class="space-y-4">
      <PanelHeader title="Proxy Groups / Multiple Egress Nodes">
        <template #copy>
          <p class="mt-1 text-xs text-muted-foreground">
            A proxy group contains multiple egress nodes. Image requests randomly select a node with available capacity and stay on it until the request ends. Requests wait when all nodes are full; they do not fall back to a direct connection.
          </p>
        </template>
        <template #actions>
          <Input
            :model-value="groupKeyword"
            block
            root-class="min-w-[12rem] md:w-80"
            placeholder="Search proxy groups / nodes / addresses"
            @update:model-value="groupKeyword = $event.trim()"
          />
          <Button size="sm" variant="primary" @click="openCreateGroupModal">Create proxy group</Button>
        </template>
      </PanelHeader>
      <TableShell
        unframed
        hover-rows
        sticky-header
        :scroll-mode="isWorkspaceLayout ? 'contained' : 'page'"
        :loading="loading && filteredGroups.length === 0"
        loading-title="Loading proxies"
        loading-description="Loading proxy groups, nodes, and health status."
        :show-empty="!loading && filteredGroups.length === 0"
        :empty-colspan="6"
        empty-title="No proxy groups"
        empty-description="Create a proxy group to assign it to an account group, an account, or the default egress."
        :scroll-class="isWorkspaceLayout ? 'max-h-[min(36rem,65dvh)]' : ''"
        table-class="min-w-[1080px] w-full table-fixed text-left text-sm"
        head-class="tracking-[0.16em]"
      >
        <template #colgroup>
          <col class="w-[20%]" />
          <col class="w-[7rem]" />
          <col class="w-[30%]" />
          <col class="w-[15%]" />
          <col class="w-[16%]" />
          <col class="w-[16rem]" />
        </template>
        <template #head>
          <tr>
            <th class="py-3 pr-4">Proxy group</th>
            <th class="py-3 pr-4">Status</th>
            <th class="py-3 pr-4">Nodes</th>
            <th class="py-3 pr-4">References</th>
            <th class="py-3 pr-4">Health</th>
            <th class="py-3 text-right">Actions</th>
          </tr>
        </template>
        <ProxyGroupRow
          v-for="group in filteredGroups"
          :key="group.id"
          :group="group"
          :testing-key="testingKey"
          :saving-group-id="savingGroupId"
          :deleting-group-id="deletingGroupId"
          :node-test-summary="nodeTestSummary"
          :node-test-class="nodeTestClass"
          @copy-reference="copyProxyGroupReference"
          @edit="openEditGroupModal"
          @action="handleProxyGroupAction"
        />
        <template #footer>
          <div class="flex justify-end pt-3">
            <ListLayoutControl v-model="listLayoutMode" />
          </div>
        </template>
      </TableShell>
    </PagePanel>

    <ModalShell
      :open="showGroupModal"
      :aria-label="editingGroupId ? 'Edit proxy group' : 'Create proxy group'"
      :z-index="120"
      :close-on-escape="!showNodeImportModal"
      scrollable
      @close="closeGroupModal"
    >
      <ModalHeader
        :title="editingGroupId ? 'Edit proxy group' : 'Create proxy group'"
        :close-disabled="savingGroupId === FORM_TEST_KEY || closingGroupModal"
        :bordered="false"
        compact
        @close="closeGroupModal"
      />

      <ModalBody class="space-y-4">
        <FormSection title="Basic information" surface="plain">
              <div class="grid grid-cols-1 gap-2.5 md:grid-cols-[minmax(0,1fr)_16rem]">
                <label class="text-xs">
                  <span class="ui-field-label">Proxy group name</span>
                  <Input
                    :model-value="groupForm.name"
                    block
                    placeholder="Hong Kong proxy pool"
                    @update:model-value="groupForm.name = $event.trim()"
                  />
                </label>
                <label class="text-xs">
                  <span class="ui-field-label">Proxy group ID</span>
                  <Input
                    :model-value="groupForm.id"
                    block
                    root-class="font-mono"
                    :disabled="Boolean(editingGroupId)"
                    @update:model-value="groupForm.id = cleanProxyGroupDraftId($event)"
                  />
                </label>
              </div>
              <div class="grid grid-cols-1 gap-2.5 md:grid-cols-[minmax(0,1fr)_auto]">
                <label class="text-xs">
                  <span class="ui-field-label">Notes</span>
                  <Input
                    :model-value="groupForm.notes"
                    block
                    placeholder="Optional"
                    @update:model-value="groupForm.notes = $event.trim()"
                  />
                </label>
                <div class="flex items-end">
                  <Checkbox v-model="groupForm.enabled">Enable proxy group</Checkbox>
                </div>
              </div>
        </FormSection>

              <div class="space-y-3">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <p class="text-xs font-medium text-foreground">Proxy nodes</p>
                  <div class="flex flex-wrap items-center gap-2">
                    <Button size="xs" variant="outline" @click="openNodeImportModal">
                      Add nodes in bulk
                    </Button>
                    <Button size="xs" variant="outline" @click="addGroupNode">Add node</Button>
                  </div>
                </div>
                <div class="space-y-3">
                  <FormSection
                    v-for="(node, index) in groupForm.nodes"
                    :key="`${node.id}-${index}`"
                    surface="muted"
                  >
                    <div class="grid grid-cols-1 gap-2 md:grid-cols-[10rem_minmax(0,1fr)_8rem_auto]">
                      <label class="text-xs">
                        <span class="ui-field-label">Name</span>
                        <Input
                          :model-value="node.name"
                          block
                          @update:model-value="node.name = $event.trim()"
                        />
                      </label>
                      <label class="text-xs">
                        <span class="ui-field-label">Proxy URL</span>
                        <Input
                          :model-value="node.url"
                          block
                          root-class="font-mono"
                          placeholder="http://user:password@host:port"
                          @update:model-value="node.url = $event.trim()"
                        />
                      </label>
                      <label class="text-xs">
                        <span class="ui-field-label">Image concurrency</span>
                        <Input
                          :model-value="String(node.image_concurrency_limit ?? 0)"
                          block
                          type="number"
                          min="0"
                          step="1"
                          placeholder="Default: 30; 0 = unlimited"
                          title="Maximum number of concurrent image requests for this node. Additional requests wait for capacity on another node in the group and never switch to a direct connection. 0 means unlimited."
                          @update:model-value="node.image_concurrency_limit = normalizeImageConcurrencyLimit($event)"
                        />
                      </label>
                      <div class="flex items-end gap-2">
                        <Checkbox v-model="node.enabled">Enabled</Checkbox>
                      </div>
                    </div>
                    <div class="mt-2 flex flex-wrap items-center justify-between gap-2">
                      <label class="min-w-[12rem] flex-1 text-xs">
                        <span class="ui-field-label">Notes</span>
                        <Input
                          :model-value="node.notes || ''"
                          block
                          placeholder="Optional"
                          @update:model-value="node.notes = $event.trim()"
                        />
                      </label>
                      <div class="flex items-end gap-2 pt-5">
                        <Button
                          size="xs"
                          variant="outline"
                          :disabled="!node.url || testingKey === `group:${editingGroupId || groupForm.id || FORM_TEST_KEY}:${node.id}`"
                          @click="testProxyGroupNode({ id: editingGroupId || groupForm.id || FORM_TEST_KEY, name: groupForm.name }, node)"
                        >
                          {{ testingKey === `group:${editingGroupId || groupForm.id || FORM_TEST_KEY}:${node.id}` ? 'Testing...' : 'Test' }}
                        </Button>
                        <Button size="xs" variant="outline" root-class="text-rose-600" @click="removeGroupNode(index)">
                          Delete
                        </Button>
                      </div>
                    </div>
                  </FormSection>
                </div>
              </div>
      </ModalBody>

      <ModalFooter :bordered="false">
        <Button size="xs" variant="outline" root-class="min-w-14 justify-center" :disabled="savingGroupId === FORM_TEST_KEY || closingGroupModal" @click="closeGroupModal">
          Cancel
        </Button>
        <Button size="xs" variant="primary" root-class="min-w-14 justify-center" :disabled="savingGroupId === FORM_TEST_KEY" @click="saveProxyGroup">
          {{ savingGroupId === FORM_TEST_KEY ? 'Saving...' : editingGroupId ? 'Update' : 'Save' }}
        </Button>
      </ModalFooter>
    </ModalShell>

    <ProxyNodeImportModal
      :open="showNodeImportModal"
      :group-name="groupForm.name || groupForm.id"
      :existing-urls="groupNodeImportExistingUrls"
      @close="closeNodeImportModal"
      @apply="applyNodeImport"
    />

    <OperationProgressDrawer
      :open="operationProgress.open"
      :title="operationProgress.title"
      :subtitle="operationProgress.subtitle"
      :total="operationProgress.total"
      :current="operationProgress.current"
      :status-label="operationProgress.statusLabel"
      :error="operationProgress.error"
      :busy="operationProgress.busy"
      :tone="operationProgress.tone"
      :events="operationProgress.events"
      @close="closeOperationProgress"
    />

  </div>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import {
  Button,
  Checkbox,
  GroupedSelectMenu,
  Input,
  TableShell,
} from 'nanocat-ui'
import ActionRow from '@/components/ai/ActionRow.vue'
import ListLayoutControl from '@/components/ai/ListLayoutControl.vue'
import FormSection from '@/components/ai/FormSection.vue'
import ModalBody from '@/components/ai/ModalBody.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import OperationProgressDrawer from '@/components/ai/OperationProgressDrawer.vue'
import PagePanel from '@/components/ai/PagePanel.vue'
import PanelHeader from '@/components/ai/PanelHeader.vue'
import { usePageVisibilityReload } from '@/composables/usePageQuery'
import { usePageRuntime } from '@/composables/usePageRuntime'
import { useListLayoutPreference } from '@/composables/useListLayoutPreference'
import {
  defaultProxyModeOptions,
  fallbackProxyModeOptions,
} from '@/views/proxy/proxyView'
import { DEFAULT_TEST_KEY, useProxyDefaultRuntime } from '@/views/proxy/proxyDefaultRuntime'
import {
  FORM_TEST_KEY,
  cleanProxyGroupDraftId,
  normalizeImageConcurrencyLimit,
  useProxyGroupRuntime,
} from '@/views/proxy/proxyGroupRuntime'
import ProxyGroupRow from '@/views/proxy/ProxyGroupRow.vue'
import ProxyNodeImportModal from '@/views/proxy/ProxyNodeImportModal.vue'

defineOptions({ name: 'Proxy' })

const { listLayoutMode, isWorkspaceLayout } = useListLayoutPreference()
const proxyGroupsRuntime = useProxyGroupRuntime()
const savingGroupId = proxyGroupsRuntime.savingGroupId
const deletingGroupId = proxyGroupsRuntime.deletingGroupId
const testingKey = proxyGroupsRuntime.testingKey
const operationProgress = proxyGroupsRuntime.operationProgress
const closeOperationProgress = proxyGroupsRuntime.closeOperationProgress
const groupKeyword = proxyGroupsRuntime.groupKeyword
const showGroupModal = proxyGroupsRuntime.showGroupModal
const showNodeImportModal = proxyGroupsRuntime.showNodeImportModal
const closingGroupModal = proxyGroupsRuntime.closingGroupModal
const editingGroupId = proxyGroupsRuntime.editingGroupId
const groups = proxyGroupsRuntime.groups
const groupForm = proxyGroupsRuntime.groupForm
const groupNodeImportExistingUrls = proxyGroupsRuntime.groupNodeImportExistingUrls
const filteredGroups = proxyGroupsRuntime.filteredGroups
const updateGroups = proxyGroupsRuntime.updateGroups
const copyProxyGroupReference = proxyGroupsRuntime.copyProxyGroupReference
const openCreateGroupModal = proxyGroupsRuntime.openCreateGroupModal
const openEditGroupModal = proxyGroupsRuntime.openEditGroupModal
const closeGroupModal = proxyGroupsRuntime.closeGroupModal
const openNodeImportModal = proxyGroupsRuntime.openNodeImportModal
const closeNodeImportModal = proxyGroupsRuntime.closeNodeImportModal
const addGroupNode = proxyGroupsRuntime.addGroupNode
const removeGroupNode = proxyGroupsRuntime.removeGroupNode
const applyNodeImport = proxyGroupsRuntime.applyNodeImport
const saveProxyGroup = proxyGroupsRuntime.saveProxyGroup
const handleProxyGroupAction = proxyGroupsRuntime.handleProxyGroupAction
const testProxyGroupNode = proxyGroupsRuntime.testProxyGroupNode
const nodeTestSummary = proxyGroupsRuntime.nodeTestSummary
const nodeTestClass = proxyGroupsRuntime.nodeTestClass
const pageRuntime = usePageRuntime('proxy')
const PROXY_DATA_REQUEST_KEY = 'proxy:data'
const proxyDefaultRuntime = useProxyDefaultRuntime({
  runtime: pageRuntime,
  requestKey: PROXY_DATA_REQUEST_KEY,
  groups,
  testingKey,
  updateGroups,
})
const loading = proxyDefaultRuntime.loading
const savingDefaultProxy = proxyDefaultRuntime.savingDefaultProxy
const defaultProxyMode = proxyDefaultRuntime.defaultProxyMode
const selectedDefaultProxyGroupId = proxyDefaultRuntime.selectedDefaultProxyGroupId
const defaultCustomProxyInput = proxyDefaultRuntime.defaultCustomProxyInput
const fallbackProxyMode = proxyDefaultRuntime.fallbackProxyMode
const selectedFallbackProxyGroupId = proxyDefaultRuntime.selectedFallbackProxyGroupId
const fallbackCustomProxyInput = proxyDefaultRuntime.fallbackCustomProxyInput
const defaultTestResult = proxyDefaultRuntime.defaultTestResult
const defaultProxyGroupOptions = proxyDefaultRuntime.defaultProxyGroupOptions
const fallbackProxyGroupOptions = proxyDefaultRuntime.fallbackProxyGroupOptions
const effectiveDefault = proxyDefaultRuntime.effectiveDefault
const canTestDefaultProxy = proxyDefaultRuntime.canTestDefaultProxy
const isDefaultProxyDirty = proxyDefaultRuntime.isDefaultProxyDirty
const setDefaultProxyMode = proxyDefaultRuntime.setDefaultProxyMode
const setFallbackProxyMode = proxyDefaultRuntime.setFallbackProxyMode
const selectDefaultProxyGroup = proxyDefaultRuntime.selectDefaultProxyGroup
const selectFallbackProxyGroup = proxyDefaultRuntime.selectFallbackProxyGroup
const setDefaultCustomProxyInput = proxyDefaultRuntime.setDefaultCustomProxyInput
const setFallbackCustomProxyInput = proxyDefaultRuntime.setFallbackCustomProxyInput
const loadData = proxyDefaultRuntime.loadData
const saveDefaultProxy = proxyDefaultRuntime.saveDefaultProxy
const setDefaultProxyDirect = proxyDefaultRuntime.setDefaultProxyDirect
const testDefaultProxy = proxyDefaultRuntime.testDefaultProxy

function deactivateProxyView() {
  proxyDefaultRuntime.invalidate()
}

function shouldSkipProxyRefresh() {
  return Boolean(
    showGroupModal.value
    || savingDefaultProxy.value
    || savingGroupId.value
    || testingKey.value
    || isDefaultProxyDirty.value,
  )
}

usePageVisibilityReload({
  runtime: pageRuntime,
  invalidate: deactivateProxyView,
  reload: loadData,
  shouldReload: () => !shouldSkipProxyRefresh(),
})

pageRuntime.onActivate(({ initial }) => {
  if (initial) {
    void loadData()
    return
  }
  if (shouldSkipProxyRefresh()) return
  void loadData()
})

pageRuntime.onDeactivate(() => {
  deactivateProxyView()
})
</script>
