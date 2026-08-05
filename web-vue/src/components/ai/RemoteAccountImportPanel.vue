<template>
  <section class="space-y-3">
    <div v-if="showModeSwitch" class="flex flex-wrap gap-2">
      <Button
        v-for="option in modeOptions"
        :key="option.value"
        size="xs"
        :variant="activeMode === option.value ? 'primary' : 'outline'"
        :disabled="busy"
        @click="setMode(option.value)"
      >
        {{ option.label }}
      </Button>
    </div>

    <ImportModePanel :title="panelTitle" :description="panelDescription">
      <div
        class="mt-3 grid gap-2"
        :class="activeMode === 'sub2api'
          ? 'md:grid-cols-[minmax(0,1fr)_minmax(12rem,16rem)_auto_auto]'
          : 'md:grid-cols-[minmax(0,1fr)_auto_auto]'"
      >
        <GroupedSelectMenu
          v-if="activeMode === 'cpa'"
          :model-value="selectedCPAPoolId"
          :options="cpaPoolOptions"
          selected-indicator="none"
          aria-label="CPA 服务器"
          block
          :disabled="busy"
          @update:model-value="setCPAPool"
        />
        <template v-else>
          <GroupedSelectMenu
            :model-value="selectedSub2APIServerId"
            :options="sub2apiServerOptions"
            selected-indicator="none"
            aria-label="Sub2API 服务器"
            block
            :disabled="busy"
            @update:model-value="setSub2APIServer"
          />
          <GroupedSelectMenu
            :model-value="selectedSub2APIGroupId"
            :options="sub2apiGroupOptions"
            selected-indicator="none"
            aria-label="Sub2API 分组"
            block
            :disabled="busy || !selectedSub2APIServerId"
            @update:model-value="setSub2APIGroup"
          />
        </template>

        <Button size="xs" variant="outline" :disabled="busy" @click="refreshSources(false)">
          {{ busy ? '刷新中...' : '刷新来源' }}
        </Button>
        <Button size="xs" variant="outline" :disabled="busy || !canLoadItems" @click="loadCurrentItems">
          {{ activeMode === 'cpa' ? '加载文件' : '加载账号' }}
        </Button>
      </div>
    </ImportModePanel>

    <div
      v-if="itemCount > 0"
      class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2"
    >
      <p class="text-xs text-muted-foreground">
        {{ loadedSummaryText }}<span v-if="duplicateCount">，已过滤/去重 {{ duplicateCount }} 个</span>
      </p>
      <div class="flex flex-wrap items-center gap-2">
        <label
          v-if="activeMode === 'sub2api'"
          class="flex items-center gap-1.5 text-xs text-muted-foreground"
        >
          <Checkbox
            :model-value="importSub2APIByGroups"
            :disabled="busy"
            @update:model-value="setImportSub2APIByGroups"
          />
          <span>按远端分组导入</span>
        </label>
        <Button size="xs" variant="outline" :disabled="busy || allSelected" @click="selectAllItems">
          {{ activeMode === 'sub2api' ? '全选账号' : '全选' }}
        </Button>
        <Button size="xs" variant="outline" :disabled="busy || selectedCount === 0" @click="clearSelection">清空</Button>
      </div>
    </div>

    <SelectableListPanel :has-items="itemCount > 0" :empty-text="emptyText" density="compact">
      <template v-if="activeMode === 'cpa'">
        <label
          v-for="file in remoteCPAFiles"
          :key="file.name"
          v-memo="[cpaFileRowSignature(file, selectedCPAFileNameSet.has(file.name), busy)]"
          class="selectable-list-panel-row"
        >
          <span class="min-w-0">
            <span class="block truncate text-sm text-foreground">{{ file.email || file.name }}</span>
            <span class="block truncate text-xs text-muted-foreground">{{ file.name }}</span>
          </span>
          <Checkbox
            :model-value="selectedCPAFileNameSet.has(file.name)"
            :disabled="busy"
            @update:model-value="(checked) => toggleCPAFile(file.name, checked)"
          />
        </label>
      </template>

      <template v-else>
        <div class="remote-account-groups">
          <section
            v-for="group in sub2apiAccountGroups"
            :key="group.key"
            class="remote-account-group"
          >
            <div class="remote-account-group__header">
              <button
                type="button"
                class="remote-account-group__toggle"
                :aria-expanded="!isSub2APIGroupCollapsed(group.key)"
                @click="toggleSub2APIGroupCollapsed(group.key)"
              >
                <Icon
                  :icon="isSub2APIGroupCollapsed(group.key) ? 'lucide:chevron-right' : 'lucide:chevron-down'"
                  class="h-3.5 w-3.5 shrink-0"
                />
                <span class="truncate">{{ group.name }}</span>
                <span class="shrink-0 text-muted-foreground">
                  {{ sub2APIGroupSelectedCount(group) }}/{{ group.accounts.length }}
                </span>
              </button>
              <div class="remote-account-group__actions">
                <Button
                  size="xs"
                  variant="outline"
                  :disabled="busy || isSub2APIGroupAllSelected(group)"
                  @click="selectSub2APIGroup(group)"
                >
                  全选本组
                </Button>
                <Button
                  size="xs"
                  variant="outline"
                  :disabled="busy || sub2APIGroupSelectedCount(group) === 0"
                  @click="clearSub2APIGroup(group)"
                >
                  清空本组
                </Button>
              </div>
            </div>
            <div v-if="!isSub2APIGroupCollapsed(group.key)" class="remote-account-group__items">
              <label
                v-for="account in group.accounts"
                :key="account.id"
                v-memo="[sub2APIAccountRowSignature(account, selectedSub2APIAccountIdSet.has(account.id), busy)]"
                class="selectable-list-panel-row"
              >
                <span class="min-w-0">
                  <span class="block truncate text-sm text-foreground">{{ account.email || account.name || account.id }}</span>
                  <span class="block truncate text-xs text-muted-foreground">
                    {{ account.plan_type || '未知' }} · {{ account.status || '-' }} · {{ account.has_access_token ? '有 access token' : '需导出 token' }}
                  </span>
                </span>
                <Checkbox
                  :model-value="selectedSub2APIAccountIdSet.has(account.id)"
                  :disabled="busy"
                  @update:model-value="(checked) => toggleSub2APIAccount(account.id, checked)"
                />
              </label>
            </div>
          </section>
        </div>
      </template>
    </SelectableListPanel>

    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-xs text-muted-foreground">{{ importStatusText }}</p>
      <Button size="xs" variant="primary" :disabled="busy || selectedCount === 0" @click="startImport">
        {{ busy ? '处理中...' : '导入选中' }}
      </Button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Button, Checkbox } from 'nanocat-ui'
