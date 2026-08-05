<template>
  <PagePanel class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="ui-section-title">{{ activeTab === 'cpa' ? 'CPA' : 'Sub2API' }}</p>
        <p class="mt-1 text-xs text-muted-foreground">
          账号管理页的远程导入会读取这里保存的连接。
        </p>
      </div>
      <Button size="sm" variant="outline" :disabled="externalSourcesLoading" @click="$emit('load')">
        {{ externalSourcesLoading ? '刷新中...' : '刷新连接' }}
      </Button>
    </div>

    <div class="grid gap-4">
      <div v-if="activeTab === 'cpa'" class="rounded-xl border border-border bg-card p-4">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-sm font-semibold text-foreground">CPA 连接管理</p>
            <p class="mt-1 text-xs text-muted-foreground">保存 CLIProxyAPI 地址和管理密钥，供远程 CPA 导入使用。</p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <span class="text-xs text-muted-foreground">{{ cpaPools.length }} 个连接</span>
            <Button size="xs" variant="outline" :disabled="savingExternalSource === 'cpa'" @click="$emit('createCpa')">
              新增
            </Button>
          </div>
        </div>

        <div class="mt-4 space-y-2">
          <div
            v-for="pool in cpaPools"
            :key="pool.id"
            class="rounded-xl border border-border bg-background px-3 py-2 text-xs"
          >
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="truncate font-medium text-foreground">{{ pool.name || pool.id }}</p>
                <p class="mt-1 truncate font-mono text-muted-foreground">{{ pool.base_url }}</p>
              </div>
              <div class="flex gap-1.5">
                <Button size="xs" variant="outline" root-class="w-14 justify-center whitespace-nowrap" @click="$emit('importCpa', pool)">导入</Button>
                <Button size="xs" variant="outline" root-class="w-14 justify-center whitespace-nowrap" :disabled="testingExternalSource === pool.id" @click="$emit('testCpa', pool)">
                  {{ testingExternalSource === pool.id ? '测试中' : '测试' }}
                </Button>
                <Button size="xs" variant="outline" root-class="w-14 justify-center whitespace-nowrap" @click="$emit('editCpa', pool)">编辑</Button>
                <Button size="xs" variant="outline" root-class="w-14 justify-center whitespace-nowrap text-rose-600" :disabled="savingExternalSource === pool.id" @click="$emit('deleteCpa', pool)">
                  删除
                </Button>
              </div>
            </div>
          </div>
          <StateBlock v-if="!cpaLoading && cpaPools.length === 0" tag="p" compact dashed>
            暂无 CPA 连接。
          </StateBlock>
        </div>
      </div>

      <div v-if="activeTab === 'sub2api'" class="rounded-xl border border-border bg-card p-4">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-sm font-semibold text-foreground">Sub2API 连接管理</p>
            <p class="mt-1 text-xs text-muted-foreground">保存 Sub2API 服务器，用于读取 OpenAI OAuth 账号并导入本地号池。</p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <span class="text-xs text-muted-foreground">{{ sub2apiServers.length }} 个连接</span>
            <Button size="xs" variant="outline" :disabled="savingExternalSource === 'sub2api'" @click="$emit('createSub2api')">
              新增
            </Button>
          </div>
        </div>

        <div class="mt-4 space-y-2">
          <div
            v-for="server in sub2apiServers"
            :key="server.id"
            class="rounded-xl border border-border bg-background px-3 py-2 text-xs"
          >
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="truncate font-medium text-foreground">{{ server.name || server.id }}</p>
                <p class="mt-1 truncate font-mono text-muted-foreground">{{ server.base_url }}</p>
                <p class="mt-1 text-muted-foreground">
                  {{ server.email || '未填邮箱' }} · {{ server.has_api_key ? '已配置 API Key' : '未配置 API Key' }}
                  <span v-if="server.group_id"> · 分组 {{ server.group_id }}</span>
                </p>
              </div>
              <div class="flex flex-wrap justify-end gap-1.5">
                <Button size="xs" variant="outline" root-class="w-14 justify-center whitespace-nowrap" @click="$emit('importSub2api', server)">导入</Button>
                <Button size="xs" variant="outline" root-class="w-14 justify-center whitespace-nowrap" :disabled="testingExternalSource === server.id" @click="$emit('testSub2api', server)">
                  {{ testingExternalSource === server.id ? '测试中' : '测试' }}
                </Button>
                <Button size="xs" variant="outline" root-class="w-16 justify-center whitespace-nowrap" :disabled="sub2apiGroupsLoadingId === server.id" @click="$emit('loadSub2apiGroups', server)">
                  {{ sub2apiGroupsLoadingId === server.id ? '读取中' : '读分组' }}
                </Button>
                <Button size="xs" variant="outline" root-class="w-14 justify-center whitespace-nowrap" @click="$emit('editSub2api', server)">编辑</Button>
                <Button size="xs" variant="outline" root-class="w-14 justify-center whitespace-nowrap text-rose-600" :disabled="savingExternalSource === server.id" @click="$emit('deleteSub2api', server)">
                  删除
                </Button>
              </div>
            </div>

            <div v-if="sub2apiGroups[server.id]?.length" class="mt-2 flex flex-wrap gap-1.5">
              <button
                v-for="group in sub2apiGroups[server.id]"
                :key="group.id"
                type="button"
                class="rounded-md border border-border bg-card px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                @click="$emit('importSub2api', server, group.id)"
              >
                {{ group.name || group.id }} · {{ group.active_account_count }}/{{ group.account_count }}
              </button>
            </div>
          </div>
          <StateBlock v-if="!sub2apiLoading && sub2apiServers.length === 0" tag="p" compact dashed>
            暂无 Sub2API 连接。
          </StateBlock>
        </div>
      </div>
    </div>
  </PagePanel>
</template>

<script setup lang="ts">
import { Button } from 'nanocat-ui'
import type { CPAPool, Sub2APIRemoteGroup, Sub2APIServer } from '@/api/accountImports'
import PagePanel from '@/components/ai/PagePanel.vue'
import StateBlock from '@/components/ai/StateBlock.vue'

defineProps<{
  activeTab: 'cpa' | 'sub2api'
  cpaPools: CPAPool[]
  cpaLoading: boolean
  sub2apiServers: Sub2APIServer[]
  sub2apiLoading: boolean
  sub2apiGroups: Record<string, Sub2APIRemoteGroup[]>
  sub2apiGroupsLoadingId: string
  savingExternalSource: string
  testingExternalSource: string
  externalSourcesLoading: boolean
}>()

defineEmits<{
  load: []
  createCpa: []
  importCpa: [pool: CPAPool]
  testCpa: [pool: CPAPool]
  editCpa: [pool: CPAPool]
  deleteCpa: [pool: CPAPool]
  createSub2api: []
  importSub2api: [server: Sub2APIServer, groupId?: string]
  testSub2api: [server: Sub2APIServer]
  loadSub2apiGroups: [server: Sub2APIServer]
  editSub2api: [server: Sub2APIServer]
  deleteSub2api: [server: Sub2APIServer]
}>()
</script>
