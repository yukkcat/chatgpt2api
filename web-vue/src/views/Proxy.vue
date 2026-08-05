<template>
  <div class="space-y-6">
    <PagePanel class="space-y-5">
      <PanelHeader title="代理管理" align="start">
        <template #copy>
          <p class="mt-1 text-xs text-muted-foreground">
            出口优先级：账号个人代理 > 账号组代理/代理组 > 默认出口；默认出口可配置代理组、代理 URL 或直连。
          </p>
        </template>
        <template #actions>
          <Button size="sm" variant="outline" :disabled="loading" @click="loadData">
            {{ loading ? '刷新中...' : '刷新' }}
          </Button>
          <Button size="sm" variant="primary" :disabled="savingDefaultProxy || loading" @click="saveDefaultProxy">
            {{ savingDefaultProxy ? '保存中...' : '保存出口配置' }}
          </Button>
        </template>
      </PanelHeader>

      <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <FormSection density="roomy">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-[12rem_minmax(0,1fr)]">
            <label class="block text-xs">
              <span class="ui-field-label">默认出口模式</span>
              <GroupedSelectMenu
                :model-value="defaultProxyMode"
                :options="defaultProxyModeOptions"
                aria-label="默认出口模式"
                selected-indicator="none"
                block
                @update:model-value="setDefaultProxyMode"
              />
            </label>

            <label v-if="defaultProxyMode === 'group'" class="block text-xs">
              <span class="ui-field-label">默认出口代理组</span>
              <GroupedSelectMenu
                :model-value="selectedDefaultProxyGroupId"
                :options="defaultProxyGroupOptions"
                :disabled="loading"
                aria-label="默认出口代理组"
                selected-indicator="none"
                block
                @update:model-value="selectDefaultProxyGroup"
              />
            </label>

            <label v-else-if="defaultProxyMode === 'custom'" class="block text-xs">
              <span class="ui-field-label">自定义代理 URL</span>
              <Input
                :model-value="defaultCustomProxyInput"
                block
                root-class="font-mono"
                placeholder="http://127.0.0.1:7890 或 socks5://127.0.0.1:7890"
                @update:model-value="setDefaultCustomProxyInput"
              />
            </label>

            <div v-else class="flex min-h-[2.5rem] items-center rounded-lg border border-dashed border-border bg-muted/20 px-3 text-xs text-muted-foreground">
              未指定账号或账号组代理时直连。
            </div>
          </div>
          <ActionRow class="mt-3" gap="tight">
            <Button size="xs" variant="outline" :disabled="testingKey === DEFAULT_TEST_KEY || !canTestDefaultProxy" @click="testDefaultProxy">
              {{ testingKey === DEFAULT_TEST_KEY ? '测试中...' : '测试默认出口' }}
            </Button>
            <Button size="xs" variant="outline" :disabled="savingDefaultProxy || testingKey === DEFAULT_TEST_KEY" @click="setDefaultProxyDirect">
              设为直连
            </Button>
          </ActionRow>
          <div class="mt-4 border-t border-border pt-4">
            <div class="grid grid-cols-1 gap-3 md:grid-cols-[12rem_minmax(0,1fr)]">
              <label class="block text-xs">
                <span class="ui-field-label">备用出口模式</span>
                <GroupedSelectMenu
                  :model-value="fallbackProxyMode"
                  :options="fallbackProxyModeOptions"
                  aria-label="备用出口模式"
                  selected-indicator="none"
                  block
                  @update:model-value="setFallbackProxyMode"
                />
              </label>

              <label v-if="fallbackProxyMode === 'group'" class="block text-xs">
                <span class="ui-field-label">备用出口代理组</span>
                <GroupedSelectMenu
                  :model-value="selectedFallbackProxyGroupId"
                  :options="fallbackProxyGroupOptions"
                  :disabled="loading"
                  aria-label="备用出口代理组"
                  selected-indicator="none"
                  block
                  @update:model-value="selectFallbackProxyGroup"
                />
              </label>

              <label v-else-if="fallbackProxyMode === 'custom'" class="block text-xs">
                <span class="ui-field-label">备用代理 URL</span>
                <Input
                  :model-value="fallbackCustomProxyInput"
                  block
                  root-class="font-mono"
                  placeholder="http://127.0.0.1:7890 或 socks5://127.0.0.1:7890"
                  @update:model-value="setFallbackCustomProxyInput"
                />
              </label>

              <div v-else class="flex min-h-[2.5rem] items-center rounded-lg border border-dashed border-border bg-muted/20 px-3 text-xs text-muted-foreground">
                {{ fallbackProxyMode === 'direct' ? '早期连接失败时重试直连一次。' : '未启用备用出口。' }}
              </div>
            </div>
            <p class="mt-2 text-xs text-muted-foreground">
              仅图片请求在早期 TLS / 连接超时且尚未收到上游事件时重试一次；生成中断和轮询超时不会切换。
            </p>
          </div>
        </FormSection>

        <FormSection density="roomy" surface="background">
          <p class="text-xs text-muted-foreground">默认出口测试结果</p>
          <div v-if="defaultTestResult" class="mt-3 space-y-1 text-xs">
            <p :class="defaultTestResult.ok ? 'text-emerald-600' : 'text-rose-600'">
              {{ defaultTestResult.ok ? '可用' : '不可用' }}
            </p>
            <p class="text-muted-foreground">HTTP {{ defaultTestResult.status || '-' }} · {{ defaultTestResult.latency_ms || 0 }}ms</p>
            <p v-if="defaultTestResult.error" class="break-all text-rose-600">{{ defaultTestResult.error }}</p>
          </div>
          <p v-else class="mt-3 text-xs text-muted-foreground">尚未测试</p>
        </FormSection>
      </div>
    </PagePanel>

    <PagePanel class="space-y-4">
      <PanelHeader title="代理组 / 多出口">
        <template #copy>
          <p class="mt-1 text-xs text-muted-foreground">
            一个代理组就是一组多出口节点；图片请求会从未满的节点里随机选择一个，请求结束前固定该出口，出口满了会等待，不会自动绕到直连。
          </p>
        </template>
        <template #actions>
          <Input
            :model-value="groupKeyword"
            block
            root-class="min-w-[12rem] md:w-80"
            placeholder="搜索代理组 / 节点 / 地址"
            @update:model-value="groupKeyword = $event.trim()"
          />
          <Button size="sm" variant="primary" @click="openCreateGroupModal">新建代理组</Button>
        </template>
      </PanelHeader>
      <TableShell
        unframed
        hover-rows
        sticky-header
        :scroll-mode="isWorkspaceLayout ? 'contained' : 'page'"
        :loading="loading && filteredGroups.length === 0"
        loading-title="正在加载代理"
        loading-description="读取代理组、节点和健康状态。"
        :show-empty="!loading && filteredGroups.length === 0"
        :empty-colspan="6"
        empty-title="暂无代理组"
        empty-description="新建代理组后，可绑定账号组、账号或默认出口使用。"
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
            <th class="py-3 pr-4">代理组</th>
            <th class="py-3 pr-4">状态</th>
            <th class="py-3 pr-4">节点</th>
            <th class="py-3 pr-4">引用</th>
            <th class="py-3 pr-4">健康</th>
            <th class="py-3 text-right">操作</th>
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
      :aria-label="editingGroupId ? '编辑代理组' : '新建代理组'"
      max-width="56rem"
      :z-index="120"
      :close-on-escape="!showNodeImportModal"
      scrollable
      @close="closeGroupModal"
    >
      <ModalHeader
        :title="editingGroupId ? '编辑代理组' : '新建代理组'"
        :close-disabled="savingGroupId === FORM_TEST_KEY || closingGroupModal"
        :bordered="false"
        compact
        @close="closeGroupModal"
      />

      <ModalBody class="space-y-4">
        <FormSection title="基础信息" surface="plain">
              <div class="grid grid-cols-1 gap-2.5 md:grid-cols-[minmax(0,1fr)_16rem]">
                <label class="text-xs">
                  <span class="ui-field-label">代理组名称</span>
                  <Input
                    :model-value="groupForm.name"
                    block
                    placeholder="香港代理池"
                    @update:model-value="groupForm.name = $event.trim()"
                  />
                </label>
                <label class="text-xs">
                  <span class="ui-field-label">代理组 ID</span>
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
                  <span class="ui-field-label">备注</span>
                  <Input
                    :model-value="groupForm.notes"
                    block
                    placeholder="可选"
                    @update:model-value="groupForm.notes = $event.trim()"
                  />
                </label>
                <div class="flex items-end">
                  <Checkbox v-model="groupForm.enabled">启用代理组</Checkbox>
                </div>
              </div>
        </FormSection>

              <div class="space-y-3">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <p class="text-xs font-medium text-foreground">代理节点</p>
                  <div class="flex flex-wrap items-center gap-2">
                    <Button size="xs" variant="outline" @click="openNodeImportModal">
                      批量添加节点
                    </Button>
                    <Button size="xs" variant="outline" @click="addGroupNode">添加节点</Button>
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
                        <span class="ui-field-label">名称</span>
                        <Input
                          :model-value="node.name"
                          block
                          @update:model-value="node.name = $event.trim()"
                        />
                      </label>
                      <label class="text-xs">
                        <span class="ui-field-label">代理 URL</span>
                        <Input
                          :model-value="node.url"
                          block
                          root-class="font-mono"
                          placeholder="http://user:password@host:port"
                          @update:model-value="node.url = $event.trim()"
                        />
                      </label>
                      <label class="text-xs">
                        <span class="ui-field-label">图片并发</span>
                        <Input
                          :model-value="String(node.image_concurrency_limit ?? 0)"
                          block
                          type="number"
                          min="0"
                          step="1"
                          placeholder="默认 30，0 不限"
                          title="限制该节点同时处理的图片请求数；超出后等待同组节点空位，不会改走直连。0 表示不限制。"
                          @update:model-value="node.image_concurrency_limit = normalizeImageConcurrencyLimit($event)"
                        />
                      </label>
                      <div class="flex items-end gap-2">
                        <Checkbox v-model="node.enabled">启用</Checkbox>
                      </div>
                    </div>
                    <div class="mt-2 flex flex-wrap items-center justify-between gap-2">
                      <label class="min-w-[12rem] flex-1 text-xs">
                        <span class="ui-field-label">备注</span>
                        <Input
                          :model-value="node.notes || ''"
                          block
                          placeholder="可选"
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
                          {{ testingKey === `group:${editingGroupId || groupForm.id || FORM_TEST_KEY}:${node.id}` ? '检测中...' : '检测' }}
                        </Button>
                        <Button size="xs" variant="outline" root-class="text-rose-600" @click="removeGroupNode(index)">
                          删除
                        </Button>
                      </div>
                    </div>
                  </FormSection>
                </div>
              </div>
      </ModalBody>

      <ModalFooter :bordered="false">
        <Button size="xs" variant="outline" root-class="min-w-14 justify-center" :disabled="savingGroupId === FORM_TEST_KEY || closingGroupModal" @click="closeGroupModal">
          取消
        </Button>
        <Button size="xs" variant="primary" root-class="min-w-14 justify-center" :disabled="savingGroupId === FORM_TEST_KEY" @click="saveProxyGroup">
          {{ savingGroupId === FORM_TEST_KEY ? '保存中...' : editingGroupId ? '更新' : '保存' }}
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