import { Icon } from '@iconify/vue'
import { accountImportsApi } from '@/api/accountImports'
import type {
  CPAImportJob,
  CPAPool,
  CPARemoteFile,
  RemoteAccountImportMode,
  RemoteAccountImportStarted,
  Sub2APIImportGroupBinding,
  Sub2APIRemoteAccount,
  Sub2APIRemoteGroup,
  Sub2APIServer,
} from '@/api/accountImports'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import { GroupedSelectMenu } from 'nanocat-ui'
import ImportModePanel from './ImportModePanel.vue'
import SelectableListPanel from './SelectableListPanel.vue'

type Sub2APIAccountGroup = {
  key: string
  remoteGroupId: string
  name: string
  accounts: Sub2APIRemoteAccount[]
}
type RemoteImportSource = {
  id: string
  import_job?: CPAImportJob | null
}

const DEFAULT_GROUP_VALUE = '__default__'
const UNGROUPED_SUB2API_GROUP_KEY = '__ungrouped__'
const UNGROUPED_SUB2API_GROUP_NAME = '未分组账号'

const props = withDefaults(defineProps<{
  mode: RemoteAccountImportMode
  cpaPoolId?: string
  sub2apiServerId?: string
  sub2apiGroupId?: string
  showModeSwitch?: boolean
  externalTracking?: boolean
}>(), {
  cpaPoolId: '',
  sub2apiServerId: '',
  sub2apiGroupId: undefined,
  showModeSwitch: false,
  externalTracking: false,
})

const emit = defineEmits<{
  imported: []
  'busy-change': [value: boolean]
  started: [value: RemoteAccountImportStarted]
  progress: [value: {
    title: string
    total: number
    job?: CPAImportJob | null
    error?: string
  }]
}>()

const toast = useToast()
const confirmDialog = useConfirmDialog()
const activeMode = ref<RemoteAccountImportMode>(props.mode)
const busy = ref(false)
const cpaPools = ref<CPAPool[]>([])
const remoteCPAFiles = ref<CPARemoteFile[]>([])
const selectedCPAPoolId = ref('')
const selectedCPAFileNames = ref<string[]>([])
const remoteCPADuplicateCount = ref(0)
const sub2apiServers = ref<Sub2APIServer[]>([])
const sub2apiGroups = ref<Record<string, Sub2APIRemoteGroup[]>>({})
const sub2apiAccounts = ref<Sub2APIRemoteAccount[]>([])
const selectedSub2APIServerId = ref('')
const selectedSub2APIGroupId = ref('')
const selectedSub2APIAccountIds = ref<string[]>([])
const sub2apiDuplicateCount = ref(0)
const collapsedSub2APIGroups = ref<Record<string, boolean>>({})
const importSub2APIByGroups = ref(true)
const importJob = ref<CPAImportJob | null>(null)
const emittedImportJobIds = new Set<string>()

const modeOptions = [
  { label: 'CPA', value: 'cpa' },
  { label: 'Sub2API', value: 'sub2api' },
] as const

const panelTitle = computed(() => (
  activeMode.value === 'cpa' ? '从远程 CPA 导入' : '从 Sub2API 导入'
))

const panelDescription = computed(() => (
  activeMode.value === 'cpa'
    ? '读取已保存 CPA 连接里的账号文件，勾选后导入本地号池。'
    : '读取已保存 Sub2API 连接里的账号；选择“全部账号”时会按远端分组折叠加载，导入时可自动创建或复用同名本地分组。'
))

const cpaPoolOptions = computed(() => [
  { label: '选择 CPA 连接', value: '' },
  ...cpaPools.value.map((pool) => ({ label: pool.name || pool.base_url || pool.id, value: pool.id })),
])

const sub2apiServerOptions = computed(() => [
  { label: '选择 Sub2API 连接', value: '' },
  ...sub2apiServers.value.map((server) => ({ label: server.name || server.base_url || server.id, value: server.id })),
])

const selectedSub2APIServer = computed(() => (
  sub2apiServers.value.find((server) => server.id === selectedSub2APIServerId.value) || null
))

const sub2apiGroupOptions = computed(() => {
  const server = selectedSub2APIServer.value
  const groups = sub2apiGroups.value[selectedSub2APIServerId.value] || []
  const options = [
    { label: '全部账号（按远端分组）', value: '' },
    ...(server?.group_id ? [{ label: '默认分组', value: DEFAULT_GROUP_VALUE }] : []),
    ...groups.map((group) => ({
      label: `${group.name || group.id} · ${group.active_account_count}/${group.account_count}`,
      value: group.id,
    })),
  ]
  const selected = selectedSub2APIGroupId.value
  if (selected && selected !== DEFAULT_GROUP_VALUE && !options.some((option) => option.value === selected)) {
    options.push({ label: `当前分组 · ${selected}`, value: selected })
  }
  return options
})

const sub2apiGroupNameById = computed(() => {
  const map = new Map<string, string>()
  for (const group of sub2apiGroups.value[selectedSub2APIServerId.value] || []) {
    const id = String(group.id || '').trim()
    if (id) map.set(id, String(group.name || id).trim())
  }
  return map
})

const sub2apiGroupOrderById = computed(() => {
  const map = new Map<string, number>()
  for (const [index, group] of (sub2apiGroups.value[selectedSub2APIServerId.value] || []).entries()) {
    const id = String(group.id || '').trim()
    if (id) map.set(id, index)
  }
  return map
})

const sub2apiAccountGroups = computed<Sub2APIAccountGroup[]>(() => {
  const groups = new Map<string, Sub2APIAccountGroup>()
  for (const account of sub2apiAccounts.value) {
    const remoteGroupId = String(account.remote_group_id || '').trim()
    const remoteGroupName = String(account.remote_group_name || '').trim()
    const name = remoteGroupName || (remoteGroupId ? sub2apiGroupNameById.value.get(remoteGroupId) || remoteGroupId : UNGROUPED_SUB2API_GROUP_NAME)
    const key = remoteGroupId || (remoteGroupName ? `name:${remoteGroupName}` : UNGROUPED_SUB2API_GROUP_KEY)
    const current = groups.get(key)
    if (current) {
      current.accounts.push(account)
    } else {
      groups.set(key, {
        key,
        remoteGroupId,
        name,
        accounts: [account],
      })
    }
  }
  const order = sub2apiGroupOrderById.value
  return Array.from(groups.values()).sort((left, right) => {
    const leftOrder = left.remoteGroupId ? order.get(left.remoteGroupId) ?? 9999 : 10000
    const rightOrder = right.remoteGroupId ? order.get(right.remoteGroupId) ?? 9999 : 10000
    if (leftOrder !== rightOrder) return leftOrder - rightOrder
    return left.name.localeCompare(right.name)
  })
})

const selectedCPAFileNameSet = computed(() => new Set(selectedCPAFileNames.value))
const selectedSub2APIAccountIdSet = computed(() => new Set(selectedSub2APIAccountIds.value))
const sub2APIGroupSelectedCountMap = computed(() => {
  const selected = selectedSub2APIAccountIdSet.value
  const counts = new Map<string, number>()
  for (const group of sub2apiAccountGroups.value) {
    let count = 0
    for (const account of group.accounts) {
      if (selected.has(account.id)) count += 1
    }
    counts.set(group.key, count)
  }
  return counts
})

const canLoadItems = computed(() => (
  activeMode.value === 'cpa' ? Boolean(selectedCPAPoolId.value) : Boolean(selectedSub2APIServerId.value)
))

const itemCount = computed(() => (
  activeMode.value === 'cpa' ? remoteCPAFiles.value.length : sub2apiAccounts.value.length
))

const selectedCount = computed(() => (
  activeMode.value === 'cpa' ? selectedCPAFileNames.value.length : selectedSub2APIAccountIds.value.length
))

const duplicateCount = computed(() => (
  activeMode.value === 'cpa' ? remoteCPADuplicateCount.value : sub2apiDuplicateCount.value
))

const loadedSummaryText = computed(() => {
  if (activeMode.value === 'cpa') {
    return `已加载 ${itemCount.value} 个文件，已选择 ${selectedCount.value} 个`
  }
  return `已加载 ${itemCount.value} 个账号，${sub2apiAccountGroups.value.length} 个分组，已选择 ${selectedCount.value} 个`
})

const allSelected = computed(() => (
  itemCount.value > 0
  && (
    activeMode.value === 'cpa'
      ? remoteCPAFiles.value.every((file) => selectedCPAFileNameSet.value.has(file.name))
      : sub2apiAccounts.value.every((account) => selectedSub2APIAccountIdSet.value.has(account.id))
  )
))

const emptyText = computed(() => {
  if (busy.value) return '正在加载...'
  if (!canLoadItems.value) return activeMode.value === 'cpa' ? '请选择 CPA 连接' : '请选择 Sub2API 连接'
  return activeMode.value === 'cpa' ? '暂无可导入文件' : '暂无可导入账号'
})

const importStatusText = computed(() => {
  const job = importJob.value
  if (!job) return '未开始导入'
  return job.result_message || job.status_label
})

watch(busy, (value) => emit('busy-change', value))

watch(() => props.mode, (mode) => {
  if (activeMode.value === mode) return
  activeMode.value = mode
  resetItems()
  applyInitialSelection()
  void refreshSources(hasFixedSource())
})

watch(() => [props.cpaPoolId, props.sub2apiServerId, props.sub2apiGroupId], () => {
  applyInitialSelection()
  resetItems()
  void refreshSources(hasFixedSource())
})

onMounted(() => {
  applyInitialSelection()
  void refreshSources(hasFixedSource())
})

function uniqueRemoteCPAFiles(files: CPARemoteFile[]) {
  const seen = new Set<string>()
  const items: CPARemoteFile[] = []
  for (const file of files) {
    const name = String(file?.name || '').trim()
    if (!name || seen.has(name)) continue
    seen.add(name)
    items.push({ ...file, name })
  }
  return { items, duplicates: Math.max(0, files.length - items.length) }
}

function uniqueSub2APIAccounts(accounts: Sub2APIRemoteAccount[]) {
  const seen = new Set<string>()
  const items: Sub2APIRemoteAccount[] = []
  for (const account of accounts) {
    const id = String(account?.id || '').trim()
    if (!id || seen.has(id)) continue
    seen.add(id)
    items.push({ ...account, id })
  }
  return { items, duplicates: Math.max(0, accounts.length - items.length) }
}

function hasFixedSource() {
  return activeMode.value === 'cpa' ? Boolean(props.cpaPoolId) : Boolean(props.sub2apiServerId)
}

function applyInitialSelection() {
  if (props.cpaPoolId) selectedCPAPoolId.value = props.cpaPoolId
  if (props.sub2apiServerId) selectedSub2APIServerId.value = props.sub2apiServerId
  selectedSub2APIGroupId.value = props.sub2apiGroupId === undefined ? '' : props.sub2apiGroupId
}

function resetItems() {
  remoteCPAFiles.value = []
  selectedCPAFileNames.value = []
  remoteCPADuplicateCount.value = 0
  sub2apiAccounts.value = []
  selectedSub2APIAccountIds.value = []
  sub2apiDuplicateCount.value = 0
  collapsedSub2APIGroups.value = {}
  importJob.value = null
}

function setMode(mode: RemoteAccountImportMode) {
  if (busy.value || activeMode.value === mode) return
  activeMode.value = mode
  resetItems()
  applyInitialSelection()
  void refreshSources(hasFixedSource())
}

function setCPAPool(value: string | string[]) {
  selectedCPAPoolId.value = Array.isArray(value) ? String(value[0] || '') : String(value || '')
  remoteCPAFiles.value = []
  selectedCPAFileNames.value = []
  remoteCPADuplicateCount.value = 0
  importJob.value = null
}

function setSub2APIServer(value: string | string[]) {
  const next = Array.isArray(value) ? String(value[0] || '') : String(value || '')
  selectedSub2APIServerId.value = next
  selectedSub2APIGroupId.value = props.sub2apiServerId === next && props.sub2apiGroupId !== undefined
    ? props.sub2apiGroupId
    : ''
  sub2apiAccounts.value = []
  selectedSub2APIAccountIds.value = []
  sub2apiDuplicateCount.value = 0
  collapsedSub2APIGroups.value = {}
  importJob.value = null
  if (next) void loadSub2APIGroups(next)
}

function setSub2APIGroup(value: string | string[]) {
  selectedSub2APIGroupId.value = Array.isArray(value) ? String(value[0] || '') : String(value || '')
  sub2apiAccounts.value = []
  selectedSub2APIAccountIds.value = []
  sub2apiDuplicateCount.value = 0
  collapsedSub2APIGroups.value = {}
  importJob.value = null
}

async function runBusy(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  try {
    await action()
  } finally {
    busy.value = false
  }
}

async function refreshSources(autoLoadItems = false) {
  await runBusy(async () => {
    if (activeMode.value === 'cpa') {
      await loadCPAPools()
      if (autoLoadItems && selectedCPAPoolId.value) await loadCPAFiles()
      return
    }
    await loadSub2APIServers()
    if (selectedSub2APIServerId.value) await loadSub2APIGroups(selectedSub2APIServerId.value)
    if (autoLoadItems && selectedSub2APIServerId.value) await loadSub2APIAccounts()
  })
}

async function loadCurrentItems() {
  await runBusy(async () => {
    if (activeMode.value === 'cpa') await loadCPAFiles()
    else await loadSub2APIAccounts()
  })
}

async function loadCPAPools() {
  try {
    const response = await accountImportsApi.listCPAPools()
    cpaPools.value = Array.isArray(response.pools) ? response.pools : []
    if (!selectedCPAPoolId.value && cpaPools.value.length > 0) selectedCPAPoolId.value = cpaPools.value[0].id
    emitRecoverableImportJobs('cpa', cpaPools.value, selectedCPAPoolId.value)
  } catch (error: any) {
    cpaPools.value = []
    toast.error(error.message || '加载 CPA 连接失败')
  }
}

async function loadCPAFiles() {
  const poolId = selectedCPAPoolId.value
  if (!poolId) {
    toast.warning('请先选择 CPA 连接')
    return
  }
  try {
    const response = await accountImportsApi.listCPAPoolFiles(poolId)
    const normalized = uniqueRemoteCPAFiles(response.files || [])
    remoteCPAFiles.value = normalized.items
    remoteCPADuplicateCount.value = normalized.duplicates
    selectedCPAFileNames.value = []
  } catch (error: any) {
    toast.error(error.message || '加载 CPA 文件失败')
  }
}

async function loadSub2APIServers() {
  try {
    const response = await accountImportsApi.listSub2APIServers()
    sub2apiServers.value = Array.isArray(response.servers) ? response.servers : []
    if (!selectedSub2APIServerId.value && sub2apiServers.value.length > 0) {
      selectedSub2APIServerId.value = sub2apiServers.value[0].id
    }
    emitRecoverableImportJobs('sub2api', sub2apiServers.value, selectedSub2APIServerId.value)
  } catch (error: any) {
    sub2apiServers.value = []
    toast.error(error.message || '加载 Sub2API 连接失败')
  }
}

async function loadSub2APIGroups(serverId: string) {
  try {
    const response = await accountImportsApi.listSub2APIServerGroups(serverId)
    sub2apiGroups.value = {
      ...sub2apiGroups.value,
      [serverId]: Array.isArray(response.groups) ? response.groups : [],
    }
  } catch (error: any) {
    sub2apiGroups.value = { ...sub2apiGroups.value, [serverId]: [] }
    toast.error(error.message || '加载 Sub2API 分组失败')
  }
}

function selectedSub2APIGroupParam() {
  return selectedSub2APIGroupId.value === DEFAULT_GROUP_VALUE ? undefined : selectedSub2APIGroupId.value
}

function selectedSub2APIGroupHint() {
  const selected = selectedSub2APIGroupId.value
  const server = selectedSub2APIServer.value
  const groupId = selected === DEFAULT_GROUP_VALUE ? String(server?.group_id || '').trim() : String(selected || '').trim()
  if (!groupId) return null
  return {
    id: groupId,
    name: sub2apiGroupNameById.value.get(groupId) || (selected === DEFAULT_GROUP_VALUE ? '默认分组' : groupId),
  }
}

function withSub2APIGroupHint(accounts: Sub2APIRemoteAccount[]) {
  const hint = selectedSub2APIGroupHint()
  return accounts.map((account) => ({
    ...account,
    remote_group_id: String(account.remote_group_id || hint?.id || '').trim(),
    remote_group_name: String(account.remote_group_name || hint?.name || '').trim(),
  }))
}

function shouldLoadAllSub2APIAccountsByGroups() {
  return selectedSub2APIGroupId.value === ''
}

function collapseAllSub2APIGroups() {
  collapsedSub2APIGroups.value = Object.fromEntries(
    sub2apiAccountGroups.value.map((group) => [group.key, true]),
  )
}

async function loadSub2APIAccountsByRemoteGroups(serverId: string) {
  const groups = sub2apiGroups.value[serverId] || []
  if (!groups.length || !shouldLoadAllSub2APIAccountsByGroups()) return null

  const results = await Promise.allSettled(
    groups.map(async (group) => {
      const response = await accountImportsApi.listSub2APIServerAccounts(serverId, group.id)
      return (response.accounts || []).map((account) => ({
        ...account,
        remote_group_id: String(account.remote_group_id || group.id || '').trim(),
        remote_group_name: String(account.remote_group_name || group.name || group.id || '').trim(),
      }))
    }),
  )
  const groupedAccounts = results.flatMap((result) => (result.status === 'fulfilled' ? result.value : []))
  if (!groupedAccounts.length) return null

  try {
    const response = await accountImportsApi.listSub2APIServerAccounts(serverId, '')
    return [...groupedAccounts, ...(response.accounts || [])]
  } catch {
    return groupedAccounts
  }
}

async function loadSub2APIAccounts() {
  const serverId = selectedSub2APIServerId.value
  if (!serverId) {
    toast.warning('请先选择 Sub2API 连接')
    return
  }
  try {
    if (
      shouldLoadAllSub2APIAccountsByGroups()
      && !Object.prototype.hasOwnProperty.call(sub2apiGroups.value, serverId)
    ) {
      await loadSub2APIGroups(serverId)
    }
    const groupedAccounts = await loadSub2APIAccountsByRemoteGroups(serverId)
    const accounts = groupedAccounts || (await accountImportsApi.listSub2APIServerAccounts(serverId, selectedSub2APIGroupParam())).accounts || []
    const normalized = uniqueSub2APIAccounts(accounts)
    sub2apiAccounts.value = withSub2APIGroupHint(normalized.items)
    sub2apiDuplicateCount.value = normalized.duplicates
    selectedSub2APIAccountIds.value = []
    collapseAllSub2APIGroups()
  } catch (error: any) {
    toast.error(error.message || '加载 Sub2API 账号失败')
  }
}

function toggleCPAFile(name: string, checked?: boolean) {
  const next = new Set(selectedCPAFileNames.value)
  const shouldSelect = typeof checked === 'boolean' ? checked : !next.has(name)
  if (shouldSelect) next.add(name)
  else next.delete(name)
  selectedCPAFileNames.value = Array.from(next)
}

function toggleSub2APIAccount(accountId: string, checked?: boolean) {
  const next = new Set(selectedSub2APIAccountIds.value)
  const shouldSelect = typeof checked === 'boolean' ? checked : !next.has(accountId)
  if (shouldSelect) next.add(accountId)
  else next.delete(accountId)
  selectedSub2APIAccountIds.value = Array.from(next)
}

function sub2APIGroupSelectedCount(group: Sub2APIAccountGroup) {
  return sub2APIGroupSelectedCountMap.value.get(group.key) || 0
}

function isSub2APIGroupAllSelected(group: Sub2APIAccountGroup) {
  return group.accounts.length > 0 && sub2APIGroupSelectedCount(group) === group.accounts.length
}

function cpaFileRowSignature(file: CPARemoteFile, selected: boolean, disabled: boolean) {
  return [
    file.name,
    boundedSignatureText(file.email || file.name),
    selected ? 1 : 0,
    disabled ? 1 : 0,
  ].map(signatureValue).join('|')
}

function sub2APIAccountRowSignature(account: Sub2APIRemoteAccount, selected: boolean, disabled: boolean) {
  return [
    account.id,
    boundedSignatureText(account.email || account.name || account.id),
    boundedSignatureText(account.plan_type, 48),
    boundedSignatureText(account.status, 48),
    account.has_access_token ? 1 : 0,
    selected ? 1 : 0,
    disabled ? 1 : 0,
  ].map(signatureValue).join('|')
}

function signatureValue(value: unknown) {
  return String(value ?? '').replaceAll('|', '/')
}

function boundedSignatureText(value: unknown, limit = 120) {
  const text = signatureValue(value)
  if (text.length <= limit) return text
  return `${text.length}:${text.slice(0, limit)}:${text.slice(-16)}`
}

function selectSub2APIGroup(group: Sub2APIAccountGroup) {
  const next = new Set(selectedSub2APIAccountIds.value)
  for (const account of group.accounts) {
    if (account.id) next.add(account.id)
  }
  selectedSub2APIAccountIds.value = Array.from(next)
}

function clearSub2APIGroup(group: Sub2APIAccountGroup) {
  const clearIds = new Set(group.accounts.map((account) => account.id))
  selectedSub2APIAccountIds.value = selectedSub2APIAccountIds.value.filter((id) => !clearIds.has(id))
}

function isSub2APIGroupCollapsed(groupKey: string) {
  return Boolean(collapsedSub2APIGroups.value[groupKey])
}

function toggleSub2APIGroupCollapsed(groupKey: string) {
  collapsedSub2APIGroups.value = {
    ...collapsedSub2APIGroups.value,
    [groupKey]: !collapsedSub2APIGroups.value[groupKey],
  }
}

function setImportSub2APIByGroups(checked?: boolean) {
  importSub2APIByGroups.value = Boolean(checked)
}

function selectAllItems() {
  if (activeMode.value === 'cpa') {
    selectedCPAFileNames.value = remoteCPAFiles.value.map((file) => file.name).filter(Boolean)
    return
  }
  selectedSub2APIAccountIds.value = sub2apiAccounts.value.map((account) => account.id).filter(Boolean)
}

function clearSelection() {
  selectedCPAFileNames.value = []
  selectedSub2APIAccountIds.value = []
}

function emitStarted(
  mode: RemoteAccountImportMode,
  sourceId: string,
  job: CPAImportJob | null,
  title: string,
  total: number,
) {
  const jobId = String(job?.job_id || '').trim()
  if (!job || !jobId || emittedImportJobIds.has(jobId)) return
  emittedImportJobIds.add(jobId)
  emit('started', {
    mode,
    source_id: sourceId,
    job,
    title,
    total: Math.max(0, Number(total || job.total || 0)),
  })
}

function emitRecoverableImportJobs(
  mode: RemoteAccountImportMode,
  sources: RemoteImportSource[],
  currentSourceId: string,
) {
  if (!props.externalTracking) return
  const current = sources.find((source) => source.id === currentSourceId)
  const orderedSources = current
    ? [current, ...sources.filter((source) => source.id !== currentSourceId)]
    : sources
  const title = mode === 'cpa' ? '导入远程 CPA' : '导入 Sub2API 账号'
  for (const source of orderedSources) {
    const job = source.import_job
    if (!job || (job.status !== 'pending' && job.status !== 'running')) continue
    emitStarted(mode, source.id, job, title, job.total)
  }
}

async function pollImportJob(sourceId: string, title: string, total: number) {
  for (let index = 0; index < 180; index += 1) {
    const response = activeMode.value === 'cpa'
      ? await accountImportsApi.getCPAImportJob(sourceId)
      : await accountImportsApi.getSub2APIImportJob(sourceId)
    importJob.value = response.import_job || null
    emit('progress', { title, total, job: importJob.value })
    if (importJob.value?.terminal) return importJob.value
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
  }
  throw new Error('导入进度超时')
}

async function startImport() {
  if (activeMode.value === 'cpa') {
    await startCPAImport()
    return
  }
  await startSub2APIImport()
}

async function startCPAImport() {
  const poolId = selectedCPAPoolId.value
  const availableNames = new Set(remoteCPAFiles.value.map((file) => file.name))
  const names = Array.from(new Set(selectedCPAFileNames.value.filter((name) => availableNames.has(name))))
  if (!poolId || !names.length) return
  const confirmed = await confirmDialog.ask({
    title: '确认远程 CPA 导入',
    message: `即将从 CPA 连接导入 ${names.length} 个文件里的账号，并写入本地号池。`,
    confirmText: '开始导入',
    cancelText: '取消',
  })
  if (!confirmed) return

  await runBusy(async () => {
    const title = '导入远程 CPA'
    emit('progress', { title, total: names.length })
    try {
      const start = await accountImportsApi.startCPAImport(poolId, names)
      importJob.value = start.import_job || null
      emitStarted('cpa', poolId, importJob.value, title, names.length)
      if (props.externalTracking && !importJob.value?.job_id) throw new Error('后端没有返回 CPA 导入任务')
      if (props.externalTracking) return
      emit('progress', { title, total: names.length, job: importJob.value })
      const job = await pollImportJob(poolId, title, names.length)
      showImportResult(job)
      if (job?.status !== 'failed') emit('imported')
    } catch (error: any) {
      const message = error.message || '远程 CPA 导入失败'
      emit('progress', { title, total: names.length, error: message })
      if (!props.externalTracking) toast.error(message)
    }
  })
}

function buildSub2APIGroupBindings(accountIds: string[]) {
  if (!importSub2APIByGroups.value) return []
  const selected = new Set(accountIds)
  const bindings: Sub2APIImportGroupBinding[] = []
  for (const group of sub2apiAccountGroups.value) {
    const ids = group.accounts.map((account) => account.id).filter((id) => selected.has(id))
    if (!ids.length) continue
    if (!group.remoteGroupId && group.name === UNGROUPED_SUB2API_GROUP_NAME) continue
    bindings.push({
      remote_group_id: group.remoteGroupId,
      name: group.name,
      account_ids: ids,
    })
  }
  return bindings
}

async function startSub2APIImport() {
  const serverId = selectedSub2APIServerId.value
  const availableIds = new Set(sub2apiAccounts.value.map((account) => account.id))
  const accountIds = Array.from(new Set(selectedSub2APIAccountIds.value.filter((id) => availableIds.has(id))))
  if (!serverId || !accountIds.length) return
  const groupBindings = buildSub2APIGroupBindings(accountIds)
  const groupText = groupBindings.length
    ? `，并按 ${groupBindings.length} 个远端分组创建或复用本地同名分组`
    : '，不写入本地分组绑定'
  const confirmed = await confirmDialog.ask({
    title: '确认 Sub2API 导入',
    message: `即将从 Sub2API 连接导入 ${accountIds.length} 个账号${groupText}。`,
    confirmText: '开始导入',
    cancelText: '取消',
  })
  if (!confirmed) return

  await runBusy(async () => {
    const title = '导入 Sub2API 账号'
    emit('progress', { title, total: accountIds.length })
    try {
      const start = await accountImportsApi.startSub2APIImport(serverId, accountIds, {
        group_bindings: groupBindings,
        create_account_groups: importSub2APIByGroups.value,
      })
      importJob.value = start.import_job || null
      emitStarted('sub2api', serverId, importJob.value, title, accountIds.length)
      if (props.externalTracking && !importJob.value?.job_id) throw new Error('后端没有返回 Sub2API 导入任务')
      if (props.externalTracking) return
      emit('progress', { title, total: accountIds.length, job: importJob.value })
      const job = await pollImportJob(serverId, title, accountIds.length)
      showImportResult(job)
      if (job?.status !== 'failed') emit('imported')
    } catch (error: any) {
      const message = error.message || 'Sub2API 导入失败'
      emit('progress', { title, total: accountIds.length, error: message })
      if (!props.externalTracking) toast.error(message)
    }
  })
}

function showImportResult(job: CPAImportJob | null) {
  if (!job) {
    toast.error('没有获取到导入结果')
    return
  }
  if (job.result_tone === 'danger') {
    toast.error(job.result_message)
    return
  }
  if (job.result_tone === 'warning') {
    toast.warning(job.result_message)
    return
  }
  toast.success(job.result_message)
}
</script>

<style scoped>
.remote-account-groups {
  min-width: 0;
}

.remote-account-group + .remote-account-group {
  border-top: 1px solid hsl(var(--border));
}

.remote-account-group__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  background: hsl(var(--muted) / 0.2);
}

.remote-account-group__toggle {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  padding: 0;
  text-align: left;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--foreground));
  cursor: pointer;
}

.remote-account-group__actions {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.remote-account-group__items {
  min-width: 0;
}

@media (max-width: 640px) {
  .remote-account-group__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .remote-account-group__actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
